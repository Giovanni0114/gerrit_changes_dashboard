"""TC-201..205 — user-facing behaviour: key sequences dispatch the right action.

Drives the real ``InputHandler`` against a ``SpyAppContext`` (see conftest): a
protocol-generated spy that records dispatched calls while reusing a real
``AppConfig`` so instance resolution stays meaningful. This isolates the input
layer from ``App`` construction entirely.
"""

from __future__ import annotations

from helpers import idx

from gcd.core.models import AppContext, TrackedChange


def _send(handler, *keys):
    for key in keys:
        handler.handle_key(key)


def test_spy_conforms_to_appcontext_protocol(spy_ctx):
    # The spy is a structural stand-in for the real boundary.
    assert isinstance(spy_ctx, AppContext)


def test_add_change_sequence_dispatches_add_change(input_handler, spy_ctx):
    # TC-201
    _send(input_handler, "a", "4", "2", "<enter>", "<enter>")

    spy_ctx.add_change.assert_called_once_with(42, spy_ctx.config.default_instance.name)


def test_toggle_sequence_dispatches_toggle_with_index(input_handler, spy_ctx):
    # TC-202
    _send(input_handler, " ", "w", "1", "<enter>")

    spy_ctx.toggle_waiting.assert_called_once_with(idx(1))


def test_comment_sequence_dispatches_add_comment(input_handler, spy_ctx):
    # TC-203
    _send(input_handler, " ", "c", "a", "1", "<enter>", "h", "i", "<enter>")

    spy_ctx.add_comment.assert_called_once_with(idx(1), "hi")


def test_publish_message_sequence_dispatches_selected_changes_and_message(input_handler, spy_ctx):
    _send(
        input_handler,
        " ",
        "r",
        "p",
        "1",
        ",",
        "3",
        "<enter>",
        "L",
        "o",
        "o",
        "k",
        "s",
        " ",
        "g",
        "o",
        "o",
        "d",
        "<enter>",
    )

    spy_ctx.review_message.assert_called_once_with(idx(1, 3), "Looks good")


def test_publish_message_tab_does_not_complete_local_comment_tags(input_handler, spy_ctx):
    spy_ctx.changes.append(TrackedChange(1, "prod", comments=["#urgent"]))

    _send(input_handler, " ", "r", "p", "1", "<enter>", "#", "u", "<tab>", "<enter>")

    spy_ctx.review_message.assert_called_once_with(idx(1), "#u")


def test_esc_cancels_while_entering_review_message(input_handler, spy_ctx):
    _send(input_handler, " ", "r", "p", "1", "<enter>", "n", "o", "<esc>")

    spy_ctx.review_message.assert_not_called()
    assert input_handler.sequence == []
    assert input_handler.current_action is None


def test_wildcard_index_produces_wildcard_index(input_handler, spy_ctx):
    # TC-204
    _send(input_handler, " ", "w", "a")

    spy_ctx.toggle_waiting.assert_called_once_with(idx(wildcard=True))


def test_esc_aborts_sequence(input_handler, spy_ctx):
    # TC-205
    _send(input_handler, " ", "w", "<esc>")

    spy_ctx.toggle_waiting.assert_not_called()
    assert input_handler.sequence == []
    assert input_handler.current_action is None
