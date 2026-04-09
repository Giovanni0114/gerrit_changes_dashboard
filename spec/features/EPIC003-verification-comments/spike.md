# EPIC003 SPIKE — Verification Failure Comments & Analyzer Plugin System

## Goal

When a change has Verified -1 or -2, pull the Gerrit reviewer comments via SSH
and run them through a configurable analyzer to produce a short failure report
shown on the dashboard.

This SPIKE documents the research, design decisions, and implementation plan.
The LLM analyzer is explicitly deferred to a future EPIC — this EPIC delivers
the plugin interface and a built-in pattern-matching analyzer only.

---

## 1. Problem Statement

When Jenkins (or another CI system) sets Verified -1/-2, it typically leaves
comments explaining what failed — build URLs, test names, abort reasons. Today
the dashboard shows the red/orange row but the user must open the Gerrit web UI
to find out *why* it failed.

The raw Gerrit comment data looks like this (via `ssh host gerrit query
--format=json --comments <number>`):

```json
{
  "comments": [
    {
      "timestamp": 1775662011,
      "reviewer": { "name": "Jenkins", "email": "...", "username": "..." },
      "message": "Patch Set 2:\n\nAborted related gates because pre-commit gate https://... failed."
    },
    {
      "timestamp": 1775666408,
      "reviewer": { "name": "Jenkins", "email": "...", "username": "..." },
      "message": "Patch Set 2: Verified-1\n\nBuild Failed\n\nhttps://.../job/foo/123/ : FAILURE"
    }
  ]
}
```

**Key observations:**
- Comments come from many reviewers; only CI/bot comments are interesting here.
- The format varies across organizations, Gerrit instances, and projects.
- The most relevant comment is typically the last one from the bot that set
  Verified -1/-2.
- A single query with `--comments` returns all comments; there is no way to
  filter server-side.

---

## 2. Design Decisions

### 2.1 When to fetch comments

**Decision: Fetch comments as part of the normal refresh cycle, but only for
changes that have Verified -1 or -2.**

Alternatives considered:
- *On every refresh for all changes* — wasteful; most changes don't need
  comments.
- *On-demand via keybind* — poor UX; the whole point is automatic surfacing.
- *Separate background poll* — adds complexity for no benefit over the existing
  refresh cycle.

**Implementation:** Combine `--all-approvals` and `--comments` in a single SSH
query when we detect the change needs it. This avoids a second SSH round-trip.
On the first refresh, approvals are fetched without `--comments` (we don't know
the status yet). Once a change is known to have -1/-2, subsequent refreshes use
the combined query.

Actually, simpler: **always query with `--all-approvals --comments`**. The
`--comments` flag adds negligible overhead to the SSH response (a few extra
lines of JSON). This avoids conditional logic entirely. The comments are simply
ignored for changes that don't need analysis.

**Revised decision: Always fetch with `--comments`. Store raw comments on
`TrackedChange`. Only run the analyzer when Verified -1/-2 is detected.**

### 2.2 Where to store Gerrit comments

**Decision: New in-memory field `gerrit_comments` on `TrackedChange`. NOT
persisted to `approvals.json`.**

These comments are fetched from the server on every refresh. Persisting them
would cause staleness and bloat the changes file. They are conceptually
different from user-authored comments (feature 005).

### 2.3 Plugin system vs built-in analyzer

**Decision: Start with a simple `Analyzer` Protocol, not a full plugin
discovery/loading system.**

The FEATURES.md mentions a "plugin system" with discovery, loading, and
configuration. For a ~2000-line TUI tool, this is overengineered. Instead:

- Define an `Analyzer` Protocol with a single method.
- Ship two built-in analyzers:
  1. `PatternAnalyzer` — regex-based extraction of failure URLs and messages.
  2. (future EPIC) `LLMAnalyzer` — sends comments to an LLM backend.
- Configuration in TOML selects which analyzer to use and its settings.
- The interface is simple enough that adding new analyzers later is trivial.

If the number of analyzers grows beyond 3-4, *then* add a plugin discovery
mechanism. YAGNI until that point.

### 2.4 Analyzer interface

```python
from typing import Protocol

@dataclass
class GerritComment:
    timestamp: int
    reviewer_name: str
    reviewer_email: str
    message: str

class Analyzer(Protocol):
    def analyze(self, comments: list[GerritComment]) -> str | None:
        """Analyze Gerrit comments and return a short report string, or None.

        This method may be called from a background thread. It must be
        thread-safe and should not block for more than a few seconds.
        """
        ...
```

The return value is a plain string displayed in the dashboard. Returning `None`
means "no useful analysis" (e.g., no matching patterns found).

**Why a Protocol, not an ABC:**
- Matches the existing codebase style (`AppContext` is a Protocol).
- No inheritance required — any object with an `analyze` method works.
- Duck typing is idiomatic Python.

### 2.5 Threading model for analysis

**Decision: Run analyzers on the existing `ThreadPoolExecutor` inside
`do_queries`, NOT on a separate executor.**

Rationale:
- The `PatternAnalyzer` is fast (regex, microseconds). No reason to defer it.
- Running it synchronously inside `_store_result` (after parsing comments)
  keeps the code simple and deterministic.
- When the future `LLMAnalyzer` arrives, it *will* need async/deferred
  execution. At that point, introduce a `plugin_executor`. Don't build the
  infrastructure now.

For this EPIC: analysis runs inline in `_store_result`. The analyzer is called
after comments are parsed and Verified -1/-2 is detected. Since `_store_result`
already runs on a background thread (inside `do_queries`'s ThreadPoolExecutor),
the UI is not blocked.

### 2.6 Display

**Decision: Show the analyzer report in the existing Comments column (feature
005), appended below user comments with distinct styling.**

Alternatives considered:
- *New column* — adds horizontal space pressure; the table already has 6
  columns after feature 005.
- *Replace the Approvals column for failing changes* — loses useful info (which
  labels failed, who set them).
- *Expandable row detail* — not supported by Rich's Table.

**Implementation:** If an analyzer report exists, append it to the Comments
column with a `dim cyan` style and a `---` separator from user comments. If
there are no user comments, just show the report directly.

Example rendering:
```
Comments                          | Approvals
my note about this change         | Verified: -1 (Jenkins)
---                               | Code-Review: +2 (Alice)
FAILURE: pre_commit_gate #99560   |
ABORTED: emulator_gate #20278    |
```

### 2.7 Configuration

```toml
[config]
interval = 30
default_host = "gerrit.example.com"

[analyzer]
type = "pattern"   # "pattern" or "none" (future: "llm")

[analyzer.pattern]
# Regex patterns to extract from comments. Each pattern is tried against
# each comment message. Named group 'report' is used if present, otherwise
# the full match.
patterns = [
    '(?P<report>https?://\S+\s*:\s*(?:FAILURE|ABORTED|UNSTABLE))',
    '(?P<report>Build Failed.*)',
]
# Optional: only analyze comments from reviewers matching this pattern
reviewer_filter = "(?i)jenkins|zuul|ci-bot"
```

If `[analyzer]` section is absent, no analysis is performed (backward
compatible).

---

## 3. Data Flow

```
Refresh cycle starts
  |
  v
do_queries() — for each non-disabled, non-deleted change:
  |
  v
SSH: gerrit query --format=json --all-approvals --comments <hash>
  |
  v
_store_result(ch, data):
  1. Parse approvals (existing logic)
  2. Parse comments -> ch.gerrit_comments (NEW)
  3. Check if Verified -1 or -2 in approvals
  4. If yes and analyzer configured:
       report = analyzer.analyze(ch.gerrit_comments)
       ch.analyzer_report = report
  5. If no: ch.analyzer_report = None
  |
  v
refresh_done.set()
  |
  v
Main loop: visual_update(live)
  |
  v
build_table(): renders ch.analyzer_report in Comments column
```

---

## 4. Sub-Feature Breakdown

### EPIC003-001 | Fetch Gerrit comments via SSH

- Modify `query_approvals` in `gerrit.py` to always include `--comments` flag.
- Parse the `"comments"` array from the response.
- Add `GerritComment` dataclass to `models.py`.
- Add `gerrit_comments: list[GerritComment]` field to `TrackedChange` (in-memory
  only).
- Populate `gerrit_comments` in `_store_result`.

**Scope:** SSH layer + model + parsing. No display, no analysis.

### EPIC003-002 | Analyzer Protocol and PatternAnalyzer

- Define `Analyzer` Protocol in a new `analyzers.py` module.
- Implement `PatternAnalyzer` class:
  - Configurable regex patterns.
  - Optional reviewer filter (only analyze comments from CI bots).
  - Returns extracted failure lines joined by newline.
- Unit tests for `PatternAnalyzer` with various comment formats.

**Scope:** Pure logic, no integration with app yet.

### EPIC003-003 | Analyzer configuration in TOML

- Add `[analyzer]` and `[analyzer.pattern]` sections to TOML parsing in
  `config.py`.
- Extend `AppConfig` with analyzer config fields.
- Add `AnalyzerConfig` dataclass.
- Factory function: `create_analyzer(config) -> Analyzer | None`.
- Update `approvals.schema.json` (if applicable to TOML — currently it's for
  the JSON changes file, so this may not apply).

**Scope:** Config parsing + factory. No runtime integration.

### EPIC003-004 | Integrate analyzer into refresh cycle

- Wire `_store_result` to call `analyzer.analyze()` when Verified -1/-2.
- Store result in `ch.analyzer_report`.
- Pass analyzer instance from `App.__init__` through to `_store_result`.
- Handle analyzer returning `None` (no report) vs empty string.
- Clear `analyzer_report` when verification status changes (e.g., new patchset
  passes).

**Scope:** Integration glue between sub-features 001, 002, 003.

### EPIC003-005 | Display analyzer report in dashboard

- Modify `build_table` in `display.py` to render `ch.analyzer_report`.
- Show below user comments with `dim cyan` style and `---` separator.
- Show "analyzing..." placeholder while report is pending (if we add async
  later).
- Handle long reports gracefully (truncate or wrap).

**Scope:** Display only.

### EPIC003-006 | Expose analyzer report over MCP

- Extend `_get_changes` payload in `mcp_background.py` to include
  `analyzer_report` and `gerrit_comments`.

**Scope:** MCP layer only.

---

## 5. What Is Explicitly Deferred

### LLM Analyzer (future EPIC)

The LLM analyzer is architecturally more complex:
- External HTTP dependency (API key, network, latency).
- Needs async/deferred execution (seconds, not microseconds).
- Requires a separate `ThreadPoolExecutor` or async pattern.
- Cost implications (per-token pricing).
- Prompt engineering and model selection.

**When the LLM EPIC arrives, the changes needed are:**
1. Add `LLMAnalyzer` implementing the same `Analyzer` Protocol.
2. Add `[analyzer.llm]` config section.
3. Introduce `plugin_executor` for deferred analysis.
4. Add `analyzer_report_pending` field to `TrackedChange`.
5. Show "analyzing..." placeholder in display while pending.

The `Analyzer` Protocol is designed to accommodate this without changes.
The LLM analyzer just has a slower `analyze()` method, which is why it needs
the deferred execution path.

### Plugin Discovery/Registration

Not needed until there are 3+ analyzers from different sources. The current
factory function (`create_analyzer`) is sufficient. If needed later, a simple
entry-point based discovery can be added without changing the `Analyzer`
Protocol.

---

## 6. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `--comments` flag not supported on target Gerrit version | Low | High | Check Gerrit version; fall back gracefully if flag is unsupported |
| Comment format varies wildly across orgs | High | Medium | Configurable regex patterns; provide sensible defaults |
| SSH overhead of `--comments` on every query | Low | Low | Comments are small; a few extra KB per query is negligible |
| Pattern analyzer produces noisy/useless output | Medium | Medium | Reviewer filter reduces noise; user can tune patterns |
| Feature 005 not merged yet | Medium | Medium | EPIC003-005 (display) depends on feature 005's Comments column; other sub-features don't |

---

## 7. Implementation Order

```
EPIC003-001 (SSH + model)     — no dependencies
EPIC003-002 (PatternAnalyzer) — no dependencies
EPIC003-003 (config)          — no dependencies
    |
    v  (all three can be parallel)
EPIC003-004 (integration)     — depends on 001, 002, 003
    |
    v
EPIC003-005 (display)         — depends on 004; also depends on feature 005
EPIC003-006 (MCP)             — depends on 004
```

Sub-features 001, 002, 003 are independent and can be developed in any order
or in parallel. 004 is the integration point. 005 and 006 are leaf tasks.

---

## 8. Open Questions

1. **Should `--comments` be added to `query_approvals` or be a separate
   function?** Adding it to `query_approvals` is simpler (one SSH call) but
   changes the response shape for all callers. A flag parameter
   `include_comments=False` would be clean.

2. **Should the analyzer report be cached across refreshes?** Currently proposed
   as re-computed on every refresh. If the analyzer is fast (PatternAnalyzer),
   this is fine. For LLM (future), caching is essential — but that's deferred.

3. **How to handle the transition when a change goes from -1 to passing?** The
   analyzer report should be cleared. This is handled naturally: `_store_result`
   runs on every refresh, and if Verified is no longer -1/-2, `analyzer_report`
   is set to `None`.

4. **Should there be a keybind to manually trigger analysis?** Not for this
   EPIC. Analysis is automatic on refresh. A manual trigger adds complexity
   with little benefit since refreshes happen every 30s.
