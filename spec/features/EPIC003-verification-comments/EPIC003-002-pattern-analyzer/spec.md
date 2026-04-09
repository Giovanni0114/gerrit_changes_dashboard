# EPIC003-002 — Analyzer Protocol and PatternAnalyzer

## Requirements

1. Create a new module `analyzers.py`.
2. Define `Analyzer` as a `Protocol` with a single method:
   ```python
   def analyze(self, comments: list[GerritComment]) -> str | None
   ```
3. Implement `PatternAnalyzer` class:
   - Constructor takes `patterns: list[str]` (regex patterns) and an optional
     `reviewer_filter: str | None` (regex to match reviewer name/email).
   - `analyze()` method:
     a. If `reviewer_filter` is set, discard comments not matching the filter.
     b. For each remaining comment, try each pattern against the message.
     c. If a pattern has a named group `report`, use that. Otherwise use the
        full match.
     d. Collect all matches, deduplicate, return joined by newline.
     e. Return `None` if no matches found.
4. Implement `NullAnalyzer` class that always returns `None` (used when no
   analyzer is configured).

## Acceptance Criteria

- `PatternAnalyzer` correctly extracts failure URLs and messages from the
  example comments in FEATURES.md.
- `reviewer_filter` correctly filters to only CI bot comments.
- Patterns with named group `report` extract only the group.
- Patterns without named groups extract the full match.
- Duplicate matches are removed.
- Empty comments list returns `None`.
- No matches returns `None`.
- `NullAnalyzer.analyze()` always returns `None`.
- The module has no dependencies on `app.py`, `config.py`, or `display.py`
  (pure logic).
