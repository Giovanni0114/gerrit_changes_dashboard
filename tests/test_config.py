"""Tests for config.py — regression guard for JSON load/save functions."""

import json
import subprocess
import tomllib
from pathlib import Path

import pytest

from config import (
    add_change_to_config,
    bulk_update_config_field,
    load_changes,
    load_toml_config,
    remove_changes_from_config,
    resolve_editor,
    resolve_email,
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


# ---------------------------------------------------------------------------
# resolve_email
# ---------------------------------------------------------------------------


class TestResolveEmail:
    def test_email_from_config(self) -> None:
        """TC-001: Config email takes priority over git fallback."""
        assert resolve_email("alice@example.com") == "alice@example.com"

    def test_email_from_git_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """TC-002: When config email is None, falls back to git config."""

        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *args, **kwargs: type("Result", (), {"returncode": 0, "stdout": "bob@example.com\n"})(),
        )
        assert resolve_email(None) == "bob@example.com"

    def test_no_email_available_subprocess_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """TC-003: When config email is None and git fails, returns None."""

        def _fail(*args, **kwargs):
            raise FileNotFoundError("git not found")

        monkeypatch.setattr(subprocess, "run", _fail)
        assert resolve_email(None) is None

    def test_no_email_available_nonzero_exit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """TC-003 variant: git returns non-zero exit code."""

        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *args, **kwargs: type("Result", (), {"returncode": 1, "stdout": ""})(),
        )
        assert resolve_email(None) is None


# ---------------------------------------------------------------------------
# load_toml_config
# ---------------------------------------------------------------------------


def _write_toml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(content, encoding="utf-8")
    return p


class TestLoadTomlConfig:
    def test_happy_path(self, tmp_path: Path) -> None:
        p = _write_toml(
            tmp_path,
            "\n".join(["[config]", "interval = 15", 'default_host = "gerrit.example.com"', "default_port = 29418"]),
        )
        cfg = load_toml_config(p)
        assert cfg.interval == 15
        assert cfg.default_host == "gerrit.example.com"
        assert cfg.default_port == 29418
        assert cfg.email is None
        assert cfg.changes_file == tmp_path / "approvals.json"

    def test_defaults_when_keys_absent(self, tmp_path: Path) -> None:
        p = _write_toml(tmp_path, "[config]")
        cfg = load_toml_config(p)
        assert cfg.interval == 30
        assert cfg.default_port == 22
        assert cfg.default_host is None
        assert cfg.email is None
        assert cfg.changes_file == (tmp_path / "approvals.json").resolve()

    def test_custom_changes_file(self, tmp_path: Path) -> None:
        p = _write_toml(tmp_path, '[config]\nchanges_file = "my_changes.json"\n')
        cfg = load_toml_config(p)
        assert cfg.changes_file == (tmp_path / "my_changes.json").resolve()

    def test_email_field(self, tmp_path: Path) -> None:
        p = _write_toml(tmp_path, '[config]\ndefault_email = "alice@example.com"\n')
        cfg = load_toml_config(p)
        assert cfg.email == "alice@example.com"

    def test_interval_below_one_raises(self, tmp_path: Path) -> None:
        p = _write_toml(tmp_path, "[config]\ninterval = 0\n")
        with pytest.raises(ValueError, match="interval"):
            load_toml_config(p)

    def test_invalid_toml_raises(self, tmp_path: Path) -> None:
        p = _write_toml(tmp_path, "interval = [unclosed\n")
        with pytest.raises(tomllib.TOMLDecodeError):
            load_toml_config(p)


# ---------------------------------------------------------------------------
# load_changes
# ---------------------------------------------------------------------------


class TestLoadChanges:
    def test_happy_path(self, tmp_path: Path) -> None:
        p = _write_config(
            tmp_path,
            {
                "changes": [
                    {"hash": "abc", "host": "gerrit.example.com"},
                    {"hash": "def", "host": "other.host", "waiting": True, "disabled": True},
                ]
            },
        )
        changes = load_changes(p, default_host=None, default_port=22)
        assert len(changes) == 2
        assert changes[0].hash == "abc"
        assert changes[0].host == "gerrit.example.com"
        assert changes[0].waiting is False
        assert changes[1].hash == "def"
        assert changes[1].waiting is True
        assert changes[1].disabled is True

    def test_empty_changes_valid(self, tmp_path: Path) -> None:
        p = _write_config(tmp_path, {"changes": []})
        changes = load_changes(p, default_host=None, default_port=None)
        assert changes == []

    def test_host_falls_back_to_default(self, tmp_path: Path) -> None:
        p = _write_config(tmp_path, {"changes": [{"hash": "abc"}]})
        changes = load_changes(p, default_host="fallback.gerrit.com", default_port=22)
        assert changes[0].host == "fallback.gerrit.com"

    def test_missing_host_no_default_raises(self, tmp_path: Path) -> None:
        p = _write_config(tmp_path, {"changes": [{"hash": "abc"}]})
        with pytest.raises(ValueError, match="no host"):
            load_changes(p, default_host=None, default_port=None)

    def test_default_port_applied(self, tmp_path: Path) -> None:
        p = _write_config(tmp_path, {"changes": [{"hash": "abc", "host": "h"}]})
        changes = load_changes(p, default_host=None, default_port=29418)
        assert changes[0].port == 29418

    def test_per_change_port_overrides_default(self, tmp_path: Path) -> None:
        p = _write_config(tmp_path, {"changes": [{"hash": "abc", "host": "h", "port": 22}]})
        changes = load_changes(p, default_host=None, default_port=29418)
        assert changes[0].port == 22

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "approvals.json"
        p.write_text("not json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            load_changes(p, default_host=None, default_port=22)

    def test_unknown_field_in_entry_ignored(self, tmp_path: Path) -> None:
        p = _write_config(tmp_path, {"changes": [{"hash": "abc", "host": "h", "extra": "field"}]})
        changes = load_changes(p, default_host=None, default_port=22)
        assert changes[0].hash == "abc"


# ---------------------------------------------------------------------------
# load_toml_config — editor field
# ---------------------------------------------------------------------------


class TestLoadTomlConfigEditor:
    def test_editor_field_loaded(self, tmp_path: Path) -> None:
        p = _write_toml(tmp_path, '[config]\neditor = "vim"\n')
        cfg = load_toml_config(p)
        assert cfg.editor == "vim"

    def test_editor_defaults_to_none(self, tmp_path: Path) -> None:
        p = _write_toml(tmp_path, "[config]\n")
        cfg = load_toml_config(p)
        assert cfg.editor is None


# ---------------------------------------------------------------------------
# resolve_editor
# ---------------------------------------------------------------------------


class TestResolveEditor:
    def test_config_editor_takes_priority(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EDITOR", "nano")
        assert resolve_editor("vim") == "vim"

    def test_env_var_used_when_config_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EDITOR", "nano")
        assert resolve_editor(None) == "nano"

    def test_returns_none_when_no_editor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("EDITOR", raising=False)
        assert resolve_editor(None) is None

    def test_empty_editor_env_treated_as_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EDITOR", "")
        assert resolve_editor(None) is None
