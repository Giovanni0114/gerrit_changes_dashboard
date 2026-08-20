"""Rendering refreshes only on demand (auto_refresh disabled).

With Rich's Live auto-refresh thread turned off to save idle CPU, the app must
explicitly force a paint (refresh=True) whenever something changed, and must
notice terminal resizes itself since the thread no longer covers them.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

import gcd.tui.app as app_module


def test_visual_update_forces_refresh_when_needed(app):
    live = MagicMock()
    app.build = MagicMock(return_value="RENDERABLE")
    app.needs_visual_update = True

    app.visual_update_if_needed(live)

    assert live.update.call_args == call("RENDERABLE", refresh=True)
    assert app.needs_visual_update is False


def test_visual_update_is_noop_when_nothing_changed(app):
    live = MagicMock()
    app.build = MagicMock(return_value="RENDERABLE")
    app.needs_visual_update = False

    app.visual_update_if_needed(live)

    live.update.assert_not_called()


def test_resize_flags_a_visual_update(app, monkeypatch):
    monkeypatch.setattr(app_module, "_console", MagicMock(size=(100, 30)))
    app._last_console_size = (80, 24)
    app.needs_visual_update = False

    app._check_terminal_resize()

    assert app.needs_visual_update is True
    assert app._last_console_size == (100, 30)


def test_no_resize_leaves_flag_untouched(app, monkeypatch):
    monkeypatch.setattr(app_module, "_console", MagicMock(size=(80, 24)))
    app._last_console_size = (80, 24)
    app.needs_visual_update = False

    app._check_terminal_resize()

    assert app.needs_visual_update is False
