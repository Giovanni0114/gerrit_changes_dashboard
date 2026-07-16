"""TC-101..116 — core behaviour driven through App / AppContext.

SSH is the ``fake_gerrit`` spy; assertions are on Changes/TrackedChange state
and on which gerrit_comm methods were invoked. Rendering is never touched.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from helpers import add, idx

from gcd.core.models import ApprovalEntry, ChangeIdentifier
from gcd.tui.app import _store_result

# --- adding changes ---


def test_add_change_appends_to_store(app):
    # TC-101
    before = app.changes.count()
    app.add_change(456, "prod")

    assert app.changes.count() == before + 1
    assert app.changes.by_id(ChangeIdentifier(456, "prod")) is not None
    assert app.status_msg  # a status message was set


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
