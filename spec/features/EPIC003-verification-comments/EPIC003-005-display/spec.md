# EPIC003-005 — Display Analyzer Report in Dashboard

## Requirements

1. Modify `build_table` in `display.py` to render `ch.analyzer_report` in the
   Comments column.
2. The analyzer report appears BELOW user comments (feature 005), separated
   by a `---` line when both are present.
3. Styling: analyzer report uses `dim cyan` to distinguish from user comments.
4. When only the analyzer report exists (no user comments), show it directly
   without the separator.
5. When the change is deleted/disabled, apply the same dim/strike styling
   to the analyzer report as to user comments.
6. Long reports should wrap naturally within the column (no truncation).
7. When `analyzer_report` is `None`, the Comments column shows only user
   comments (or is empty) — no change from current behavior.

## Acceptance Criteria

- Failing changes (-1/-2 row background) show the failure analysis in the
  Comments column.
- User comments and analyzer report are visually distinct (different colors).
- Separator only shown when both user comments and analyzer report exist.
- Deleted/disabled styling applied uniformly.
- No crash when `analyzer_report` is `None`, empty string, or very long.
- Table renders correctly with 0, 1, or many changes having reports.
