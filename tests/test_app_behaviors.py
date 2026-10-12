"""TC-101..116 — core behaviour driven through App / AppContext.

SSH is the ``fake_gerrit`` spy; assertions are on Changes/TrackedChange state
and on which gerrit_comm methods were invoked. Rendering is never touched.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from helpers import add, idx

from gcd.core.models import ApprovalEntry, ChangeIdentifier
from gcd.plugins.neo_comment_errors import CommentCatcher
from gcd.tui.app import _store_result

COMMENT_CATCHER_CONFIG = {
    "start_gate_message": "gate started",
    "start_check_message": "check started",
    "finish_messages": ["finished"],
    "buildset_link_prefix": "buildset",
    "job_line_prefix": "job",
    "success_labels": ["SUCCESS"],
    "failure_labels": ["FAILURE"],
}


def install_comment_catcher(app, *, initialize: bool) -> CommentCatcher:
    plugin = CommentCatcher(app, "prod", COMMENT_CATCHER_CONFIG)
    app.plugin_manager.plugins_per_instance["prod"] = [plugin]
    if initialize:
        plugin.on_init()
    return plugin

# --- adding changes ---


def test_add_change_appends_to_store(app):
    # TC-101
    before = app.changes.count()
    app.add_change(456, "prod")

    assert app.changes.count() == before + 1
    assert app.changes.by_id(ChangeIdentifier(456, "prod")) is not None
    assert app.status_msg  # a status message was set


def test_add_change_emits_tracked_change(app):
    app.plugin_manager.emit = MagicMock()

    app.add_change(456, "prod")

    change = app.changes.by_id(ChangeIdentifier(456, "prod"))
    assert change is not None
    event, instance, emitted_change = app.plugin_manager.emit.call_args.args
    assert (event, instance) == ("new_change", "prod")
    assert emitted_change is change


def test_fetch_open_changes_emits_tracked_change(app):
    app.plugin_manager.emit = MagicMock()
    app.gerrit_comm.open_changes = [{"number": 789, "currentPatchSet": {}}]
    instance = app.config.get_instance_by_name("prod")
    assert instance is not None

    assert app._fetch_open_changes_from_instance(instance) == 1

    change = app.changes.by_id(ChangeIdentifier(789, "prod"))
    assert change is not None
    event, instance, emitted_change = app.plugin_manager.emit.call_args.args
    assert (event, instance) == ("new_change", "prod")
    assert emitted_change is change


def test_fetch_open_changes_handles_approvals_after_change_is_available(app):
    install_comment_catcher(app, initialize=True)
    app.gerrit_comm.comments_response = [{"message": "gate started https://ci.example/1"}]
    app.gerrit_comm.open_changes = [
        {
            "number": 789,
            "currentPatchSet": {
                "revision": "abc123",
                "number": 1,
                "approvals": [{"type": "Verified", "value": "+1", "by": {"name": "CI"}}],
            },
        }
    ]
    instance = app.config.get_instance_by_name("prod")
    assert instance is not None

    assert app._fetch_open_changes_from_instance(instance) == 1

    change = app.changes.by_id(ChangeIdentifier(789, "prod"))
    assert change is not None
    assert change.comments == ["Gate started at https://ci.example/1"]


def test_run_initializes_plugins_before_querying_changes(app, monkeypatch):
    install_comment_catcher(app, initialize=False)
    change = add(app, 123)
    app.gerrit_comm.query_response = {
        "number": 123,
        "currentPatchSet": {
            "revision": "abc123",
            "number": 1,
            "approvals": [{"type": "Verified", "value": "+1", "by": {"name": "CI"}}],
        },
    }
    app.gerrit_comm.comments_response = [{"message": "gate started https://ci.example/1"}]
    app.running = False
    monkeypatch.setattr("gcd.tui.app.Thread", MagicMock())
    monkeypatch.setattr("gcd.tui.app.Live", MagicMock())

    app.run()

    assert change.comments == ["Gate started at https://ci.example/1"]


@pytest.mark.parametrize("number", [None, "789", True, 0, -1])
def test_fetch_open_changes_ignores_invalid_change_numbers(app, number):
    app.plugin_manager.emit = MagicMock()
    app.gerrit_comm.open_changes = [{"number": number, "currentPatchSet": {}}]
    instance = app.config.get_instance_by_name("prod")
    assert instance is not None

    assert app._fetch_open_changes_from_instance(instance) == 0
    assert app.changes.count() == 0
    app.plugin_manager.emit.assert_not_called()


# --- toggles ---


def test_toggle_waiting_flips_flag(app):
    # TC-102
    ch = add(app, 1)
    app.toggle_waiting(idx(1))
    assert ch.waiting is True
    app.toggle_waiting(idx(1))
    assert ch.waiting is False


def test_toggle_deleted_and_disabled_flip_flags(app):
    # TC-103
    ch = add(app, 1)
    app.toggle_deleted(idx(1))
    assert ch.deleted is True

    app.toggle_disabled(idx(1))
    assert ch.disabled is True


# --- comments ---


def test_add_comment_appends(app):
    # TC-104
    ch = add(app, 1)
    app.add_comment(idx(1), "hello")
    assert ch.comments == ["hello"]


def test_edit_last_comment_replaces_last(app):
    # TC-105
    ch = add(app, 1, comments=["first", "second"])
    app.edit_last_comment(idx(1), "new")
    assert ch.comments == ["first", "new"]


def test_delete_comment_removes_addressed(app):
    # TC-106
    ch = add(app, 1, comments=["a", "b", "c"])
    app.delete_comment(idx(1), idx(2))
    assert ch.comments == ["a", "c"]


def test_delete_comment_all_tags_removes_tags(app):
    ch = add(app, 1, comments=["note", "#tag", "follow-up", "#urgent"])

    app.delete_comment_all_tags(idx(1))

    assert ch.comments == ["note", "follow-up"]


def test_fetch_comments_returns_error_for_missing_instance(app):
    ch = add(app, 1, instance="missing")

    result = app.fetch_comments_from_change(ch)

    assert result == {"error": "Instance not found"}
    assert "cannot find instance 'missing'" in app.status_msg


# --- delete / restore lifecycle ---


def test_delete_all_submitted_marks_only_submitted(app):
    # TC-107
    submitted = add(app, 1, submitted=True)
    running = add(app, 2)

    app.delete_all_submitted()

    assert submitted.deleted is True
    assert running.deleted is False


def test_restore_all_clears_deleted(app):
    # TC-108
    a = add(app, 1, deleted=True)
    b = add(app, 2, deleted=True)

    app.restore_all()

    assert a.deleted is False
    assert b.deleted is False


# --- review guards & success ---


def test_review_automerge_guard_no_revision(app):
    # TC-109
    add(app, 1)  # no current_revision
    app.review_set_automerge(idx(1))

    assert not app.gerrit_comm.called("review_set_automerge")
    assert app.status_msg  # feedback given to the user


def test_review_automerge_guard_already_submitted(app):
    # TC-110
    add(app, 1, current_revision="abc", submitted=True)
    app.review_set_automerge(idx(1))

    assert not app.gerrit_comm.called("review_set_automerge")
    assert "already submitted" in app.status_msg


def test_review_automerge_guard_label_present(app):
    # TC-111
    add(app, 1, current_revision="abc", approvals=[ApprovalEntry("Automerge", "1", "bot")])
    app.review_set_automerge(idx(1))

    assert not app.gerrit_comm.called("review_set_automerge")
    assert "already exists" in app.status_msg


def test_review_automerge_success_calls_gerrit(app):
    # TC-112
    app._start_refresh = MagicMock()
    add(app, 1, current_revision="abc")

    app.review_set_automerge(idx(1))

    assert ("review_set_automerge", (app.config.default_instance, "abc")) in app.gerrit_comm.calls
    app._start_refresh.assert_called_once()


def test_review_failure_surfaces_error_and_no_refresh(app):
    # TC-113
    app._start_refresh = MagicMock()
    app.gerrit_comm.review_response = {"error": "boom"}
    add(app, 1, current_revision="abc")

    app.review_set_automerge(idx(1))

    assert "failed" in app.status_msg
    app._start_refresh.assert_not_called()


def test_review_message_publishes_without_starting_refresh(app):
    app._start_refresh = MagicMock()
    add(app, 101, current_revision="deadbeef")

    app.review_message(idx(1), "Looks good")

    assert ("review_message", (app.config.default_instance, "deadbeef", "Looks good")) in app.gerrit_comm.calls
    assert "1 change" in app.status_msg
    assert "green" in app.status_msg
    app._start_refresh.assert_not_called()


def test_review_message_publishes_to_multiple_instances(app):
    add(app, 101, current_revision="prod-revision")
    add(app, 202, instance="staging", current_revision="staging-revision")

    app.review_message(idx(1, 2), "Looks good")

    assert app.gerrit_comm.calls == [
        ("review_message", (app.config.default_instance, "prod-revision", "Looks good")),
        ("review_message", (app.config.instances[1], "staging-revision", "Looks good")),
    ]
    assert "2 changes" in app.status_msg
    assert "green" in app.status_msg


@pytest.mark.parametrize("message", ["", "   "])
def test_review_message_rejects_empty_or_whitespace_only_text(app, message):
    add(app, 101, current_revision="deadbeef")

    app.review_message(idx(1), message)

    assert not app.gerrit_comm.called("review_message")
    assert "empty" in app.status_msg.lower()
    assert "red" in app.status_msg


def test_review_message_reports_missing_revision_without_blocking_valid_change(app):
    add(app, 101)
    add(app, 202, current_revision="cafebabe")

    app.review_message(idx(1, 2), "Please take another look")

    assert app.gerrit_comm.calls == [
        ("review_message", (app.config.default_instance, "cafebabe", "Please take another look"))
    ]
    assert "1 of 2" in app.status_msg
    assert "#101" in app.status_msg
    assert "yellow" in app.status_msg


def test_review_message_reports_gerrit_failure_without_blocking_later_change(app):
    add(app, 101, current_revision="bad")
    add(app, 202, current_revision="good")
    responses = iter([{"error": "permission denied"}, {"success": True}])

    def review_message(instance, revision, message):
        app.gerrit_comm._record("review_message", instance, revision, message)
        return next(responses)

    app.gerrit_comm.review_message = review_message

    app.review_message(idx(1, 2), "Please take another look")

    assert [args[1] for name, args in app.gerrit_comm.calls if name == "review_message"] == ["bad", "good"]
    assert "1 of 2" in app.status_msg
    assert "#101" in app.status_msg
    assert "permission denied" in app.status_msg
    assert "yellow" in app.status_msg


def test_review_message_reports_unknown_instance_without_blocking_valid_change(app):
    add(app, 101, instance="retired", current_revision="unknown")
    add(app, 202, current_revision="good")

    app.review_message(idx(1, 2), "Please take another look")

    assert app.gerrit_comm.calls == [
        ("review_message", (app.config.default_instance, "good", "Please take another look"))
    ]
    assert "1 of 2" in app.status_msg
    assert "#101" in app.status_msg
    assert "retired" in app.status_msg
    assert "yellow" in app.status_msg


def test_review_message_preserves_no_matching_changes_error(app):
    app.review_message(idx(9), "Looks good")

    assert not app.gerrit_comm.called("review_message")
    assert "No matching changes" in app.status_msg
    assert "red" in app.status_msg


def test_review_message_reports_every_failure_when_nothing_is_published(app):
    add(app, 101)
    add(app, 202, instance="retired", current_revision="unknown")

    app.review_message(idx(1, 2), "Looks good")

    assert not app.gerrit_comm.called("review_message")
    assert "0 of 2" in app.status_msg
    assert "#101" in app.status_msg
    assert "#202" in app.status_msg
    assert "red" in app.status_msg


# --- gerrit JSON -> model mapping ---


def test_store_result_maps_query_dict(app):
    # TC-114
    ch = add(app, 123)
    data = {
        "subject": "Fix the bug",
        "project": "myproj",
        "url": "https://gerrit.example.com/123",
        "currentPatchSet": {
            "revision": "deadbeef",
            "number": 4,
            "approvals": [{"type": "Code-Review", "value": "2", "by": {"name": "Alice"}}],
        },
    }

    _store_result(ch, data, app.cache, app.plugin_manager)

    assert ch.subject == "Fix the bug"
    assert ch.project == "myproj"
    assert ch.url == "https://gerrit.example.com/123"
    assert ch.current_revision == "deadbeef"
    assert ch.current_patchset_number == 4
    assert len(ch.approvals) == 1
    assert ch.approvals[0].label == "Code-Review"
    assert ch.approvals[0].value == "2"
    assert ch.approvals[0].by == "Alice"


def test_store_result_clears_waiting_when_first_approval_arrives(app):
    ch = add(app, 123, waiting=True)
    app.plugin_manager.emit = MagicMock()
    no_approvals = {"currentPatchSet": {"approvals": []}}
    first_approval = {
        "currentPatchSet": {"approvals": [{"type": "Code-Review", "value": "2", "by": {"name": "Alice"}}]}
    }

    _store_result(ch, no_approvals, app.cache, app.plugin_manager)
    _store_result(ch, first_approval, app.cache, app.plugin_manager)

    assert ch.waiting is False
    app.plugin_manager.emit.assert_any_call("status_changed", ch.instance, ch.id, ("waiting", False))


def test_store_result_derives_status_flags(app):
    # TC-115
    abandoned = add(app, 1)
    _store_result(abandoned, {"status": "ABANDONED", "currentPatchSet": {}}, app.cache, app.plugin_manager)
    assert abandoned.abandoned is True

    submitted = add(app, 2)
    _store_result(
        submitted,
        {"currentPatchSet": {"approvals": [{"type": "SUBM", "value": "1", "by": {"name": "x"}}]}},
        app.cache,
        app.plugin_manager,
    )
    assert submitted.submitted is True

    wip = add(app, 3)
    _store_result(wip, {"wip": True, "currentPatchSet": {}}, app.cache, app.plugin_manager)
    assert wip.is_wip is True


def test_store_result_records_error(app):
    # TC-116
    ch = add(app, 1, subject="kept")
    _store_result(ch, {"error": "not found"}, app.cache, app.plugin_manager)

    assert ch.error == "not found"
    assert ch.subject == "kept"  # other fields untouched


def test_last_comment_returns_last_or_none(app):
    # TC-117 — accessor used by the input layer's edit-last prefill
    add(app, 1, comments=["one", "two"])
    add(app, 2)  # no comments

    assert app.last_comment(idx(1)) == "two"
    assert app.last_comment(idx(2)) is None
