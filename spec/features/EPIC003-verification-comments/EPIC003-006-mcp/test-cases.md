# EPIC003-006 — Test Cases

## TC-001: Failing change includes analyzer_report in MCP

Set up a change with `analyzer_report = "FAILURE: foo"`. Call `_get_changes`.
Verify payload contains `"analyzer_report": "FAILURE: foo"`.

## TC-002: Passing change has null analyzer_report

Set up a change with `analyzer_report = None`. Call `_get_changes`. Verify
payload contains `"analyzer_report": null`.

## TC-003: gerrit_comments included in payload

Set up a change with two `GerritComment` entries. Call `_get_changes`. Verify
`gerrit_comments` array has two objects with correct fields.

## TC-004: Empty gerrit_comments

Set up a change with `gerrit_comments = []`. Call `_get_changes`. Verify
`gerrit_comments` is an empty array.

## TC-005: Existing fields unchanged

Verify all existing MCP payload fields (host, hash, waiting, disabled,
deleted, submitted, subject, number, project, url, approvals) are still
present and correct.
