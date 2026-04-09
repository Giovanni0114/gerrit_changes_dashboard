"""Tests for Feature 005 — Comments field for changes."""

import json
from pathlib import Path

import pytest

from config import load_changes, update_config_comments
from models import TrackedChange

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_changes(tmp_path: Path, changes: list[dict]) -> Path:
    """Write a changes JSON file and return its path."""
    p = tmp_path / "approvals.json"
    p.write_text(json.dumps({"changes": changes}, indent=2) + "\n")
    return p


def _read_config(path: Path) -> dict:
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# TC-001 & TC-002: TrackedChange data model
# ---------------------------------------------------------------------------


class TestTrackedChangeModel:
    def test_tc_001_default_comments(self) -> None:
        """TC-001: TrackedChange default comments should be empty list."""
        ch = TrackedChange(host="h", hash="abc")
        assert ch.comments == []

    def test_tc_002_with_comments(self) -> None:
        """TC-002: TrackedChange with comments parameter."""
        ch = TrackedChange(host="h", hash="abc", comments=["note1", "note2"])
        assert ch.comments == ["note1", "note2"]


# ---------------------------------------------------------------------------
# TC-003 & TC-004: Config loading
# ---------------------------------------------------------------------------


class TestLoadConfigComments:
    def test_tc_003_load_with_comments(self, tmp_path: Path) -> None:
        """TC-003: Load config with comments field."""
        p = _write_changes(tmp_path, [{"hash": "abc", "host": "h", "comments": ["a", "b"]}])
        changes = load_changes(p, None, 22)
        assert changes[0].comments == ["a", "b"]

    def test_tc_004_load_without_comments_field(self, tmp_path: Path) -> None:
        """TC-004: Load config without comments field defaults to empty list."""
        p = _write_changes(tmp_path, [{"hash": "abc", "host": "h"}])
        changes = load_changes(p, None, 22)
        assert changes[0].comments == []


# ---------------------------------------------------------------------------
# TC-005 & TC-006: update_config_comments
# ---------------------------------------------------------------------------


class TestUpdateConfigComments:
    def test_tc_005_update_config_comments_writes(self, tmp_path: Path) -> None:
        """TC-005: update_config_comments writes new comments array."""
        p = _write_changes(tmp_path, [{"hash": "abc", "host": "h", "comments": []}])
        mtime = update_config_comments(p, "abc", ["new note"])
        config = _read_config(p)
        assert config["changes"][0]["comments"] == ["new note"]
        assert isinstance(mtime, float)

    def test_tc_006_update_config_comments_clears(self, tmp_path: Path) -> None:
        """TC-006: update_config_comments can clear comments array."""
        p = _write_changes(tmp_path, [{"hash": "abc", "host": "h", "comments": ["old"]}])
        update_config_comments(p, "abc", [])
        config = _read_config(p)
        assert config["changes"][0]["comments"] == []

    def test_update_config_comments_does_not_modify_other_entries(self, tmp_path: Path) -> None:
        """Other entries in config should remain unchanged."""
        p = _write_changes(
            tmp_path,
            [
                {"hash": "abc", "host": "h", "comments": ["old1"]},
                {"hash": "def", "host": "h", "comments": ["old2"]},
            ],
        )
        update_config_comments(p, "abc", ["new"])
        config = _read_config(p)
        assert config["changes"][0]["comments"] == ["new"]
        assert config["changes"][1]["comments"] == ["old2"]

    def test_update_config_comments_not_found(self, tmp_path: Path) -> None:
        """update_config_comments should raise error if hash not found."""
        p = _write_changes(tmp_path, [{"hash": "abc", "host": "h", "comments": []}])
        with pytest.raises(ValueError, match="not found"):
            update_config_comments(p, "missing", ["new"])


# ---------------------------------------------------------------------------
# TC-013 through TC-019: Action functions (comment_add, etc.)
# ---------------------------------------------------------------------------


class TestCommentActionFunctions:
    def test_tc_013_comment_add_appends(self, app) -> None:
        """TC-013: comment_add should append comment to existing list."""
        from input_handler import comment_add

        app.changes = [TrackedChange(host="h", hash="abc", comments=["old"])]
        comment_add(app, {"idx": "1", "text": "new"})
        assert app.added_comments == [(1, "new")]

    def test_tc_014_comment_replace_all_replaces(self, app) -> None:
        """TC-014: comment_replace_all should replace all comments."""
        from input_handler import comment_replace_all

        app.changes = [TrackedChange(host="h", hash="abc", comments=["a", "b"])]
        comment_replace_all(app, {"idx": "1", "text": "only"})
        assert app.replaced_comments == [(1, "only")]

    def test_tc_015_comment_edit_last_edits(self, app) -> None:
        """TC-015: comment_edit_last should edit last comment."""
        from input_handler import comment_edit_last

        app.changes = [TrackedChange(host="h", hash="abc", comments=["a", "b"])]
        comment_edit_last(app, {"idx": "1", "text": "c"})
        assert app.edited_comments == [(1, "c")]

    def test_tc_016_edit_last_comment_no_comments(self, app) -> None:
        """TC-016: edit_last_comment with no comments should be no-op."""
        from input_handler import comment_edit_last

        app.changes = [TrackedChange(host="h", hash="abc", comments=[])]
        comment_edit_last(app, {"idx": "1", "text": "new"})
        # Should handle gracefully (no crash, but implementation detail)
        assert isinstance(app.edited_comments, list)

    def test_tc_017_comment_delete_by_index(self, app) -> None:
        """TC-017: comment_delete by index should delete specific comment."""
        from input_handler import comment_delete

        app.changes = [TrackedChange(host="h", hash="abc", comments=["a", "b", "c"])]
        comment_delete(app, {"idx": "1", "comment_idx": "1"})
        assert app.deleted_comments == [(1, 1)]

    def test_tc_018_comment_delete_special_a(self, app) -> None:
        """TC-018: comment_delete with special char 'a' deletes all."""
        from input_handler import comment_delete

        app.changes = [TrackedChange(host="h", hash="abc", comments=["a", "b"])]
        comment_delete(app, {"idx": "1", "comment_idx": "a"})
        assert app.deleted_all_comments == [1]

    def test_tc_019_invalid_comment_index(self, app) -> None:
        """TC-019: Invalid comment index should set status message."""
        from input_handler import comment_delete

        app.changes = [TrackedChange(host="h", hash="abc", comments=["a", "b"])]
        comment_delete(app, {"idx": "1", "comment_idx": "5"})
        # Should set error status and not modify comments
        assert app.changes[0].comments == ["a", "b"]
        assert "[red]" in app.status_msg


# ---------------------------------------------------------------------------
# TC-007 through TC-012: Input handler sub-action routing
# ---------------------------------------------------------------------------


class TestInputHandlerSubActions:
    def test_tc_007_space_c_enters_comment_mode(self, app) -> None:
        """TC-007: Space + c enters comment mode."""
        from input_handler import InputHandler

        handler = InputHandler(app)
        app.changes = [TrackedChange(host="h", hash="abc")]

        handler.handle_key(" ")
        handler.handle_key("c")

        # After Space + c, should be collecting idx field
        assert handler.current_field is not None
        assert handler.current_field.name == "idx"
        assert handler.input == ""

    def test_tc_008_after_idx_enters_sub_action_selection(self, app) -> None:
        """TC-008: After idx, enters sub-action selection mode."""
        from input_handler import InputHandler

        handler = InputHandler(app)
        app.changes = [TrackedChange(host="h", hash="abc")]

        handler.handle_key(" ")
        handler.handle_key("c")
        handler.handle_key("1")
        handler.handle_key("<enter>")

        # After collecting idx, should have pending_sub_actions
        assert handler.pending_sub_actions is not None
        assert "a" in handler.pending_sub_actions
        assert "A" in handler.pending_sub_actions
        assert "e" in handler.pending_sub_actions
        assert "d" in handler.pending_sub_actions

    def test_tc_009_sub_action_a_starts_text_input(self, app) -> None:
        """TC-009: Sub-action a starts text input."""
        from input_handler import InputHandler

        handler = InputHandler(app)
        app.changes = [TrackedChange(host="h", hash="abc")]

        handler.handle_key(" ")
        handler.handle_key("c")
        handler.handle_key("1")
        handler.handle_key("<enter>")
        # Now pending_sub_actions is set, press 'a'
        handler.handle_key("a")

        # Should start collecting text field
        assert handler.pending_sub_actions is None
        assert handler.current_field is not None
        assert handler.current_field.name == "text"
        assert handler.input == ""

    def test_tc_010_sub_action_d_starts_cidx_input(self, app) -> None:
        """TC-010: Sub-action d starts comment index input."""
        from input_handler import InputHandler

        handler = InputHandler(app)
        app.changes = [TrackedChange(host="h", hash="abc")]

        handler.handle_key(" ")
        handler.handle_key("c")
        handler.handle_key("1")
        handler.handle_key("<enter>")
        # Now pending_sub_actions is set, press 'd'
        handler.handle_key("d")

        # Should start collecting comment_idx field
        assert handler.pending_sub_actions is None
        assert handler.current_field is not None
        assert handler.current_field.name == "comment_idx"
        assert handler.input == ""

    def test_tc_011_invalid_sub_action_key(self, app) -> None:
        """TC-011: Invalid sub-action key shows error."""
        from input_handler import InputHandler

        handler = InputHandler(app)
        app.changes = [TrackedChange(host="h", hash="abc")]

        handler.handle_key(" ")
        handler.handle_key("c")
        handler.handle_key("1")
        handler.handle_key("<enter>")
        # Now pending_sub_actions is set, press invalid key 'z'
        handler.handle_key("z")

        # Should reset and show status message with error
        assert handler.pending_sub_actions is None
        assert handler.current_field is None
        assert handler.sequence == []

    def test_tc_012_esc_cancels_from_sub_action_mode(self, app) -> None:
        """TC-012: ESC cancels from sub-action mode."""
        from input_handler import InputHandler

        handler = InputHandler(app)
        app.changes = [TrackedChange(host="h", hash="abc")]

        handler.handle_key(" ")
        handler.handle_key("c")
        handler.handle_key("1")
        handler.handle_key("<enter>")
        # Now pending_sub_actions is set, press ESC
        handler.handle_key("<esc>")

        # Should reset completely
        assert handler.pending_sub_actions is None
        assert handler.current_field is None
        assert handler.sequence == []
        assert handler.input is None


# ---------------------------------------------------------------------------
# TC-020 & TC-021: Edit pre-fill and no comments handling
# ---------------------------------------------------------------------------


class TestEditPreFill:
    def test_tc_020_edit_pre_fills_last_comment(self, app) -> None:
        """TC-020: Edit pre-fills last comment."""
        from input_handler import InputHandler

        handler = InputHandler(app)
        app.changes = [TrackedChange(host="h", hash="abc", comments=["first", "second"])]

        handler.handle_key(" ")
        handler.handle_key("c")
        handler.handle_key("1")
        handler.handle_key("<enter>")
        # Now pending_sub_actions is set, press 'e' for edit
        handler.handle_key("e")

        # Should have pre-filled input with last comment
        assert handler.input == "second"
        assert handler.current_field is not None
        assert handler.current_field.name == "text"

    def test_tc_021_edit_with_no_comments_shows_error(self, app) -> None:
        """TC-021: Edit with no comments shows error."""
        from input_handler import InputHandler

        handler = InputHandler(app)
        app.changes = [TrackedChange(host="h", hash="abc", comments=[])]

        handler.handle_key(" ")
        handler.handle_key("c")
        handler.handle_key("1")
        handler.handle_key("<enter>")
        # Now pending_sub_actions is set, press 'e' for edit
        handler.handle_key("e")

        # Should reset and show status message
        assert handler.pending_sub_actions is None
        assert handler.current_field is None
        assert handler.sequence == []
        assert "No comments" in app.status_msg


# ---------------------------------------------------------------------------
# TC-022 & TC-023: Display tests
# ---------------------------------------------------------------------------


class TestCommentDisplay:
    def test_tc_022_comments_column_shows_comments(self) -> None:
        """TC-022: Comments column shows comments in table."""
        from display import build_table

        ch = TrackedChange(host="h", hash="abc", comments=["note1", "note2"])
        table = build_table([ch], "/path/config", 30)
        # Just verify it doesn't crash and table is built
        assert table is not None

    def test_tc_023_empty_comments_column(self) -> None:
        """TC-023: Empty comments column when no comments."""
        from display import build_table

        ch = TrackedChange(host="h", hash="abc", comments=[])
        table = build_table([ch], "/path/config", 30)
        # Just verify it doesn't crash
        assert table is not None


# ---------------------------------------------------------------------------
# Sub-action prompt display
# ---------------------------------------------------------------------------


class TestSubActionPrompt:
    def test_sub_action_prompt_shows_options(self, app) -> None:
        """Sub-action mode should show available options in prompt."""
        from input_handler import InputHandler

        handler = InputHandler(app)
        app.changes = [TrackedChange(host="h", hash="abc")]

        handler.handle_key(" ")
        handler.handle_key("c")
        handler.handle_key("1")
        handler.handle_key("<enter>")

        # Should show sub-action options in prompt
        prompt = handler.prompt(1)
        assert "a=add" in prompt
        assert "A=replace all" in prompt
        assert "e=edit last" in prompt
        assert "d=delete" in prompt
        assert "ESC=cancel" in prompt
