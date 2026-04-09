# EPIC003-002 — Test Cases

## TC-001: PatternAnalyzer extracts FAILURE URLs

Comments:
```
"Build Failed\n\nhttps://jenkins/job/foo/123/ : FAILURE\nhttps://jenkins/job/bar/456/ : ABORTED"
```
Pattern: `(?P<report>https?://\S+\s*:\s*(?:FAILURE|ABORTED|UNSTABLE))`

Expected: two lines, each with URL and status.

## TC-002: PatternAnalyzer returns None when no matches

Comments: `["Patch Set 3:\n\nLooks good to me"]`
Pattern: `(?P<report>https?://\S+\s*:\s*FAILURE)`

Expected: `None`.

## TC-003: PatternAnalyzer filters by reviewer

Comments from "Jenkins" and "Alice".
`reviewer_filter = "(?i)jenkins"`

Expected: only Jenkins comments are analyzed; Alice's comments ignored.

## TC-004: PatternAnalyzer with no reviewer filter analyzes all

Same comments as TC-003 but `reviewer_filter=None`.

Expected: all comments are analyzed.

## TC-005: Pattern without named group uses full match

Pattern: `Build Failed.*`
Comment: `"Patch Set 2: Verified-1\n\nBuild Failed on linux-x86"`

Expected: `"Build Failed on linux-x86"`.

## TC-006: Pattern with named group uses group only

Pattern: `Build (?P<report>Failed\S*)`
Comment: `"Build FailedXYZ other stuff"`

Expected: `"FailedXYZ"`.

## TC-007: Duplicate matches are removed

Two comments with the same failure URL. Same pattern as TC-001.

Expected: URL appears only once in output.

## TC-008: Empty comments list returns None

`analyze([])` -> `None`.

## TC-009: NullAnalyzer always returns None

`NullAnalyzer().analyze([comment1, comment2])` -> `None`.

## TC-010: Multiple patterns applied in order

Two patterns: one for FAILURE, one for ABORTED. Comment contains both.

Expected: both matches present in output.

## TC-011: PatternAnalyzer with empty patterns list returns None

`PatternAnalyzer(patterns=[], reviewer_filter=None).analyze([comment])`
-> `None`.

## TC-012: Reviewer filter matches on email

`reviewer_filter = "jenkins"`. Reviewer has `name="CI Bot"` but
`email="jenkins@example.com"`.

Expected: comment is included (filter checks both name and email).

## TC-013: Real-world example from FEATURES.md

Use the exact JSON example from FEATURES.md (lines 222-258) as input.
Use default patterns. Verify sensible output.
