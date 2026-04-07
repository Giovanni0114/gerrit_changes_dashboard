"""Tests for gerrit.py — query_open_changes function."""

import json
import subprocess

import pytest

from gerrit import query_open_changes

# ---------------------------------------------------------------------------
# query_open_changes
# ---------------------------------------------------------------------------


class TestQueryOpenChanges:
    def test_multiple_changes_returned(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """TC-004: Parse 3 change lines + 1 stats line → list of 3 dicts."""
        change1 = {"number": 100, "currentPatchSet": {"revision": "aaa111"}}
        change2 = {"number": 200, "currentPatchSet": {"revision": "bbb222"}}
        change3 = {"number": 300, "currentPatchSet": {"revision": "ccc333"}}
        stats = {"type": "stats", "rowCount": 3, "runTimeMilliseconds": 42}
        stdout = "\n".join(json.dumps(obj) for obj in [change1, change2, change3, stats])

        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *args, **kwargs: type("Result", (), {"returncode": 0, "stdout": stdout})(),
        )
        result = query_open_changes("user@example.com", "gerrit.host")
        assert len(result) == 3
        assert result[0]["number"] == 100
        assert result[1]["number"] == 200
        assert result[2]["number"] == 300

    def test_no_changes_returned(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """TC-005: Only stats line → empty list."""
        stats = {"type": "stats", "rowCount": 0, "runTimeMilliseconds": 5}
        stdout = json.dumps(stats)

        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *args, **kwargs: type("Result", (), {"returncode": 0, "stdout": stdout})(),
        )
        result = query_open_changes("user@example.com", "gerrit.host")
        assert result == []

    def test_ssh_failure_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """TC-006: SSH timeout → empty list."""

        def _timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="ssh", timeout=30)

        monkeypatch.setattr(subprocess, "run", _timeout)
        result = query_open_changes("user@example.com", "gerrit.host")
        assert result == []

    def test_ssh_nonzero_exit_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """TC-006 variant: Non-zero exit code → empty list."""
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *args, **kwargs: type("Result", (), {"returncode": 1, "stdout": ""})(),
        )
        result = query_open_changes("user@example.com", "gerrit.host")
        assert result == []

    def test_port_included_in_command(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify -p flag is passed when port is specified."""
        captured_cmd = []
        stats = {"type": "stats", "rowCount": 0}

        def _capture(*args, **kwargs):
            captured_cmd.extend(args[0])
            return type("Result", (), {"returncode": 0, "stdout": json.dumps(stats)})()

        monkeypatch.setattr(subprocess, "run", _capture)
        query_open_changes("user@example.com", "gerrit.host", port=29418)
        assert "-p" in captured_cmd
        assert "29418" in captured_cmd
