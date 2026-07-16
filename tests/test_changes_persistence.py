"""TC-001..006 — Changes persistence (data integrity)."""

from __future__ import annotations

import json
import os

import pytest

from gcd.core.changes import Changes
from gcd.core.models import TrackedChange


def _write_changes(path, entries):
    path.write_text(json.dumps(entries, indent=2) + "\n")


def _bump_mtime(path):
    """Force a distinct mtime regardless of filesystem timestamp resolution."""
    future = os.stat(path).st_mtime + 10
    os.utime(path, (future, future))


def test_add_and_save_round_trips(tmp_path):
    # TC-001
    path = tmp_path / "changes.json"
    store = Changes(path)
    store.append(TrackedChange(number=123, instance="prod"))

    assert store.save_changes() is True

    reloaded = Changes(path)
    ch = reloaded.by_id(TrackedChange(number=123, instance="prod").id)
    assert ch is not None
    assert ch.number == 123
    assert ch.instance == "prod"


def test_save_is_noop_when_nothing_modified(tmp_path):
    # TC-002
    path = tmp_path / "changes.json"
    _write_changes(path, [{"number": 1, "instance": "prod"}])
    store = Changes(path)

    assert store.save_changes() is False


def test_save_persists_when_dirty(tmp_path):
    # TC-003
    path = tmp_path / "changes.json"
    _write_changes(path, [{"number": 7, "instance": "prod"}])
    store = Changes(path)

    ch = store.get_all()[0]
    ch.waiting = True  # tracked field -> marks modified

    assert store.save_changes() is True
    assert Changes(path).get_all()[0].waiting is True


def test_external_edit_is_detected(tmp_path):
    # TC-004
    path = tmp_path / "changes.json"
    store = Changes(path)
    assert store.is_file_changed() is False

    _write_changes(path, [{"number": 9, "instance": "prod"}])
    _bump_mtime(path)

    assert store.is_file_changed() is True


def test_conflicting_external_edit_raises(tmp_path):
    # TC-005
    path = tmp_path / "changes.json"
    _write_changes(path, [{"number": 1, "instance": "prod"}])
    store = Changes(path)

    store.get_all()[0].waiting = True  # local change -> dirty

    _write_changes(path, [{"number": 1, "instance": "prod", "comments": ["external"]}])
    _bump_mtime(path)

    with pytest.raises(RuntimeError):
        store.save_changes()


def test_load_rejects_non_list_root(tmp_path):
    # TC-006
    path = tmp_path / "changes.json"
    path.write_text(json.dumps({"not": "a list"}))

    with pytest.raises(ValueError):
        Changes(path)
