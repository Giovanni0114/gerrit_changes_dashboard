# EPIC003-004 — Test Cases

## TC-001: Analyzer called when Verified -1

Set up a `TrackedChange` with approvals including `Verified: -1` and
`gerrit_comments` populated. Mock the analyzer. Call `_store_result`.
Verify `analyzer.analyze()` was called with the comments.

## TC-002: Analyzer called when Verified -2

Same as TC-001 but with `Verified: -2`.

## TC-003: Analyzer NOT called when Verified +1

Set up approvals with `Verified: +1`. Call `_store_result`. Verify analyzer
was NOT called and `ch.analyzer_report is None`.

## TC-004: Analyzer NOT called when no Verified label

Set up approvals with only `Code-Review: +2`. Call `_store_result`. Verify
analyzer was NOT called.

## TC-005: Analyzer report stored on change

Analyzer returns `"FAILURE: job/foo/123"`. Call `_store_result`. Verify
`ch.analyzer_report == "FAILURE: job/foo/123"`.

## TC-006: Analyzer returns None — report is None

Analyzer returns `None`. Verify `ch.analyzer_report is None`.

## TC-007: Report cleared when verification passes

First call: Verified -1, analyzer returns report. Second call: Verified +1.
Verify `ch.analyzer_report is None` after second call.

## TC-008: Analyzer exception caught gracefully

Analyzer raises `RuntimeError`. Call `_store_result`. Verify no exception
propagates and `ch.analyzer_report is None`.

## TC-009: Empty gerrit_comments — analyzer still called

Verified -1 but `gerrit_comments == []`. Analyzer should still be called
(it returns `None` for empty input).

## TC-010: _has_verification_failure helper

Test the helper with various approval combinations:
- `[Verified: -1]` -> True
- `[Verified: -2]` -> True
- `[Verified: +1]` -> False
- `[Code-Review: -2]` -> False (not Verified label)
- `[]` -> False
- `[Verified: -1, Code-Review: +2]` -> True
