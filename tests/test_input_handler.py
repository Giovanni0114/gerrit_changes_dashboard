"""Tests for input_handler.py — regression guard for key routing, input collection,
digits-only filtering, special-char immediate completion, and action dispatch."""

import pytest
from conftest import FakeApp

from input_handler import (
    InputField,
    InputHandler,
    add_change,
    fetch_my_changes,
    handle_deletion,
    open_approvals_in_editor,
    open_change,
    open_config_in_editor,
    parse_idx_notation,
    set_automerge,
    toggle_disable,
    toggle_waiting,
    validate_idx,
)
from models import TrackedChange


def _make_changes(n: int) -> list[TrackedChange]:
    """Create n dummy TrackedChange objects for testing."""
    return [TrackedChange(host=f"host{i}", hash=f"hash{i}") for i in range(1, n + 1)]


# ---------------------------------------------------------------------------
# InputField dataclass
# ---------------------------------------------------------------------------


class TestInputField:
    def test_defaults(self) -> None:
        f = InputField("hash")
        assert f.name == "hash"
        assert f.special_chars == frozenset()
        assert f.digits_only is False

    def test_custom_values(self) -> None:
        f = InputField("idx", frozenset({"a", "x"}), True)
        assert f.name == "idx"
        assert f.special_chars == frozenset({"a", "x"})
        assert f.digits_only is True

    def test_frozen(self) -> None:
        f = InputField("idx")
        with pytest.raises(AttributeError):
            f.name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# InputHandler — sequence building
# ---------------------------------------------------------------------------


class TestSequenceBuilding:
    def test_r_triggers_refresh(self, app: FakeApp) -> None:
        h = InputHandler(app)
        h.handle_key("r")
        assert app.refresh_called

    def test_q_triggers_quit(self, app: FakeApp) -> None:
        h = InputHandler(app)
        h.handle_key("q")
        assert app.quit_called

    def test_invalid_key_sets_status(self, app: FakeApp) -> None:
        h = InputHandler(app)
        h.handle_key("z")
        assert "not allowed" in app.status_msg

    def test_space_then_invalid_key_sets_status(self, app: FakeApp) -> None:
        h = InputHandler(app)
        h.handle_key(" ")
        h.handle_key("z")
        assert "not allowed" in app.status_msg

    def test_enter_on_empty_sequence_is_noop(self, app: FakeApp) -> None:
        h = InputHandler(app)
        h.handle_key("<enter>")
        assert not app.quit_called
        assert not app.refresh_called
        assert app.status_msg == ""

    def test_space_builds_sequence(self, app: FakeApp) -> None:
        h = InputHandler(app)
        h.handle_key(" ")
        assert h.sequence == [" "]

    def test_space_then_leader_key_sets_input_mode(self, app: FakeApp) -> None:
        h = InputHandler(app)
        h.handle_key(" ")
        h.handle_key("w")
        # Should now be in input mode waiting for idx
        assert h.input is not None
        assert h.current_field is not None
        assert h.current_field.name == "idx"


# ---------------------------------------------------------------------------
# InputHandler — ESC resets
# ---------------------------------------------------------------------------


class TestEscReset:
    def test_esc_on_empty_resets(self, app: FakeApp) -> None:
        h = InputHandler(app)
        h.handle_key("<esc>")
        assert h.sequence == []
        assert h.input is None

    def test_esc_mid_sequence_resets(self, app: FakeApp) -> None:
        h = InputHandler(app)
        h.handle_key(" ")
        h.handle_key("<esc>")
        assert h.sequence == []

    def test_esc_mid_input_resets(self, app: FakeApp) -> None:
        h = InputHandler(app)
        h.handle_key(" ")
        h.handle_key("w")
        h.handle_key("1")
        h.handle_key("<esc>")
        assert h.input is None
        assert h.current_field is None
        assert h.sequence == []
        assert h.context == {}


# ---------------------------------------------------------------------------
# InputHandler — input collection basics
# ---------------------------------------------------------------------------


class TestInputCollection:
    def _enter_input_mode(self, app: FakeApp) -> InputHandler:
        """Helper: Space + w puts us in input mode for idx (digits_only, special={a})."""
        h = InputHandler(app)
        h.handle_key(" ")
        h.handle_key("w")
        return h

    def test_chars_appended(self, app: FakeApp) -> None:
        h = self._enter_input_mode(app)
        h.handle_key("1")
        h.handle_key("2")
        assert h.input == "12"

    def test_backspace_trims(self, app: FakeApp) -> None:
        h = self._enter_input_mode(app)
        h.handle_key("1")
        h.handle_key("2")
        h.handle_key("<bs>")
        assert h.input == "1"

    def test_backspace_on_empty_stays_empty(self, app: FakeApp) -> None:
        h = self._enter_input_mode(app)
        h.handle_key("<bs>")
        assert h.input == ""

    def test_enter_completes_field_and_executes(self, app: FakeApp) -> None:
        app.changes = _make_changes(5)
        h = self._enter_input_mode(app)
        h.handle_key("3")
        h.handle_key("<enter>")
        assert app.toggled_waiting == [3]
        assert h.input is None
        assert h.sequence == []

    def test_input_not_leaked_to_sequence(self, app: FakeApp) -> None:
        """Keys typed during input mode must not affect the sequence."""
        h = self._enter_input_mode(app)
        h.handle_key("r")  # would normally refresh — but we're in input mode
        assert not app.refresh_called
        assert h.input == ""  # 'r' ignored (digits_only)


# ---------------------------------------------------------------------------
# InputHandler — digits_only filtering
# ---------------------------------------------------------------------------


class TestDigitsOnly:
    def _enter_digits_field(self, app: FakeApp) -> InputHandler:
        h = InputHandler(app)
        h.handle_key(" ")
        h.handle_key("o")  # open_change — digits_only, no special chars
        return h

    def test_digits_accepted(self, app: FakeApp) -> None:
        h = self._enter_digits_field(app)
        h.handle_key("4")
        h.handle_key("2")
        assert h.input == "42"

    def test_letters_silently_ignored(self, app: FakeApp) -> None:
        h = self._enter_digits_field(app)
        h.handle_key("a")
        h.handle_key("b")
        assert h.input == ""

    def test_mixed_only_digits_kept(self, app: FakeApp) -> None:
        h = self._enter_digits_field(app)
        for ch in "a1b2c3":
            h.handle_key(ch)
        assert h.input == "123"


# ---------------------------------------------------------------------------
# InputHandler — special-char immediate completion
# ---------------------------------------------------------------------------


class TestSpecialCharCompletion:
    def _enter_deletion_field(self, app: FakeApp) -> InputHandler:
        """Space + x → idx field with special_chars={a,x,r}, digits_only=True."""
        h = InputHandler(app)
        h.handle_key(" ")
        h.handle_key("x")
        return h

    def test_special_char_a_completes_immediately(self, app: FakeApp) -> None:
        h = self._enter_deletion_field(app)
        h.handle_key("a")
        assert app.delete_all_submitted_called
        assert h.input is None
        assert h.sequence == []

    def test_special_char_x_completes_immediately(self, app: FakeApp) -> None:
        h = self._enter_deletion_field(app)
        h.handle_key("x")
        assert app.purge_deleted_called

    def test_special_char_r_completes_immediately(self, app: FakeApp) -> None:
        h = self._enter_deletion_field(app)
        h.handle_key("r")
        assert app.restore_all_called

    def test_special_char_stored_as_value(self, app: FakeApp) -> None:
        """Context must hold the char itself, not accumulate it as regular input."""
        # Use a variant: 'a' for waiting (only {a}), verify toggle_all_waiting called.
        h2 = InputHandler(app)
        h2.handle_key(" ")
        h2.handle_key("w")
        h2.handle_key("a")
        assert app.all_waiting_toggled == 1

    def test_digit_after_partial_does_not_trigger_special(self, app: FakeApp) -> None:
        app.changes = _make_changes(5)
        h = self._enter_deletion_field(app)
        h.handle_key("5")
        h.handle_key("<enter>")
        # idx=5 → toggle_deleted(5)
        assert app.toggled_deleted == [5]


# ---------------------------------------------------------------------------
# InputHandler — multi-field action (add_change: hash + host)
# ---------------------------------------------------------------------------


class TestMultiFieldAction:
    def test_add_change_two_enters(self, app: FakeApp) -> None:
        h = InputHandler(app)
        for key in [" ", "a"]:
            h.handle_key(key)
        # Now in input mode for 'hash'
        assert h.current_field is not None
        assert h.current_field.name == "hash"
        for ch in "abc123":
            h.handle_key(ch)
        h.handle_key("<enter>")
        # Now should be collecting 'host'
        assert h.current_field is not None
        assert h.current_field.name == "host"
        for ch in "gerrit.example.com":
            h.handle_key(ch)
        h.handle_key("<enter>")
        assert app.added_changes == [("abc123", "gerrit.example.com")]

    def test_esc_mid_second_field_aborts(self, app: FakeApp) -> None:
        h = InputHandler(app)
        for key in [" ", "a"]:
            h.handle_key(key)
        for ch in "abc123":
            h.handle_key(ch)
        h.handle_key("<enter>")
        h.handle_key("<esc>")
        assert app.added_changes == []
        assert h.sequence == []


# ---------------------------------------------------------------------------
# InputHandler — prompt()
# ---------------------------------------------------------------------------


class TestPrompt:
    def test_empty_sequence_returns_empty(self, app: FakeApp) -> None:
        h = InputHandler(app)
        assert h.prompt(0) == ""

    def test_sequence_no_input_returns_action_name(self, app: FakeApp) -> None:
        h = InputHandler(app)
        h.handle_key(" ")
        # Space alone — last key is " ", not in PROMPTS_FOR_LAST_KEY → empty string
        assert h.prompt(0) == ""

    def test_prompt_in_input_mode_shows_field_name(self, app: FakeApp) -> None:
        h = InputHandler(app)
        h.handle_key(" ")
        h.handle_key("w")
        p = h.prompt(0)
        assert "idx" in p
        assert "ESC=cancel" in p

    def test_prompt_shows_special_chars_when_present(self, app: FakeApp) -> None:
        h = InputHandler(app)
        h.handle_key(" ")
        h.handle_key("x")
        p = h.prompt(0)
        # all three special chars must appear
        assert "a" in p
        assert "x" in p
        assert "r" in p

    def test_prompt_no_special_chars_bracket_absent(self, app: FakeApp) -> None:
        h = InputHandler(app)
        h.handle_key(" ")
        h.handle_key("o")  # digits_only, no special chars
        p = h.prompt(0)
        assert "[" not in p or "ESC" in p  # only the ESC bracket should appear


# ---------------------------------------------------------------------------
# InputHandler — hints()
# ---------------------------------------------------------------------------


class TestHints:
    def test_default_hints(self, app: FakeApp) -> None:
        h = InputHandler(app)
        hints = h.hints()
        assert "quit" in hints
        assert "refresh" in hints
        assert "Space" in hints

    def test_hints_after_space(self, app: FakeApp) -> None:
        h = InputHandler(app)
        h.handle_key(" ")
        hints = h.hints()
        assert "add" in hints
        assert "wait" in hints
        assert "delete" in hints

    def test_hints_reset_after_action(self, app: FakeApp) -> None:
        h = InputHandler(app)
        h.handle_key("r")
        hints = h.hints()
        assert "quit" in hints  # back to default


# ---------------------------------------------------------------------------
# Action functions — direct unit tests
# ---------------------------------------------------------------------------


class TestToggleWaiting:
    def test_numeric_idx(self, app: FakeApp) -> None:
        app.changes = _make_changes(5)
        toggle_waiting(app, {"idx": "3"})
        assert app.toggled_waiting == [3]

    def test_idx_a_calls_toggle_all(self, app: FakeApp) -> None:
        toggle_waiting(app, {"idx": "a"})
        assert app.all_waiting_toggled == 1

    def test_invalid_idx_sets_status(self, app: FakeApp) -> None:
        toggle_waiting(app, {"idx": "abc"})
        assert "Invalid" in app.status_msg
        assert app.toggled_waiting == []

    def test_out_of_range_idx_sets_status(self, app: FakeApp) -> None:
        app.changes = _make_changes(3)
        toggle_waiting(app, {"idx": "5"})
        assert "Invalid" in app.status_msg
        assert app.toggled_waiting == []

    def test_zero_idx_sets_status(self, app: FakeApp) -> None:
        app.changes = _make_changes(3)
        toggle_waiting(app, {"idx": "0"})
        assert "Invalid" in app.status_msg
        assert app.toggled_waiting == []

    def test_multi_idx_range(self, app: FakeApp) -> None:
        app.changes = _make_changes(5)
        toggle_waiting(app, {"idx": "2-4"})
        assert app.toggled_waiting == [2, 3, 4]

    def test_multi_idx_list(self, app: FakeApp) -> None:
        app.changes = _make_changes(5)
        toggle_waiting(app, {"idx": "1,3,5"})
        assert app.toggled_waiting == [1, 3, 5]

    def test_multi_idx_combined(self, app: FakeApp) -> None:
        app.changes = _make_changes(10)
        toggle_waiting(app, {"idx": "1-3, 7, 9-10"})
        assert app.toggled_waiting == [1, 2, 3, 7, 9, 10]


class TestHandleDeletion:
    def test_numeric_idx(self, app: FakeApp) -> None:
        app.changes = _make_changes(5)
        handle_deletion(app, {"idx": "2"})
        assert app.toggled_deleted == [2]

    def test_idx_a_deletes_all_submitted(self, app: FakeApp) -> None:
        handle_deletion(app, {"idx": "a"})
        assert app.delete_all_submitted_called

    def test_idx_x_purges_deleted(self, app: FakeApp) -> None:
        handle_deletion(app, {"idx": "x"})
        assert app.purge_deleted_called

    def test_idx_r_restores_all(self, app: FakeApp) -> None:
        handle_deletion(app, {"idx": "r"})
        assert app.restore_all_called

    def test_invalid_idx_sets_status(self, app: FakeApp) -> None:
        handle_deletion(app, {"idx": "bad"})
        assert "Invalid" in app.status_msg

    def test_out_of_range_idx_sets_status(self, app: FakeApp) -> None:
        app.changes = _make_changes(2)
        handle_deletion(app, {"idx": "10"})
        assert "Invalid" in app.status_msg
        assert app.toggled_deleted == []

    def test_multi_idx_deletion(self, app: FakeApp) -> None:
        app.changes = _make_changes(5)
        handle_deletion(app, {"idx": "1,3"})
        assert app.toggled_deleted == [1, 3]


class TestToggleDisable:
    def test_numeric_idx(self, app: FakeApp) -> None:
        app.changes = _make_changes(5)
        toggle_disable(app, {"idx": "1"})
        assert app.toggled_disabled == [1]

    def test_idx_a_calls_toggle_all_disabled(self, app: FakeApp) -> None:
        toggle_disable(app, {"idx": "a"})
        assert app.all_disabled_toggled == 1

    def test_invalid_idx_sets_status(self, app: FakeApp) -> None:
        toggle_disable(app, {"idx": "z"})
        assert "Invalid" in app.status_msg

    def test_out_of_range_idx_sets_status(self, app: FakeApp) -> None:
        app.changes = _make_changes(3)
        toggle_disable(app, {"idx": "0"})
        assert "Invalid" in app.status_msg
        assert app.toggled_disabled == []

    def test_multi_idx_disable(self, app: FakeApp) -> None:
        app.changes = _make_changes(5)
        toggle_disable(app, {"idx": "2-4"})
        assert app.toggled_disabled == [2, 3, 4]


class TestOpenChange:
    def test_numeric_idx(self, app: FakeApp) -> None:
        app.changes = _make_changes(10)
        open_change(app, {"idx": "7"})
        assert app.opened_webui == [7]

    def test_invalid_idx_sets_status(self, app: FakeApp) -> None:
        open_change(app, {"idx": "x"})
        assert "Invalid" in app.status_msg

    def test_out_of_range_idx_sets_status(self, app: FakeApp) -> None:
        app.changes = _make_changes(3)
        open_change(app, {"idx": "99"})
        assert "Invalid" in app.status_msg
        assert app.opened_webui == []

    def test_multi_idx_open(self, app: FakeApp) -> None:
        app.changes = _make_changes(5)
        open_change(app, {"idx": "1,3,5"})
        assert app.opened_webui == [1, 3, 5]


class TestSetAutomerge:
    def test_numeric_idx(self, app: FakeApp) -> None:
        app.changes = _make_changes(5)
        set_automerge(app, {"idx": "2"})
        assert app.automerge_set == [2]

    def test_invalid_idx_sets_status(self, app: FakeApp) -> None:
        set_automerge(app, {"idx": "nope"})
        assert "Invalid" in app.status_msg

    def test_out_of_range_idx_sets_status(self, app: FakeApp) -> None:
        app.changes = _make_changes(2)
        set_automerge(app, {"idx": "5"})
        assert "Invalid" in app.status_msg
        assert app.automerge_set == []

    def test_multi_idx_automerge(self, app: FakeApp) -> None:
        app.changes = _make_changes(5)
        set_automerge(app, {"idx": "1-3"})
        assert app.automerge_set == [1, 2, 3]


class TestAddChange:
    def test_basic_add(self, app: FakeApp) -> None:
        add_change(app, {"hash": "abc123", "host": "gerrit.example.com"})
        assert app.added_changes == [("abc123", "gerrit.example.com")]

    def test_empty_hash_sets_status(self, app: FakeApp) -> None:
        add_change(app, {"hash": "", "host": "gerrit.example.com"})
        assert "Invalid hash" in app.status_msg
        assert app.added_changes == []

    def test_empty_host_uses_default_host(self, app: FakeApp) -> None:
        app.default_host = "default.gerrit.com"
        add_change(app, {"hash": "abc", "host": ""})
        assert app.added_changes == [("abc", "default.gerrit.com")]

    def test_empty_host_no_default_sets_status(self, app: FakeApp) -> None:
        app.default_host = None
        add_change(app, {"hash": "abc", "host": ""})
        assert "No host" in app.status_msg
        assert app.added_changes == []

    def test_digit_host_resolves_from_changes(self, app: FakeApp) -> None:
        app.changes = [TrackedChange(host="row1.gerrit.com", hash="h1")]
        add_change(app, {"hash": "newhash", "host": "1"})
        assert app.added_changes == [("newhash", "row1.gerrit.com")]

    def test_digit_host_out_of_range_sets_status(self, app: FakeApp) -> None:
        app.changes = [TrackedChange(host="row1.gerrit.com", hash="h1")]
        add_change(app, {"hash": "newhash", "host": "5"})
        assert "No change at index" in app.status_msg
        assert app.added_changes == []

    def test_literal_host_used_as_is(self, app: FakeApp) -> None:
        add_change(app, {"hash": "abc", "host": "custom.host"})
        assert app.added_changes == [("abc", "custom.host")]


# ---------------------------------------------------------------------------
# Fetch open changes — keybind routing (TC-007, TC-008, TC-009)
# ---------------------------------------------------------------------------


class TestFetchOpenChanges:
    def test_f_triggers_fetch(self, app: FakeApp) -> None:
        """TC-007: Pressing f calls fetch_open_changes()."""
        h = InputHandler(app)
        h.handle_key("f")
        assert app.fetch_open_changes_called

    def test_f_in_leader_sequence_does_nothing(self, app: FakeApp) -> None:
        """f after Space is rejected (not a leader action)."""
        h = InputHandler(app)
        h.handle_key(" ")
        h.handle_key("f")
        assert not app.fetch_open_changes_called
        assert "not allowed" in app.status_msg

    def test_hints_show_f_in_default_state(self, app: FakeApp) -> None:
        """TC-009: Default hints include 'fetch' for the f key."""
        h = InputHandler(app)
        hints = h.hints()
        assert "fetch" in hints

    def test_hints_after_space_do_not_show_fetch(self, app: FakeApp) -> None:
        """After Space, hints should NOT include fetch."""
        h = InputHandler(app)
        h.handle_key(" ")
        hints = h.hints()
        assert "fetch" not in hints

    def test_f_resets_handler(self, app: FakeApp) -> None:
        """f should execute immediately and reset state."""
        h = InputHandler(app)
        h.handle_key("f")
        assert h.input is None
        assert h.sequence == []
        assert h.context == {}


class TestFetchMyChangesAction:
    def test_calls_fetch_open_changes(self, app: FakeApp) -> None:
        """Direct unit test for fetch_my_changes action function."""
        fetch_my_changes(app, {})
        assert app.fetch_open_changes_called


# ---------------------------------------------------------------------------
# Editor keybinds — Space + e + c / Space + e + a (feature 009)
# ---------------------------------------------------------------------------


class TestEditorKeybinds:
    def test_space_e_intermediate_state_no_action(self, app: FakeApp) -> None:
        """After Space + e alone, no editor action is triggered (waiting for c or a)."""
        h = InputHandler(app)
        h.handle_key(" ")
        h.handle_key("e")
        assert not app.open_config_in_editor_called
        assert not app.open_approvals_in_editor_called
        assert h.sequence == [" ", "e"]

    def test_space_e_c_opens_config(self, app: FakeApp) -> None:
        """Space + e + c triggers open_config_in_editor."""
        h = InputHandler(app)
        h.handle_key(" ")
        h.handle_key("e")
        h.handle_key("c")
        assert app.open_config_in_editor_called
        assert not app.open_approvals_in_editor_called

    def test_space_e_a_opens_approvals(self, app: FakeApp) -> None:
        """Space + e + a triggers open_approvals_in_editor."""
        h = InputHandler(app)
        h.handle_key(" ")
        h.handle_key("e")
        h.handle_key("a")
        assert app.open_approvals_in_editor_called
        assert not app.open_config_in_editor_called

    def test_space_e_resets_after_c(self, app: FakeApp) -> None:
        """Handler resets to idle after Space + e + c completes."""
        h = InputHandler(app)
        h.handle_key(" ")
        h.handle_key("e")
        h.handle_key("c")
        assert h.sequence == []
        assert h.input is None

    def test_space_e_resets_after_a(self, app: FakeApp) -> None:
        """Handler resets to idle after Space + e + a completes."""
        h = InputHandler(app)
        h.handle_key(" ")
        h.handle_key("e")
        h.handle_key("a")
        assert h.sequence == []
        assert h.input is None

    def test_space_e_invalid_key_rejected(self, app: FakeApp) -> None:
        """After Space + e, an unrecognised key sets status and does not open editor."""
        h = InputHandler(app)
        h.handle_key(" ")
        h.handle_key("e")
        h.handle_key("z")
        assert "not allowed" in app.status_msg
        assert not app.open_config_in_editor_called
        assert not app.open_approvals_in_editor_called

    def test_esc_after_space_e_resets(self, app: FakeApp) -> None:
        """ESC after Space + e cancels without opening editor."""
        h = InputHandler(app)
        h.handle_key(" ")
        h.handle_key("e")
        h.handle_key("<esc>")
        assert h.sequence == []
        assert not app.open_config_in_editor_called
        assert not app.open_approvals_in_editor_called

    def test_hints_after_space_e(self, app: FakeApp) -> None:
        """After Space + e, hints show config and approvals options."""
        h = InputHandler(app)
        h.handle_key(" ")
        h.handle_key("e")
        hints = h.hints()
        assert "config" in hints
        assert "approvals" in hints

    def test_hints_after_space_include_editor(self, app: FakeApp) -> None:
        """After Space, hints include the 'editor' option."""
        h = InputHandler(app)
        h.handle_key(" ")
        hints = h.hints()
        assert "editor" in hints

    def test_e_alone_not_accepted(self, app: FakeApp) -> None:
        """Pressing e without Space prefix is rejected."""
        h = InputHandler(app)
        h.handle_key("e")
        assert "not allowed" in app.status_msg


class TestOpenEditorActions:
    def test_open_config_in_editor_action(self, app: FakeApp) -> None:
        """Direct unit test for open_config_in_editor action function."""
        open_config_in_editor(app, {})
        assert app.open_config_in_editor_called

    def test_open_approvals_in_editor_action(self, app: FakeApp) -> None:
        """Direct unit test for open_approvals_in_editor action function."""
        open_approvals_in_editor(app, {})
        assert app.open_approvals_in_editor_called


# ---------------------------------------------------------------------------
# parse_idx_notation — unit tests (feature 007)
# ---------------------------------------------------------------------------


class TestParseIdxNotation:
    """Tests for the advanced index notation parser."""

    def test_single_index(self) -> None:
        assert parse_idx_notation("3", 10) == [3]

    def test_comma_separated(self) -> None:
        assert parse_idx_notation("3,2,4", 10) == [2, 3, 4]

    def test_range(self) -> None:
        assert parse_idx_notation("3-8", 10) == [3, 4, 5, 6, 7, 8]

    def test_combined(self) -> None:
        assert parse_idx_notation("1-2, 3-5, 11, 23", 30) == [1, 2, 3, 4, 5, 11, 23]

    def test_whitespace_ignored(self) -> None:
        assert parse_idx_notation("  1 , 3 , 5  ", 10) == [1, 3, 5]

    def test_single_element_range(self) -> None:
        assert parse_idx_notation("5-5", 10) == [5]

    def test_duplicates_removed(self) -> None:
        assert parse_idx_notation("1,1,2,2", 5) == [1, 2]

    def test_overlapping_ranges(self) -> None:
        assert parse_idx_notation("1-3,2-4", 5) == [1, 2, 3, 4]

    def test_empty_string_returns_none(self) -> None:
        assert parse_idx_notation("", 10) is None

    def test_whitespace_only_returns_none(self) -> None:
        assert parse_idx_notation("   ", 10) is None

    def test_non_numeric_returns_none(self) -> None:
        assert parse_idx_notation("abc", 10) is None

    def test_zero_index_returns_none(self) -> None:
        assert parse_idx_notation("0", 10) is None

    def test_out_of_range_returns_none(self) -> None:
        assert parse_idx_notation("11", 10) is None

    def test_range_out_of_bounds_returns_none(self) -> None:
        assert parse_idx_notation("8-12", 10) is None

    def test_reversed_range_returns_none(self) -> None:
        assert parse_idx_notation("5-3", 10) is None

    def test_double_comma_returns_none(self) -> None:
        assert parse_idx_notation("1,,3", 10) is None

    def test_trailing_comma_returns_none(self) -> None:
        assert parse_idx_notation("1,3,", 10) is None

    def test_leading_comma_returns_none(self) -> None:
        assert parse_idx_notation(",1,3", 10) is None

    def test_double_dash_returns_none(self) -> None:
        assert parse_idx_notation("1--3", 10) is None

    def test_range_with_zero_start_returns_none(self) -> None:
        assert parse_idx_notation("0-3", 10) is None

    def test_max_idx_boundary(self) -> None:
        assert parse_idx_notation("10", 10) == [10]

    def test_max_idx_plus_one_returns_none(self) -> None:
        assert parse_idx_notation("11", 10) is None

    def test_range_at_boundary(self) -> None:
        assert parse_idx_notation("9-10", 10) == [9, 10]


# ---------------------------------------------------------------------------
# validate_idx — unit tests (feature 008)
# ---------------------------------------------------------------------------


class TestValidateIdx:
    """Tests for single-index validation with bounds checking."""

    def test_valid_idx(self) -> None:
        assert validate_idx("3", 5) == 3

    def test_valid_idx_boundary_low(self) -> None:
        assert validate_idx("1", 5) == 1

    def test_valid_idx_boundary_high(self) -> None:
        assert validate_idx("5", 5) == 5

    def test_zero_returns_none(self) -> None:
        assert validate_idx("0", 5) is None

    def test_out_of_range_returns_none(self) -> None:
        assert validate_idx("6", 5) is None

    def test_non_numeric_returns_none(self) -> None:
        assert validate_idx("abc", 5) is None

    def test_empty_returns_none(self) -> None:
        assert validate_idx("", 5) is None

    def test_large_number_returns_none(self) -> None:
        assert validate_idx("999", 3) is None

    def test_no_changes_returns_none(self) -> None:
        assert validate_idx("1", 0) is None


# ---------------------------------------------------------------------------
# Integration: multi-index through InputHandler keystroke flow (feature 007)
# ---------------------------------------------------------------------------


class TestMultiIdxKeystrokeFlow:
    """Test that multi-index notation works through the full InputHandler → action pipeline."""

    def test_range_via_keystrokes(self, app: FakeApp) -> None:
        """Space + w, type '1-3', Enter should toggle waiting for indexes 1, 2, 3."""
        app.changes = _make_changes(5)
        h = InputHandler(app)
        h.handle_key(" ")
        h.handle_key("w")
        for ch in "1-3":
            h.handle_key(ch)
        h.handle_key("<enter>")
        assert app.toggled_waiting == [1, 2, 3]

    def test_comma_list_via_keystrokes(self, app: FakeApp) -> None:
        """Space + d, type '1,3,5', Enter should toggle disabled for indexes 1, 3, 5."""
        app.changes = _make_changes(5)
        h = InputHandler(app)
        h.handle_key(" ")
        h.handle_key("d")
        for ch in "1,3,5":
            h.handle_key(ch)
        h.handle_key("<enter>")
        assert app.toggled_disabled == [1, 3, 5]

    def test_combined_notation_via_keystrokes(self, app: FakeApp) -> None:
        """Space + x, type '1-2,4', Enter should toggle deleted for indexes 1, 2, 4."""
        app.changes = _make_changes(5)
        h = InputHandler(app)
        h.handle_key(" ")
        h.handle_key("x")
        for ch in "1-2,4":
            h.handle_key(ch)
        h.handle_key("<enter>")
        assert app.toggled_deleted == [1, 2, 4]

    def test_out_of_range_via_keystrokes_sets_status(self, app: FakeApp) -> None:
        """Space + o, type '99', Enter should set error status when only 3 changes exist."""
        app.changes = _make_changes(3)
        h = InputHandler(app)
        h.handle_key(" ")
        h.handle_key("o")
        for ch in "99":
            h.handle_key(ch)
        h.handle_key("<enter>")
        assert "Invalid" in app.status_msg
        assert app.opened_webui == []

    def test_zero_via_keystrokes_sets_status(self, app: FakeApp) -> None:
        """Space + s, type '0', Enter should set error status."""
        app.changes = _make_changes(3)
        h = InputHandler(app)
        h.handle_key(" ")
        h.handle_key("s")
        h.handle_key("0")
        h.handle_key("<enter>")
        assert "Invalid" in app.status_msg
        assert app.automerge_set == []

    def test_extra_chars_accepted_in_input(self, app: FakeApp) -> None:
        """Dash and comma should be accepted in input mode for idx fields."""
        app.changes = _make_changes(5)
        h = InputHandler(app)
        h.handle_key(" ")
        h.handle_key("w")
        h.handle_key("1")
        h.handle_key("-")
        h.handle_key("3")
        assert h.input == "1-3"

    def test_space_in_idx_input_accepted(self, app: FakeApp) -> None:
        """Spaces in idx notation should be allowed (e.g. '1, 3')."""
        app.changes = _make_changes(5)
        h = InputHandler(app)
        h.handle_key(" ")
        h.handle_key("w")
        h.handle_key("1")
        h.handle_key(",")
        h.handle_key(" ")
        h.handle_key("3")
        assert h.input == "1, 3"
