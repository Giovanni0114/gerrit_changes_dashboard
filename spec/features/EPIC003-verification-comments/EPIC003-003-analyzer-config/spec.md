# EPIC003-003 — Analyzer Configuration in TOML

## Requirements

1. Add an `AnalyzerConfig` dataclass to `config.py`:
   ```python
   @dataclass
   class AnalyzerConfig:
       type: str                    # "pattern" or "none"
       patterns: list[str]          # regex patterns (for pattern type)
       reviewer_filter: str | None  # regex for reviewer filtering
   ```
2. Extend `AppConfig` with `analyzer: AnalyzerConfig | None` field.
3. Parse `[analyzer]` and `[analyzer.pattern]` sections in `load_toml_config`.
4. If `[analyzer]` section is absent, `analyzer` is `None` (no analysis).
5. Provide sensible default patterns when `type = "pattern"` but `patterns` is
   not specified.
6. Add a factory function `create_analyzer(config: AnalyzerConfig | None)
   -> Analyzer` that returns the appropriate analyzer instance.
7. Validate config: unknown `type` raises `ValueError`.

## TOML Format

```toml
[analyzer]
type = "pattern"

[analyzer.pattern]
patterns = [
    '(?P<report>https?://\S+\s*:\s*(?:FAILURE|ABORTED|UNSTABLE))',
    '(?P<report>Build Failed.*)',
]
reviewer_filter = "(?i)jenkins|zuul|ci-bot"
```

## Acceptance Criteria

- Missing `[analyzer]` section results in `AppConfig.analyzer == None`.
- `type = "none"` results in `NullAnalyzer` from factory.
- `type = "pattern"` results in `PatternAnalyzer` with configured patterns.
- Missing `patterns` key uses default patterns.
- Missing `reviewer_filter` key results in `None` (no filtering).
- Invalid `type` raises `ValueError` with clear message.
- Invalid regex in `patterns` raises `ValueError` at config load time.
- Existing config files without `[analyzer]` continue to work (backward
  compatible).
