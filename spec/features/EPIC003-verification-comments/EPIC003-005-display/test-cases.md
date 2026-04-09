# EPIC003-005 — Test Cases

## TC-001: Analyzer report shown in table

Create a `TrackedChange` with `analyzer_report = "FAILURE: foo"`. Build
table. Verify no crash and table is built.

## TC-002: No analyzer report — no change

Create a `TrackedChange` with `analyzer_report = None`. Build table. Verify
table renders same as before feature 005 (just user comments if any).

## TC-003: Both user comments and analyzer report

Create a `TrackedChange` with `comments = ["my note"]` and
`analyzer_report = "FAILURE: foo"`. Build table. Verify both are present.

## TC-004: Only analyzer report, no user comments

`comments = []`, `analyzer_report = "FAILURE: foo"`. Build table. Verify
report is shown without separator.

## TC-005: Deleted change with analyzer report

`deleted = True`, `analyzer_report = "FAILURE: foo"`. Build table. Verify
dim/strike styling applies.

## TC-006: Disabled change with analyzer report

`disabled = True`, `analyzer_report = "FAILURE: foo"`. Build table. Verify
dim/italic styling applies.

## TC-007: Empty string analyzer report treated as no report

`analyzer_report = ""`. Build table. Verify treated same as `None`.

## TC-008: Multi-line analyzer report

`analyzer_report = "FAILURE: foo\nABORTED: bar\nUNSTABLE: baz"`. Build
table. Verify no crash.
