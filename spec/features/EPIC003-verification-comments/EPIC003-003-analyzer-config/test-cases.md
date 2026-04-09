# EPIC003-003 — Test Cases

## TC-001: Missing analyzer section returns None

TOML with only `[config]`. Load config. Verify `cfg.analyzer is None`.

## TC-002: type = "none" parses correctly

```toml
[analyzer]
type = "none"
```
Verify `cfg.analyzer.type == "none"`.

## TC-003: type = "pattern" with explicit patterns

```toml
[analyzer]
type = "pattern"

[analyzer.pattern]
patterns = ["foo", "bar"]
reviewer_filter = "jenkins"
```
Verify `cfg.analyzer.patterns == ["foo", "bar"]` and
`cfg.analyzer.reviewer_filter == "jenkins"`.

## TC-004: type = "pattern" with default patterns

```toml
[analyzer]
type = "pattern"
```
No `[analyzer.pattern]` section. Verify `cfg.analyzer.patterns` is a
non-empty list of default patterns.

## TC-005: Missing reviewer_filter defaults to None

```toml
[analyzer]
type = "pattern"

[analyzer.pattern]
patterns = ["foo"]
```
Verify `cfg.analyzer.reviewer_filter is None`.

## TC-006: Invalid type raises ValueError

```toml
[analyzer]
type = "unknown"
```
Verify `ValueError` raised with message containing "unknown".

## TC-007: Invalid regex in patterns raises ValueError

```toml
[analyzer]
type = "pattern"

[analyzer.pattern]
patterns = ["[invalid"]
```
Verify `ValueError` raised.

## TC-008: Backward compatibility — existing config without analyzer

Load the actual `config.toml` from the repo. Verify it loads without error
and `cfg.analyzer is None`.

## TC-009: Factory returns NullAnalyzer for None config

`create_analyzer(None)` returns a `NullAnalyzer` instance.

## TC-010: Factory returns NullAnalyzer for type "none"

`create_analyzer(AnalyzerConfig(type="none", ...))` returns `NullAnalyzer`.

## TC-011: Factory returns PatternAnalyzer for type "pattern"

`create_analyzer(AnalyzerConfig(type="pattern", patterns=["foo"],
reviewer_filter=None))` returns a `PatternAnalyzer` with correct config.

## TC-012: Factory raises for unknown type

`create_analyzer(AnalyzerConfig(type="bad", ...))` raises `ValueError`.
