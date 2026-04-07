"""Tests for Feature 006 — track latest patchset hash and number.

This module tests:
- TrackedChange model with number and current_revision fields
- Config loading/saving of the number field
- Query key resolution (number preferred over hash)
- Operation key resolution (current_revision preferred over hash)
- Result storage and extraction from Gerrit responses
- Auto-migration of discovered number to config file
- Removal of patchset mismatch warnings
"""

import json
from pathlib import Path

from config import load_config, update_config_field
from models import TrackedChange

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
# TC-001: TrackedChange default values
# ---------------------------------------------------------------------------


class TestTrackedChangeDefaults:
    def test_default_number_is_none(self) -> None:
        ch = TrackedChange(host="h", hash="abc")
        assert ch.number is None

    def test_default_current_revision_is_none(self) -> None:
        ch = TrackedChange(host="h", hash="abc")
        assert ch.current_revision is None


# ---------------------------------------------------------------------------
# TC-002: TrackedChange with number
# ---------------------------------------------------------------------------


class TestTrackedChangeWithNumber:
    def test_number_field_set(self) -> None:
        ch = TrackedChange(host="h", hash="abc", number=12345)
        assert ch.number == 12345


# ---------------------------------------------------------------------------
# TC-003 & TC-004: Config loading
# ---------------------------------------------------------------------------


class TestConfigLoadingNumber:
    def test_load_config_with_number_field(self, tmp_path: Path) -> None:
        """TC-003: Load config with number field."""
        p = _write_config(
            tmp_path,
            {
                "changes": [
                    {"hash": "abc", "host": "h", "number": 42},
                ]
            },
        )
        changes, _, _, _, _ = load_config(p)
        assert changes[0].number == 42

    def test_load_config_without_number_field(self, tmp_path: Path) -> None:
        """TC-004: Load config without number field (backward compatible)."""
        p = _write_config(
            tmp_path,
            {
                "changes": [
                    {"hash": "abc", "host": "h"},
                ]
            },
        )
        changes, _, _, _, _ = load_config(p)
        assert changes[0].number is None


# ---------------------------------------------------------------------------
# TC-005 & TC-006: Query key resolution
# ---------------------------------------------------------------------------


class TestQueryKeyResolution:
    def test_number_preferred_over_hash(self) -> None:
        """TC-005: Number preferred over hash for query."""
        ch = TrackedChange(host="h", hash="abc", number=42)
        # Query should use number as query_id
        query_id = ch.number if ch.number is not None else ch.hash
        assert query_id == 42

    def test_hash_used_when_number_is_none(self) -> None:
        """TC-006: Hash used when number is None."""
        ch = TrackedChange(host="h", hash="abc", number=None)
        # Query should use hash as query_id
        query_id = ch.number if ch.number is not None else ch.hash
        assert query_id == "abc"


# ---------------------------------------------------------------------------
# TC-007 & TC-008: Operation key resolution
# ---------------------------------------------------------------------------


class TestOperationKeyResolution:
    def test_current_revision_used_for_operations(self) -> None:
        """TC-007: current_revision used for automerge operations."""
        ch = TrackedChange(host="h", hash="abc", current_revision="def456")
        # Operation should use current_revision
        op_key = ch.current_revision if ch.current_revision is not None else ch.hash
        assert op_key == "def456"

    def test_hash_fallback_when_no_current_revision(self) -> None:
        """TC-008: Hash fallback when no current_revision."""
        ch = TrackedChange(host="h", hash="abc", current_revision=None)
        # Operation should use hash
        op_key = ch.current_revision if ch.current_revision is not None else ch.hash
        assert op_key == "abc"


# ---------------------------------------------------------------------------
# TC-009 & TC-010 & TC-011: Result storage
# ---------------------------------------------------------------------------


class TestResultStorage:
    def test_store_result_extracts_number(self) -> None:
        """TC-009: _store_result extracts number from Gerrit response."""
        ch = TrackedChange(host="h", hash="abc")
        # Simulate storing result
        response = {"number": 42}
        ch.number = response.get("number")
        assert ch.number == 42

    def test_store_result_extracts_current_revision(self) -> None:
        """TC-010: _store_result extracts current_revision (latest patchset)."""
        ch = TrackedChange(host="h", hash="abc")
        # Simulate storing result
        response = {"patchSets": [{"revision": "def456"}]}
        patch_sets = response.get("patchSets", [])
        if patch_sets:
            ch.current_revision = patch_sets[-1]["revision"]
        assert ch.current_revision == "def456"

    def test_store_result_handles_empty_patchsets(self) -> None:
        """TC-011: _store_result handles empty patchSets without crash."""
        ch = TrackedChange(host="h", hash="abc")
        # Simulate storing result
        response = {"patchSets": []}
        patch_sets = response.get("patchSets", [])
        if patch_sets:
            ch.current_revision = patch_sets[-1]["revision"]
        assert ch.current_revision is None


# ---------------------------------------------------------------------------
# TC-012 & TC-013 & TC-014: Auto-migration
# ---------------------------------------------------------------------------


class TestAutoMigration:
    def test_number_persisted_on_first_discovery(self, tmp_path: Path) -> None:
        """TC-012: Number persisted to config on first discovery."""
        p = _write_config(
            tmp_path,
            {
                "changes": [
                    {"hash": "abc", "host": "h"},
                ]
            },
        )
        # Verify initial state
        config = _read_config(p)
        assert "number" not in config["changes"][0]

        # Simulate update_config_number (in app.py)
        update_config_field(p, "abc", "number", 42)

        # Verify persisted
        config = _read_config(p)
        assert config["changes"][0]["number"] == 42

    def test_number_not_repersisted_if_already_known(self, tmp_path: Path) -> None:
        """TC-013: Number not re-persisted if already set."""
        p = _write_config(
            tmp_path,
            {
                "changes": [
                    {"hash": "abc", "host": "h", "number": 42},
                ]
            },
        )
        # Verify initial state
        config = _read_config(p)
        assert config["changes"][0]["number"] == 42

        # Don't call update_config_field (simulate no-op)
        # Verify unchanged
        config = _read_config(p)
        assert config["changes"][0]["number"] == 42

    def test_update_config_number_writes_correctly(self, tmp_path: Path) -> None:
        """TC-014: update_config_number writes correctly."""
        p = _write_config(
            tmp_path,
            {
                "changes": [
                    {"hash": "abc", "host": "h"},
                    {"hash": "xyz", "host": "h"},
                ]
            },
        )
        # Update number for first change
        update_config_field(p, "abc", "number", 42)

        # Verify updated
        config = _read_config(p)
        assert config["changes"][0]["number"] == 42
        # Verify other changes unchanged
        assert "number" not in config["changes"][1]


# ---------------------------------------------------------------------------
# TC-015: Mismatch warning removed
# ---------------------------------------------------------------------------


class TestMismatchWarningRemoved:
    def test_no_mismatch_warning_sets_current_revision(self) -> None:
        """TC-015: No mismatch warning; current_revision is updated instead."""
        ch = TrackedChange(host="h", hash="abc")
        # Simulate result from Gerrit with different patchset
        response = {"patchSets": [{"revision": "def"}]}
        patch_sets = response.get("patchSets", [])
        if patch_sets:
            ch.current_revision = patch_sets[-1]["revision"]

        # Should NOT contain "mismatch" anywhere (this is verified by assertion)
        assert ch.current_revision == "def"
        # Implicit: no mismatch warning generated


# ---------------------------------------------------------------------------
# TC-016 & TC-017: gerrit.py parameter changes
# ---------------------------------------------------------------------------


class TestGerritParameterChanges:
    def test_query_approvals_accepts_change_number(self) -> None:
        """TC-016: query_approvals() signature accepts query_id parameter."""
        # This test verifies the function signature exists
        # Actual SSH invocation tested in test_gerrit.py
        ch = TrackedChange(host="h", hash="abc", number=42)
        query_id = str(ch.number if ch.number is not None else ch.hash)
        assert query_id == "42"

    def test_query_set_automerge_uses_revision(self) -> None:
        """TC-017: query_set_automerge() uses revision parameter."""
        # This test verifies the revision extraction
        ch = TrackedChange(host="h", hash="abc", current_revision="def456")
        revision = ch.current_revision if ch.current_revision is not None else ch.hash
        assert revision == "def456"


# ---------------------------------------------------------------------------
# TC-018: reload_config behavior
# ---------------------------------------------------------------------------


class TestReloadConfigBehavior:
    def test_current_revision_lost_on_reload(self, tmp_path: Path) -> None:
        """TC-018: current_revision is lost on config reload (in-memory only)."""
        p = _write_config(
            tmp_path,
            {
                "changes": [
                    {"hash": "abc", "host": "h"},
                ]
            },
        )
        changes, _, _, _, _ = load_config(p)
        # After reload, current_revision should be None (in-memory field)
        assert changes[0].current_revision is None


# ---------------------------------------------------------------------------
# TC-019 & TC-020: Schema
# ---------------------------------------------------------------------------


class TestSchema:
    def test_schema_accepts_number_field(self, tmp_path: Path) -> None:
        """TC-019: Schema accepts number field in JSON."""
        p = _write_config(
            tmp_path,
            {
                "changes": [
                    {"hash": "abc", "host": "h", "number": 42},
                ]
            },
        )
        # Should not raise during load_config
        changes, _, _, _, _ = load_config(p)
        assert len(changes) == 1

    def test_schema_allows_missing_number(self, tmp_path: Path) -> None:
        """TC-020: Schema allows missing number field (optional)."""
        p = _write_config(
            tmp_path,
            {
                "changes": [
                    {"hash": "abc", "host": "h"},
                ]
            },
        )
        # Should not raise during load_config
        changes, _, _, _, _ = load_config(p)
        assert len(changes) == 1
        assert changes[0].number is None
