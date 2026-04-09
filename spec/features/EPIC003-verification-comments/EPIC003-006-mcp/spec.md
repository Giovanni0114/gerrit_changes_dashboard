# EPIC003-006 — Expose Analyzer Report over MCP

## Requirements

1. Extend the `_get_changes` payload in `mcp_background.py` to include:
   - `analyzer_report: str | null` — the analyzed failure summary.
   - `gerrit_comments: list[object]` — raw Gerrit comments (each with
     `timestamp`, `reviewer_name`, `reviewer_email`, `message`).
2. Only include `gerrit_comments` for changes that have them (don't send empty
   arrays to reduce payload size — or always include for consistency; TBD).
3. `analyzer_report` is always included (as `null` when not available).

## Acceptance Criteria

- MCP payload for a failing change includes `analyzer_report` string.
- MCP payload for a passing change includes `analyzer_report: null`.
- MCP payload includes `gerrit_comments` array with correct structure.
- Existing MCP fields are unchanged (backward compatible).
