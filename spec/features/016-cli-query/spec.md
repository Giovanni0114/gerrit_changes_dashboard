# 016 — CLI `query` subcommand

## Problem

The dashboard is TUI-only. There is no way to run a one-off Gerrit search from
the shell, script it, or pipe results into other tools. Spike 014 concluded that
a CLI over the existing decoupled modules (`gerrit.py`, `config.py`,
`changes.py`) serves both humans and AI assistants better than MCP. This is the
first concrete CLI feature: a `query` subcommand that runs a Gerrit search
against configured instances and prints results as a Rich table or JSON.

## Scope

First iteration covers ad-hoc Gerrit change search. It does **not** touch
`changes.json` (tracked changes) — it is a read-only query tool.

Target invocations:

```
gcd query --all-instances --mine --mergedafter="20-06-2026"
gcd query --instance="old-gerrit" --owner="john.doe@example.com" --submittable --project="some/project/path"
gcd query --json --instance="old-gerrit" --owner="john.doe@example.com" --open
```

## CLI surface

```
gcd [-c/--config PATH] query [flags]
```

- No subcommand → launch the TUI (unchanged default behaviour).
- `query` subcommand → run a search and exit.

**Config becomes a global `-c/--config` option** (default `config.toml`),
replacing the current optional positional `config` argument. This is required
because argparse subparsers cannot cleanly coexist with an optional leading
positional (`gcd query ...` would otherwise consume `query` as the config path).
`gcd` with no arguments still launches the TUI against `config.toml`.
`--init` and `--clear-cache` remain top-level flags on the TUI path.

### `query` flags

| Flag | Type | Meaning |
|---|---|---|
| `--instance NAME` | str | Query a single instance (looked up by config name). |
| `--all-instances` | bool | Query every configured instance. |
| `--mine` | bool | Filter by owner = the instance's configured email. |
| `--owner EMAIL` | str | Filter by owner = EMAIL. |
| `--open` | bool | `is:open`. |
| `--submittable` | bool | `is:submittable`. |
| `--project PATH` | str | `project:PATH`. |
| `--mergedafter DD-MM-YYYY` | str | `mergedafter:YYYY-MM-DD`. |
| `--limit N` | int | `limit:N`. |
| `--json` | bool | Emit JSON instead of a Rich table. |

**Mutually exclusive groups:**
- `--instance` xor `--all-instances`. Neither given → the default instance
  (`AppConfig.default_instance`, the first configured instance).
- `--mine` xor `--owner`.

## Flag → Gerrit operator mapping

Operators are joined with a single space (Gerrit ANDs them). Empty query
(no operators) is allowed and returns the server default.

| Flag | Operator emitted |
|---|---|
| `--mine` | `owner:<instance.email>` |
| `--owner EMAIL` | `owner:EMAIL` |
| `--open` | `is:open` |
| `--submittable` | `is:submittable` |
| `--project PATH` | `project:PATH` |
| `--mergedafter DD-MM-YYYY` | `mergedafter:YYYY-MM-DD` |
| `--limit N` | `limit:N` |

- `--mine` resolves the owner from `GerritInstance.email` (which itself falls
  back to `default_email` then `git config user.email`). If the resolved email
  is `None`/empty for an instance, that instance errors (see Errors).
- `--project` values containing characters outside Gerrit's bare-word set
  (A–Z a–z 0–9 @ - . _) are wrapped in double quotes.
- `--mergedafter` input is `DD-MM-YYYY`; it is reformatted to Gerrit's
  `YYYY-MM-DD`. Invalid dates are a fatal argument error.

## Execution

Reuse the existing query path. `GerritCommunication._query(instance, *args)`
already builds `ssh -x -p <port> <host> gerrit query --format=json
--current-patch-set <args...>`, drops the trailing `stats` line, and returns a
list of raw JSON dicts. Add a thin public wrapper:

```python
def query_operators(self, instance: GerritInstance, operators: list[str]) -> list[dict]:
    return self._query(instance, *operators)
```

For `--all-instances`, iterate instances and query each independently.

## Output

### Human (default): Rich, one table per instance

- Table title = instance name.
- Columns: **Number**, **Project**, **Subject**, **Owner**.
  - **Number** is a clickable link to the change's `url` field (Rich `link`
    markup), mirroring the TUI's clickable number.
  - **Owner** = `change["owner"]["name"]` (fallback to email/username/`?`).
- No comments and no approvals columns.
- Row order follows Gerrit's returned order; numbering (if any) restarts per
  table.
- Tables are stacked in config instance order.

### JSON (`--json`)

- A single flat JSON array printed with `json.dumps(..., indent=2)`.
- Each element is the **raw** Gerrit change object (all retrieved fields), with
  an added `"instance": "<name>"` key identifying its source instance.
- No Rich, no table — plain stdout suitable for piping.

## Errors

- `--mine` against an instance with no resolvable email → print a clear message
  to stderr and exit non-zero (before running queries).
- A per-instance SSH/query failure surfaces as a `{"error": ...}` dict from
  `_query`. In table mode, print the error to stderr for that instance and
  continue with the remaining instances. In JSON mode, the error object is
  included in the array (annotated with its instance) so the failure is
  machine-visible. Overall exit code is non-zero if any instance failed.
- Unknown `--instance NAME` → clear message, exit non-zero.

## Code layout

- **New** `gcd/cli/__init__.py` and `gcd/cli/query.py`:
  - `convert_date(ddmmyyyy: str) -> str` — pure DD-MM-YYYY → YYYY-MM-DD.
  - `build_query(args, instance_email: str | None) -> list[str]` — pure
    flags → operator list (raises on missing `--mine` email).
  - `run(config: AppConfig, args: argparse.Namespace) -> int` — orchestrates
    instance selection, querying, and output; returns an exit code.
  - `render_table(console, instance_name, changes) -> None` — Rich rendering.
- **Modify** `gcd/core/gerrit.py`: add `query_operators`.
- **Modify** `gcd/tui/app.py::main()`: introduce argparse subparsers; move
  `config` to `-c/--config`; dispatch `query` → `gcd.cli.query.run`, otherwise
  run the TUI as today.

The pure functions (`convert_date`, `build_query`) are the primary unit-test
targets; SSH is not exercised in tests (mock at the `GerritCommunication` seam
if needed).
