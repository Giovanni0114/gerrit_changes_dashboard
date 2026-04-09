# EPIC003-001 — Fetch Gerrit comments via SSH

## Requirements

1. Modify `query_approvals` in `gerrit.py` to accept an `include_comments`
   parameter (default `True`) that adds `--comments` to the SSH query.
2. Add a `GerritComment` dataclass to `models.py` with fields: `timestamp`
   (int), `reviewer_name` (str), `reviewer_email` (str), `message` (str).
3. Add `gerrit_comments: list[GerritComment]` to `TrackedChange` as an
   in-memory-only field (NOT persisted to `approvals.json`).
4. In `_store_result` (`app.py`), parse the `"comments"` array from the SSH
   response and populate `ch.gerrit_comments`.
5. If `"comments"` is absent from the response (e.g., older Gerrit version),
   set `gerrit_comments` to an empty list.

## Acceptance Criteria

- `query_approvals` with `include_comments=True` produces an SSH command
  containing both `--all-approvals` and `--comments`.
- `query_approvals` with `include_comments=False` produces the same command
  as today (no `--comments`).
- `GerritComment` is a frozen dataclass with proper type hints.
- `_store_result` populates `ch.gerrit_comments` from raw SSH data.
- Missing or empty `"comments"` key results in `gerrit_comments == []`.
- `gerrit_comments` is NOT included in any config write/read path.
- Existing tests continue to pass (no regressions in approval parsing).
