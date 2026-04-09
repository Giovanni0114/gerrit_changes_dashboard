# EPIC003-004 — Integrate Analyzer into Refresh Cycle

## Requirements

1. `App.__init__` accepts an `analyzer: Analyzer` parameter and stores it.
2. `_store_result` detects Verified -1 or -2 in the parsed approvals.
3. When Verified -1/-2 is detected AND `gerrit_comments` is non-empty, call
   `self.analyzer.analyze(ch.gerrit_comments)` and store the result in
   `ch.analyzer_report`.
4. When Verified is NOT -1/-2 (or no approvals yet), set
   `ch.analyzer_report = None`.
5. Add `analyzer_report: str | None = None` field to `TrackedChange`
   (in-memory only).
6. The analyzer runs synchronously inside `_store_result` (which already
   runs on a background thread). No separate executor needed for
   `PatternAnalyzer`.
7. Handle analyzer exceptions gracefully — catch `Exception`, log the error,
   set `ch.analyzer_report = None`.
8. When a change transitions from -1/-2 to passing (new patchset), the report
   is naturally cleared because `_store_result` sets it to `None`.

## Helper Logic

Detection of verification failure:
```python
def _has_verification_failure(approvals: list[ApprovalEntry]) -> bool:
    return any(
        a.label == "Verified" and a.value in ("-1", "-2")
        for a in approvals
    )
```

## Acceptance Criteria

- Changes with Verified -1/-2 get `analyzer_report` populated (when analyzer
  returns non-None).
- Changes with Verified +1/+2 or no Verified label have
  `analyzer_report == None`.
- Changes that transition from -1 to +1 have their report cleared.
- Analyzer exceptions don't crash the app; report is set to None.
- Disabled/deleted changes are not analyzed (they're skipped by `do_queries`
  already).
- The refresh cycle timing is not noticeably affected by pattern analysis.
