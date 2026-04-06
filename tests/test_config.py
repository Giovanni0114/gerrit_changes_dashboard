"""Tests for config.py — regression guard for JSON load/save functions."""

import json
from pathlib import Path

import pytest

from config import (
    add_change_to_config,
    bulk_update_config_field,
    load_config,
    remove_changes_from_config,
    update_config_field,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_config(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "approvals.json"
    p.write_text(json.dumps(data, indent=2) + "\n")
    return p


def _read_config(path: Path) -> dict:
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_happy_path(self, tmp_path: Path) -> None:
        p = _write_config(
            tmp_path,
            {
                "interval": 15,
                "default_host": "gerrit.example.com",
                "changes": [
                    {"hash": "abc", "host": "gerrit.example.com"},
                    {"hash": "def", "host": "other.host", "waiting": True, "disabled": True},
                ],
            },
        )
        changes, interval, default_host, _ = load_config(p)
        assert interval == 15
        assert default_host == "gerrit.example.com"
        assert len(changes) == 2
        assert changes[0].hash == "abc"
        assert changes[0].waiting is False
        assert changes[0].disabled is False
        assert changes[1].hash == "def"
        assert changes[1].waiting is True
        assert changes[1].disabled is True

    def test_default_interval_used_when_absent(self, tmp_path: Path) -> None:
        p = _write_config(tmp_path, {"changes": []})
        _, interval, _, _ = load_config(p)
        assert interval == 30

    def test_interval_below_one_raises(self, tmp_path: Path) -> None:
        p = _write_config(tmp_path, {"interval": 0, "changes": []})
        with pytest.raises(ValueError, match="interval"):
            load_config(p)

    def test_missing_host_no_default_raises(self, tmp_path: Path) -> None:
        p = _write_config(tmp_path, {"changes": [{"hash": "abc"}]})
        with pytest.raises(ValueError, match="no host"):
            load_config(p)

    def test_missing_host_falls_back_to_default_host(self, tmp_path: Path) -> None:
        p = _write_config(
            tmp_path,
            {
                "default_host": "fallback.gerrit.com",
                "changes": [{"hash": "abc"}],
            },
        )
        changes, _, _, _ = load_config(p)
        assert changes[0].host == "fallback.gerrit.com"

    def test_no_default_host_returns_none(self, tmp_path: Path) -> None:
        p = _write_config(tmp_path, {"changes": []})
        _, _, default_host, _ = load_config(p)
        assert default_host is None

    def test_empty_changes_list(self, tmp_path: Path) -> None:
        p = _write_config(tmp_path, {"changes": []})
        changes, _, _, _ = load_config(p)
        assert changes == []

    def test_default_port_applied_to_all_changes(self, tmp_path: Path) -> None:
        p = _write_config(
            tmp_path,
            {
                "default_port": 29418,
                "changes": [
                    {"hash": "abc", "host": "h"},
                    {"hash": "def", "host": "h"},
                ],
            },
        )
        changes, _, _, default_port = load_config(p)
        assert default_port == 29418
        assert changes[0].port == 29418
        assert changes[1].port == 29418

    def test_per_change_port_overrides_default(self, tmp_path: Path) -> None:
        p = _write_config(
            tmp_path,
            {
                "default_port": 29418,
                "changes": [
                    {"hash": "abc", "host": "h", "port": 22},
                    {"hash": "def", "host": "h"},
                ],
            },
        )
        changes, _, _, _ = load_config(p)
        assert changes[0].port == 22
        assert changes[1].port == 29418

    def test_no_port_returns_none(self, tmp_path: Path) -> None:
        p = _write_config(tmp_path, {"changes": [{"hash": "abc", "host": "h"}]})
        changes, _, _, default_port = load_config(p)
        assert default_port is None
        assert changes[0].port is None


# ---------------------------------------------------------------------------
# update_config_field
# ---------------------------------------------------------------------------


class TestUpdateConfigField:
    def test_sets_waiting_true(self, tmp_path: Path) -> None:
        p = _write_config(
            tmp_path,
            {"changes": [{"hash": "abc", "host": "h"}]},
        )
        update_config_field(p, "abc", "waiting", True)
        data = _read_config(p)
        assert data["changes"][0]["waiting"] is True

    def test_sets_disabled_false(self, tmp_path: Path) -> None:
        p = _write_config(
            tmp_path,
            {"changes": [{"hash": "abc", "host": "h", "disabled": True}]},
        )
        update_config_field(p, "abc", "disabled", False)
        data = _read_config(p)
        assert data["changes"][0]["disabled"] is False

    def test_non_matching_hash_unchanged(self, tmp_path: Path) -> None:
        p = _write_config(
            tmp_path,
            {"changes": [{"hash": "abc", "host": "h"}, {"hash": "def", "host": "h"}]},
        )
        update_config_field(p, "abc", "waiting", True)
        data = _read_config(p)
        assert "waiting" not in data["changes"][1] or data["changes"][1].get("waiting") is not True

    def test_returns_mtime(self, tmp_path: Path) -> None:
        p = _write_config(tmp_path, {"changes": [{"hash": "abc", "host": "h"}]})
        mtime = update_config_field(p, "abc", "waiting", True)
        assert mtime == p.stat().st_mtime


# ---------------------------------------------------------------------------
# bulk_update_config_field
# ---------------------------------------------------------------------------


class TestBulkUpdateConfigField:
    def test_updates_multiple_entries(self, tmp_path: Path) -> None:
        p = _write_config(
            tmp_path,
            {
                "changes": [
                    {"hash": "a", "host": "h"},
                    {"hash": "b", "host": "h"},
                    {"hash": "c", "host": "h"},
                ]
            },
        )
        bulk_update_config_field(p, {"a": ("waiting", True), "b": ("disabled", True)})
        data = _read_config(p)
        assert data["changes"][0]["waiting"] is True
        assert data["changes"][1]["disabled"] is True
        assert "waiting" not in data["changes"][2]
        assert "disabled" not in data["changes"][2]

    def test_empty_updates_leaves_file_unchanged(self, tmp_path: Path) -> None:
        original = {"changes": [{"hash": "a", "host": "h"}]}
        p = _write_config(tmp_path, original)
        bulk_update_config_field(p, {})
        data = _read_config(p)
        assert data == original

    def test_returns_mtime(self, tmp_path: Path) -> None:
        p = _write_config(tmp_path, {"changes": [{"hash": "a", "host": "h"}]})
        mtime = bulk_update_config_field(p, {"a": ("waiting", True)})
        assert mtime == p.stat().st_mtime


# ---------------------------------------------------------------------------
# add_change_to_config
# ---------------------------------------------------------------------------


class TestAddChangeToConfig:
    def test_appends_new_entry(self, tmp_path: Path) -> None:
        p = _write_config(tmp_path, {"changes": [{"hash": "existing", "host": "h"}]})
        add_change_to_config(p, "newhash", "new.host")
        data = _read_config(p)
        assert len(data["changes"]) == 2
        assert data["changes"][1] == {"hash": "newhash", "host": "new.host"}

    def test_existing_entries_unchanged(self, tmp_path: Path) -> None:
        p = _write_config(tmp_path, {"changes": [{"hash": "abc", "host": "h", "waiting": True}]})
        add_change_to_config(p, "new", "h2")
        data = _read_config(p)
        assert data["changes"][0] == {"hash": "abc", "host": "h", "waiting": True}

    def test_returns_mtime(self, tmp_path: Path) -> None:
        p = _write_config(tmp_path, {"changes": []})
        mtime = add_change_to_config(p, "abc", "h")
        assert mtime == p.stat().st_mtime


# ---------------------------------------------------------------------------
# remove_changes_from_config
# ---------------------------------------------------------------------------


class TestRemoveChangesFromConfig:
    def test_removes_matching_hashes(self, tmp_path: Path) -> None:
        p = _write_config(
            tmp_path,
            {
                "changes": [
                    {"hash": "a", "host": "h"},
                    {"hash": "b", "host": "h"},
                    {"hash": "c", "host": "h"},
                ]
            },
        )
        remove_changes_from_config(p, {"a", "c"})
        data = _read_config(p)
        assert len(data["changes"]) == 1
        assert data["changes"][0]["hash"] == "b"

    def test_empty_set_removes_nothing(self, tmp_path: Path) -> None:
        p = _write_config(tmp_path, {"changes": [{"hash": "a", "host": "h"}]})
        remove_changes_from_config(p, set())
        data = _read_config(p)
        assert len(data["changes"]) == 1

    def test_non_matching_hash_ignored(self, tmp_path: Path) -> None:
        p = _write_config(tmp_path, {"changes": [{"hash": "a", "host": "h"}]})
        remove_changes_from_config(p, {"z"})
        data = _read_config(p)
        assert len(data["changes"]) == 1

    def test_returns_mtime(self, tmp_path: Path) -> None:
        p = _write_config(tmp_path, {"changes": [{"hash": "a", "host": "h"}]})
        mtime = remove_changes_from_config(p, {"a"})
        assert mtime == p.stat().st_mtime
