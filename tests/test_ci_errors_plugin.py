from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from gcd.core.models import AppContext, ApprovalEntry, ChangeIdentifier, TrackedChange
from gcd.core.plugin_manager import PluginManager
from gcd.plugins.ci_errors import CiErrorsPlugin


def make_plugin(ctx: AppContext, config: dict[object, object]) -> CiErrorsPlugin:
    return CiErrorsPlugin(ctx, "prod", config)


@pytest.mark.parametrize(
    "config",
    [
        {},
        {"url": "", "api_key": "key"},
        {"url": "https://ci.example.test", "api_key": ""},
        {"url": 1, "api_key": "key"},
        {"url": "https://ci.example.test", "api_key": 1},
    ],
)
def test_on_init_disables_plugin_with_invalid_connection_config(
    spy_ctx: AppContext, config: dict[object, object]
) -> None:
    plugin = make_plugin(spy_ctx, config)

    plugin.on_init()

    assert not plugin.enabled


def test_on_init_does_not_log_api_key(spy_ctx: AppContext) -> None:
    api_key = "secret-api-key"
    plugin = make_plugin(spy_ctx, {"url": "https://ci.example.test", "api_key": api_key})
    plugin.log = MagicMock()

    plugin.on_init()

    assert plugin.enabled
    assert api_key[:3] not in str(plugin.log.info.call_args)


def test_disabled_plugin_does_not_handle_events(spy_ctx: AppContext, monkeypatch: pytest.MonkeyPatch) -> None:
    change = TrackedChange(number=123, instance="prod", current_patchset_number=4)
    spy_ctx.changes.append(change)
    plugin = make_plugin(spy_ctx, {})
    plugin.log = MagicMock()
    manager = object.__new__(PluginManager)
    post = MagicMock()
    monkeypatch.setattr(requests, "post", post)

    manager._safe_call(plugin, "on_init")
    plugin.log.reset_mock()
    manager._safe_call(plugin, "on_activate", args=[change.id, change])
    manager._safe_call(
        plugin,
        "on_new_approval",
        args=[change.id, ApprovalEntry(label="Verified", value="+1", by="reviewer")],
    )

    assert not plugin.enabled
    post.assert_not_called()
    plugin.log.error.assert_not_called()
    assert change.comments == []
    assert not change.modified


def test_check_ci_errors_adds_completed_error_comment(spy_ctx: AppContext, monkeypatch: pytest.MonkeyPatch) -> None:
    plugin = make_plugin(spy_ctx, {"url": "https://ci.example.test", "api_key": "key"})
    change = TrackedChange(number=123, instance="prod", current_patchset_number=4)
    response = MagicMock()
    response.json.return_value = [
        {
            "job_status": "COMPLETED",
            "categories": [{"category": "error", "err_type": "build", "job_link": "https://job.example.test"}],
        }
    ]
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: response)

    plugin._check_ci_errors(change)

    assert change.comments == [
        "VERIFICATION: COMPLETED: 1, RUNNING: 0, UNKNOWN: 0",
        "(build) error - https://job.example.test",
    ]
    assert change.modified


def test_check_ci_errors_ignores_non_list_response(spy_ctx: AppContext, monkeypatch: pytest.MonkeyPatch) -> None:
    plugin = make_plugin(spy_ctx, {"url": "https://ci.example.test", "api_key": "key"})
    change = TrackedChange(number=123, instance="prod", current_patchset_number=4)
    response = MagicMock()
    response.json.return_value = {"job_status": "COMPLETED"}
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: response)

    plugin._check_ci_errors(change)

    assert change.comments == []
    assert not change.modified


def test_ask_for_errors_handles_http_error_without_response(
    spy_ctx: AppContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin = make_plugin(spy_ctx, {"url": "https://ci.example.test", "api_key": "key"})
    plugin.log = MagicMock()
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: (_ for _ in ()).throw(requests.HTTPError()))

    assert plugin._ask_for_errors(123, 4) is None
    plugin.log.error.assert_called_once_with("_ask_for_errors: HTTP unknown for change 123")


def test_ask_for_errors_skips_malformed_response_records(spy_ctx: AppContext, monkeypatch: pytest.MonkeyPatch) -> None:
    plugin = make_plugin(spy_ctx, {"url": "https://ci.example.test", "api_key": "key"})
    response = MagicMock()
    response.json.return_value = [
        "invalid entry",
        {"job_status": "COMPLETED", "categories": {"category": "error"}},
        {"job_status": "COMPLETED", "categories": ["invalid category", {"category": "error", "err_type": 1}]},
        {"job_status": "RUNNING"},
    ]
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: response)

    statuses = plugin._ask_for_errors(123, 4)

    assert statuses is not None
    assert statuses.completed == 2
    assert statuses.running == 1
    assert statuses.unknown == 0
    assert statuses.comments == ["(<?>) error - <?>"]


def test_ask_for_errors_logs_unknown_status(spy_ctx: AppContext, monkeypatch: pytest.MonkeyPatch) -> None:
    plugin = make_plugin(spy_ctx, {"url": "https://ci.example.test", "api_key": "key"})
    plugin.log = MagicMock()
    response = MagicMock()
    response.json.return_value = [{"job_status": "UNRECOGNIZED"}]
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: response)

    statuses = plugin._ask_for_errors(123, 4)

    assert statuses is not None
    assert statuses.unknown == 1
    plugin.log.error.assert_called_once()


def test_verified_approval_checks_the_tracked_change(spy_ctx: AppContext) -> None:
    change = TrackedChange(number=123, instance="prod")
    spy_ctx.changes.append(change)
    plugin = make_plugin(spy_ctx, {"url": "https://ci.example.test", "api_key": "key"})

    with patch.object(plugin, "_check_ci_errors") as check_ci_errors:
        plugin.on_new_approval(change.id, ApprovalEntry(label="Verified", value="+1", by="reviewer"))

    check_ci_errors.assert_called_once_with(change)


@pytest.mark.parametrize(
    ("change_id", "approval"),
    [
        (ChangeIdentifier(999, "prod"), ApprovalEntry(label="Verified", value="+1", by="reviewer")),
        (ChangeIdentifier(123, "prod"), ApprovalEntry(label="Code-Review", value="+1", by="reviewer")),
    ],
)
def test_nonmatching_approval_does_not_check_ci_errors(
    spy_ctx: AppContext, change_id: ChangeIdentifier, approval: ApprovalEntry
) -> None:
    change = TrackedChange(number=123, instance="prod")
    spy_ctx.changes.append(change)
    plugin = make_plugin(spy_ctx, {"url": "https://ci.example.test", "api_key": "key"})

    with patch.object(plugin, "_check_ci_errors") as check_ci_errors:
        plugin.on_new_approval(change_id, approval)

    check_ci_errors.assert_not_called()
