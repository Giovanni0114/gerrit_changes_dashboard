# 025 — CLI `query` Tier-1 filters

## Problem

The `query` subcommand (016) exposes only 7 filters: `--mine`/`--owner`,
`--open`, `--submittable`, `--project`, `--mergedafter`, `--limit`. For a tool
whose whole point is *reviewing* changes, several high-value filters are missing:

- No **reviewer** filter — you cannot ask "changes I need to review", the single
  most common review-dashboard workflow.
- Only `is:open` status — no way to query **merged/abandoned/closed** history.
- No **activity-time** scoping (last-updated windows or "updated within N days").
- No **branch/topic** scoping.
- No **escape hatch** for arbitrary Gerrit operators, even though the server
  already accepts any operator string. Every new filter needs a code change.

Tier 1 closes these gaps. (Tiers 2 and 3 — `--label`, text search, file/path,
author/committer, etc. — are explicitly deferred; see *Out of scope*.)

## Scope

Extends the existing `query` subcommand only:

- `gcd/cli/query.py::build_query` gains the new flag → operator translations plus
  an `_validate_age` helper.
- The `query` argparse subparser in `gcd/tui/app.py::main()` gains the new
  arguments and two new mutually-exclusive groups, plus a trailing positional.

Read-only. Reuses the existing execution path (`query_operators` → `_query`) and
output path (Rich table / `--json`) from 016. Does **not** touch `changes.json`.

## CLI surface

Unchanged invocation shape (`gcd [-c/--config PATH] query [flags] [QUERY...]`).
New flags below; all existing 016 flags remain and behave identically.

### New `query` flags

| Flag | Type | Meaning |
|---|---|---|
| `--reviewer EMAIL` | str | Filter by reviewer = EMAIL. |
| `--to-review` | bool | Filter by reviewer = the instance's configured email. |
| `--merged` | bool | `is:merged`. |
| `--abandoned` | bool | `is:abandoned`. |
| `--closed` | bool | `is:closed`. |
| `--branch NAME` | str | `branch:NAME`. |
| `--topic NAME` | str | `topic:NAME`. |
| `--after DD-MM-YYYY` | str | `after:YYYY-MM-DD`. |
| `--before DD-MM-YYYY` | str | `before:YYYY-MM-DD`. |
| `--age DURATION` | str | `age:DURATION` (e.g. `2d`, `1w`, `3mon`). |
| `QUERY` (positional, `nargs="*"`) | str | Raw Gerrit operators, appended verbatim. |

### Mutually-exclusive groups

- **New:** `--reviewer` xor `--to-review` (mirrors `--mine` xor `--owner`).
- **New:** `--open` xor `--merged` xor `--abandoned` xor `--closed`. These would
  otherwise be AND-joined (`is:open is:merged` returns nothing), so they share one
  mutually-exclusive group. `--open` moves into this group but keeps emitting
  `is:open`. For status **OR** logic, use the raw positional (see below), e.g.
  `gcd query -- "status:merged OR status:abandoned"`.
- Existing `--instance` xor `--all-instances` and `--mine` xor `--owner` are
  unchanged.

### Raw positional query

- `QUERY` collects all trailing tokens (`nargs="*"`), joins them with a single
  space, and appends the result **verbatim** (unquoted — the user owns the
  syntax) as the last operator.
- Operators beginning with `-` (negation, e.g. `-is:wip`) collide with argparse
  option parsing. Use the standard `--` separator to pass them:
  `gcd query --mine -- -is:wip is:mergeable`.
- An empty positional appends nothing.

## Flag → Gerrit operator mapping

Operators are joined with a single space (Gerrit ANDs them). The empty query is
allowed and returns the server default.

| Flag | Operator emitted |
|---|---|
| `--reviewer EMAIL` | `reviewer:EMAIL` |
| `--to-review` | `reviewer:<instance.email>` |
| `--merged` | `is:merged` |
| `--abandoned` | `is:abandoned` |
| `--closed` | `is:closed` |
| `--branch NAME` | `branch:NAME` (quoted if not a bare word) |
| `--topic NAME` | `topic:NAME` (quoted if not a bare word) |
| `--after DD-MM-YYYY` | `after:YYYY-MM-DD` |
| `--before DD-MM-YYYY` | `before:YYYY-MM-DD` |
| `--age DURATION` | `age:DURATION` |
| `QUERY...` | the tokens, space-joined, appended verbatim |

Details:

- `--to-review` resolves the reviewer from `GerritInstance.email` (same
  resolution chain as `--mine`: instance email → `default_email` →
  `git config user.email`). If the resolved email is `None`/empty for an
  instance, that instance errors — same fatal path as `--mine` (see Errors).
- `--after` / `--before` reuse `convert_date` (`DD-MM-YYYY` → `YYYY-MM-DD`).
  Invalid dates raise `ValueError`, surfaced per-instance (matching the existing
  `--mergedafter` behaviour).
- `--age` is validated against Gerrit's duration grammar before emission:
  `\d+` followed by one unit of
  `s|sec|second|seconds | m|min|minute|minutes | h|hr|hour|hours | d|day|days |
  w|week|weeks | mon|month|months | y|year|years`. Invalid input raises
  `ValueError` (per-instance error, non-zero exit).
- `--branch` / `--topic` values are routed through the existing `_quote` helper
  (values outside Gerrit's bare-word set `A–Z a–z 0–9 @ - . _` are double-quoted).

### Deterministic operator order

`build_query` emits operators in a fixed order so table/JSON output and unit
tests are stable:

```
owner → reviewer → status → submittable → project → branch → topic
      → after → before → age → mergedafter → limit → raw
```

(`owner` = `--mine`/`--owner`; `reviewer` = `--to-review`/`--reviewer`;
`status` = whichever of `--open`/`--merged`/`--abandoned`/`--closed` is set.)

## Execution & Output

Unchanged from 016. `build_query` returns a `list[str]` of operators, passed to
`GerritCommunication.query_operators(instance, operators)`. Output is one Rich
table per instance (Number/Project/Subject/Owner) or a flat JSON array with the
added `"instance"` key under `--json`.

## Errors

Unchanged model from 016:

- `--to-review` against an instance with no resolvable email → clear per-instance
  message to stderr, non-zero exit.
- Invalid `--after`/`--before` date or invalid `--age` → `ValueError` in
  `build_query`, surfaced per-instance to stderr, non-zero exit.
- Per-instance SSH/query failures still surface as `{"error": ...}` dicts
  (stderr in table mode, included in the array in JSON mode); overall exit is
  non-zero if any instance failed.

## Code layout

- **Modify** `gcd/cli/query.py`:
  - Add `_validate_age(value: str) -> str` — validates the duration grammar,
    returns the value unchanged, raises `ValueError` on bad input.
  - Extend `build_query(args, instance_email)` with the new flags in the
    deterministic order above, including the raw positional (`args["raw"]`, a
    `list[str]`, space-joined and appended verbatim when non-empty).
- **Modify** `gcd/tui/app.py::main()`: add the new arguments to `query_parser`,
  the `--reviewer`/`--to-review` and status mutually-exclusive groups, and the
  trailing positional `raw` (`nargs="*"`).

The pure functions (`convert_date`, `_validate_age`, `build_query`) are the
primary unit-test targets; SSH is not exercised (mock at the
`GerritCommunication` seam if needed). Per 016's convention, temporary tests live
under `/tmp/opencode/` and are not committed.

## Out of scope (Tier 2 / Tier 3)

Deferred to later work: `--label`, `--message`/`--comment`, `--file`/`--path`,
`--author`/`--committer`, `--cc`, `--bug`/`--tr`, `--start` (pagination),
dedicated negation flags, and all caller-session/admin operators
(`is:starred`, `is:watched`, `has:draft`, `visibleto:`, named queries, etc.).
The raw positional query already provides an escape hatch for any of these.
