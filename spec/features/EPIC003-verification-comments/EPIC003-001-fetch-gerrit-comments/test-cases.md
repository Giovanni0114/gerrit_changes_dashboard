# EPIC003-001 — Test Cases

## TC-001: GerritComment dataclass defaults

Create a `GerritComment` with all fields. Verify fields are accessible and
types are correct.

## TC-002: GerritComment is frozen

Attempt to modify a field on a `GerritComment` instance. Verify
`FrozenInstanceError` is raised.

## TC-003: TrackedChange has empty gerrit_comments by default

Create a `TrackedChange` with no `gerrit_comments` argument. Verify
`ch.gerrit_comments == []`.

## TC-004: query_approvals includes --comments flag

Mock `subprocess.run`. Call `query_approvals("abc", "host",
include_comments=True)`. Verify the SSH command contains `--comments`.

## TC-005: query_approvals excludes --comments when disabled

Mock `subprocess.run`. Call `query_approvals("abc", "host",
include_comments=False)`. Verify the SSH command does NOT contain `--comments`.

## TC-006: _store_result parses comments array

Provide a data dict with a `"comments"` array containing two comment objects.
Call `_store_result`. Verify `ch.gerrit_comments` has two `GerritComment`
entries with correct fields.

## TC-007: _store_result handles missing comments key

Provide a data dict without a `"comments"` key. Call `_store_result`. Verify
`ch.gerrit_comments == []`.

## TC-008: _store_result handles empty comments array

Provide a data dict with `"comments": []`. Call `_store_result`. Verify
`ch.gerrit_comments == []`.

## TC-009: _store_result preserves existing approval parsing

Provide a data dict with both `"patchSets"` (approvals) and `"comments"`.
Call `_store_result`. Verify approvals are parsed correctly (no regression)
AND comments are parsed.

## TC-010: gerrit_comments not included in config writes

Create a `TrackedChange` with `gerrit_comments` populated. Call
`add_change_to_config`. Read the JSON file. Verify no `gerrit_comments` field
in the written entry.
