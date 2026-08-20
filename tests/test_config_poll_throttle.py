"""Config-poll throttling — reload_config must not run on every render tick.

The main loop ticks at ui_refresh_rate (default 20 Hz). Polling the config /
changes files (and the save calls inside reload_config) on every tick is the
idle-CPU regression this guards against: it should happen at most once per
CONFIG_POLL_INTERVAL_SEC.
"""

from __future__ import annotations

from unittest.mock import MagicMock


def test_poll_is_throttled_below_interval(app):
    app.reload_config = MagicMock(return_value=False)
    app.seconds_since_config_poll = 0.0

    ticks = int(app.CONFIG_POLL_INTERVAL_SEC / 0.05) - 1
    for _ in range(ticks):
        assert app._poll_config_if_due(0.05) is False

    app.reload_config.assert_not_called()


def test_poll_fires_once_interval_elapsed(app):
    app.reload_config = MagicMock(return_value=True)
    app.seconds_since_config_poll = 0.0

    result = app._poll_config_if_due(app.CONFIG_POLL_INTERVAL_SEC)

    assert result is True
    app.reload_config.assert_called_once()


def test_poll_resets_accumulator_after_firing(app):
    app.reload_config = MagicMock(return_value=False)
    app.seconds_since_config_poll = 0.0

    app._poll_config_if_due(app.CONFIG_POLL_INTERVAL_SEC)
    assert app.seconds_since_config_poll == 0.0

    # right after firing it must throttle again
    app._poll_config_if_due(0.05)
    app.reload_config.assert_called_once()
