# EPIC003 — Verification Failure Comments & Analyzer System

## Motivation

When a change has Verified -1 or -2 (typically set by Jenkins/CI), the
dashboard shows a red/orange row but provides no information about *why* the
verification failed. The user must open the Gerrit web UI and read through
reviewer comments to find failure details.

This EPIC adds automatic fetching of Gerrit reviewer comments via SSH and a
configurable analyzer system that extracts actionable failure information to
display directly on the dashboard.

## Prerequisites

- **Feature 005** (comments field) — the display sub-feature (EPIC003-005)
  reuses the Comments column added by feature 005. Other sub-features are
  independent.

## Scope

This EPIC covers:
- Fetching Gerrit comments via SSH `--comments` flag
- An `Analyzer` Protocol for processing comments
- A built-in `PatternAnalyzer` (regex-based extraction)
- TOML configuration for analyzer settings
- Integration into the refresh cycle
- Display of analyzer reports in the dashboard
- MCP exposure of analyzer data

This EPIC does **not** cover:
- LLM-based analysis (deferred to a future EPIC)
- Plugin discovery/loading mechanisms
- Interactive comment browsing or keybinds

## Design Overview

The analyzer system uses a simple `Analyzer` Protocol with a single
`analyze(comments) -> str | None` method. A factory function creates the
configured analyzer from TOML settings. The analyzer runs inline during the
refresh cycle (inside `_store_result`) — it's fast enough for regex-based
analysis. When the future LLM EPIC arrives, the Protocol stays the same; only
the execution model changes (deferred to a separate thread pool).

See `spike.md` in this directory for detailed design rationale.

## Sub-Features

- **EPIC003-001** — Fetch Gerrit comments via SSH
- **EPIC003-002** — Analyzer Protocol and PatternAnalyzer
- **EPIC003-003** — Analyzer configuration in TOML
- **EPIC003-004** — Integrate analyzer into refresh cycle
- **EPIC003-005** — Display analyzer report in dashboard
- **EPIC003-006** — Expose analyzer report over MCP

## Implementation Order

001, 002, 003 are independent (can be parallel). 004 depends on all three.
005 depends on 004 and feature 005. 006 depends on 004.

## Open Questions

1. Should `--comments` be a flag parameter on `query_approvals` or always
   included? (See spike.md section 8.1)
2. Default regex patterns for the PatternAnalyzer — need examples from the
   target Gerrit instance to tune these.
