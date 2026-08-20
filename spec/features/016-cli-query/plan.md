# CLI `query` Subcommand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `gcd query` subcommand that runs an ad-hoc Gerrit search against one or all configured instances and prints results as a Rich table (one per instance) or as a JSON array.

**Architecture:** A new `gcd/cli/query.py` holds pure helpers (`convert_date`, `build_query`) plus an orchestrator (`run`) and a Rich renderer (`render_table`). `gcd/core/gerrit.py` gains a thin public `query_operators` wrapper over the existing `_query`. `gcd/tui/app.py::main()` is restructured to use argparse subparsers: no subcommand → TUI (default), `query` → CLI.

**Tech Stack:** Python 3.12+, argparse, Rich (`Console`, `Table`, `Text`), stdlib `json`/`datetime`, SSH via existing `GerritCommunication`.

**Constraints (from AGENTS.md + user):**
- Do NOT commit to `master`. Work on branch `feature/016-cli-query`.
- Do NOT commit tests. Temporary test files are for local verification only; delete or leave them uncommitted (they live under `/tmp` so they are never staged).
- Run `uv run ruff check . --fix && uv run ruff format .` before each commit.

---

## Task 0: Setup branch

**Files:** none (git only)

- [ ] **Step 1: Create and switch to the feature branch**

Run:
```bash
git checkout -b feature/016-cli-query
```
Expected: `Switched to a new branch 'feature/016-cli-query'`

---

## Task 1: `convert_date` helper (DD-MM-YYYY → YYYY-MM-DD)

**Files:**
- Create: `gcd/cli/__init__.py` (empty package marker)
- Create: `gcd/cli/query.py`
- Test: `/tmp/opencode/test_query_helpers.py` (temporary, not committed)

- [ ] **Step 1: Create the package marker**

Create `gcd/cli/__init__.py` with a single blank line (empty module).

- [ ] **Step 2: Write the failing test**

Create `/tmp/opencode/test_query_helpers.py`:
```python
import sys
sys.path.insert(0, "/home/jjurosze/repo/gerrit_changes_dashboard")

import pytest
from gcd.cli.query import convert_date


def test_convert_date_reformats_ddmmyyyy_to_iso():
    assert convert_date("20-06-2026") == "2026-06-20"


def test_convert_date_rejects_invalid():
    with pytest.raises(ValueError):
        convert_date("2026-06-20")

    with pytest.raises(ValueError):
        convert_date("31-02-2026")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest /tmp/opencode/test_query_helpers.py -v`
Expected: FAIL with `ImportError` / `cannot import name 'convert_date'`.

- [ ] **Step 4: Write minimal implementation**

Create `gcd/cli/query.py` with the imports and `convert_date`:
```python
from datetime import datetime


def convert_date(value: str) -> str:
    """Convert a DD-MM-YYYY date string into Gerrit's YYYY-MM-DD format."""
    parsed = datetime.strptime(value, "%d-%m-%Y")
    return parsed.strftime("%Y-%m-%d")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest /tmp/opencode/test_query_helpers.py -v`
Expected: PASS (both tests).

- [ ] **Step 6: Format and commit (source only, not the temp test)**

```bash
uv run ruff check . --fix && uv run ruff format .
git add gcd/cli/__init__.py gcd/cli/query.py
git commit -m "feat(cli): add convert_date helper for query subcommand"
```

---

## Task 2: `build_query` helper (flags → Gerrit operator list)

**Files:**
- Modify: `gcd/cli/query.py`
- Test: `/tmp/opencode/test_query_helpers.py` (temporary, extend it)

`build_query` is pure: it takes the parsed argparse values (as plain params) and the resolved instance email, and returns a list of Gerrit operator strings. It raises `ValueError` if `--mine` was requested but no email is available.

- [ ] **Step 1: Write the failing tests**

Append to `/tmp/opencode/test_query_helpers.py`:
```python
from gcd.cli.query import build_query


def _args(**kw):
    base = dict(
        mine=False, owner=None, open=False, submittable=False,
        project=None, mergedafter=None, limit=None,
    )
    base.update(kw)
    return base


def test_build_query_owner_open():
    ops = build_query(_args(owner="john.doe@example.com", open=True), instance_email=None)
    assert ops == ["owner:john.doe@example.com", "is:open"]


def test_build_query_mine_uses_instance_email():
    ops = build_query(_args(mine=True), instance_email="me@example.com")
    assert ops == ["owner:me@example.com"]


def test_build_query_mine_without_email_raises():
    with pytest.raises(ValueError):
        build_query(_args(mine=True), instance_email=None)


def test_build_query_submittable_and_project_and_limit():
    ops = build_query(
        _args(submittable=True, project="some/project/path", limit=25),
        instance_email=None,
    )
    assert ops == ["is:submittable", "project:some/project/path", "limit:25"]


def test_build_query_project_with_space_is_quoted():
    ops = build_query(_args(project="my project"), instance_email=None)
    assert ops == ['project:"my project"']


def test_build_query_mergedafter_reformats_date():
    ops = build_query(_args(mergedafter="20-06-2026"), instance_email=None)
    assert ops == ["mergedafter:2026-06-20"]


def test_build_query_empty_is_empty_list():
    assert build_query(_args(), instance_email=None) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest /tmp/opencode/test_query_helpers.py -v`
Expected: FAIL with `cannot import name 'build_query'`.

- [ ] **Step 3: Write minimal implementation**

Add to `gcd/cli/query.py` (below `convert_date`). Note the module takes a small `Mapping`-shaped dict for testability; the orchestrator will pass `vars(args)`:
```python
import re
from collections.abc import Mapping

_BARE_WORD = re.compile(r"^[A-Za-z0-9@._/-]+$")  # includes / so project paths stay unquoted


def _quote(value: str) -> str:
    """Wrap a Gerrit operator value in double quotes unless it is a bare word."""
    if _BARE_WORD.match(value):
        return value
    return f'"{value}"'


def build_query(args: Mapping, instance_email: str | None) -> list[str]:
    """Translate parsed flags into a list of Gerrit query operators."""
    operators: list[str] = []

    if args.get("mine"):
        if not instance_email:
            raise ValueError("--mine requires an email; none configured for this instance")
        operators.append(f"owner:{instance_email}")
    elif args.get("owner"):
        operators.append(f"owner:{args['owner']}")

    if args.get("open"):
        operators.append("is:open")

    if args.get("submittable"):
        operators.append("is:submittable")

    if args.get("project"):
        operators.append(f"project:{_quote(args['project'])}")

    if args.get("mergedafter"):
        operators.append(f"mergedafter:{convert_date(args['mergedafter'])}")

    if args.get("limit"):
        operators.append(f"limit:{args['limit']}")

    return operators
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest /tmp/opencode/test_query_helpers.py -v`
Expected: PASS (all tests, including Task 1's).

- [ ] **Step 5: Format and commit**

```bash
uv run ruff check . --fix && uv run ruff format .
git add gcd/cli/query.py
git commit -m "feat(cli): add build_query flags-to-operators helper"
```

---

## Task 3: `query_operators` wrapper on `GerritCommunication`

**Files:**
- Modify: `gcd/core/gerrit.py` (add method after `query_open_changes`, currently ending at line 124)
- Test: `/tmp/opencode/test_query_operators.py` (temporary, not committed)

- [ ] **Step 1: Write the failing test (mock the SSH seam)**

Create `/tmp/opencode/test_query_operators.py`:
```python
import sys
sys.path.insert(0, "/home/jjurosze/repo/gerrit_changes_dashboard")

from unittest.mock import MagicMock

from gcd.core.gerrit import GerritCommunication
from gcd.core.models import GerritInstance


def test_query_operators_delegates_to_query():
    comm = GerritCommunication()
    comm._query = MagicMock(return_value=[{"number": 1}])
    instance = GerritInstance("i", "host", 22, "e@x.com")

    result = comm.query_operators(instance, ["owner:e@x.com", "is:open"])

    comm._query.assert_called_once_with(instance, "owner:e@x.com", "is:open")
    assert result == [{"number": 1}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest /tmp/opencode/test_query_operators.py -v`
Expected: FAIL with `AttributeError: ... has no attribute 'query_operators'`.

- [ ] **Step 3: Add the method**

In `gcd/core/gerrit.py`, append inside the `GerritCommunication` class (after `query_open_changes`):
```python
    def query_operators(self, instance: GerritInstance, operators: list[str]) -> list[dict]:
        return self._query(instance, *operators)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest /tmp/opencode/test_query_operators.py -v`
Expected: PASS.

- [ ] **Step 5: Format and commit**

```bash
uv run ruff check . --fix && uv run ruff format .
git add gcd/core/gerrit.py
git commit -m "feat(gerrit): add query_operators public wrapper"
```

---

## Task 4: `render_table` (Rich, one table per instance)

**Files:**
- Modify: `gcd/cli/query.py`
- Test: manual visual check (no committed test)

Columns: Number (clickable link to `change["url"]`), Project, Subject, Owner.
Owner resolves from `change["owner"]` dict: prefer `name`, then `email`, then `username`, else `?`.

- [ ] **Step 1: Add imports and the owner helper + renderer**

At the top of `gcd/cli/query.py` add Rich imports (keep the existing `from datetime import datetime`, `import re`, `from collections.abc import Mapping`):
```python
from rich.console import Console
from rich.table import Table
from rich.text import Text
```

Add helper and renderer to `gcd/cli/query.py`:
```python
def _owner_name(change: dict) -> str:
    owner = change.get("owner") or {}
    return owner.get("name") or owner.get("email") or owner.get("username") or "?"


def render_table(console: Console, instance_name: str, changes: list[dict]) -> None:
    table = Table(title=instance_name, title_style="bold white reverse", expand=True)
    table.add_column("Number", style="magenta", no_wrap=True)
    table.add_column("Project", no_wrap=True)
    table.add_column("Subject")
    table.add_column("Owner", no_wrap=True)

    for change in changes:
        number = str(change.get("number", "?"))
        url = change.get("url")
        number_cell = Text(number, style=f"link {url}") if url else Text(number)
        table.add_row(
            number_cell,
            change.get("project", ""),
            change.get("subject", ""),
            _owner_name(change),
        )

    console.print(table)
```

- [ ] **Step 2: Manual smoke test of the renderer**

Run:
```bash
uv run python -c "
from rich.console import Console
from gcd.cli.query import render_table
render_table(Console(), 'neo', [
    {'number': 123, 'url': 'https://gerrit/123', 'project': 'foo/bar', 'subject': 'Fix things', 'owner': {'name': 'Jane Doe'}},
])
"
```
Expected: a table titled `neo` with a `Number` column showing `123` (as a link) and an `Owner` column showing `Jane Doe`.

- [ ] **Step 3: Format and commit**

```bash
uv run ruff check . --fix && uv run ruff format .
git add gcd/cli/query.py
git commit -m "feat(cli): add render_table for query results"
```

---

## Task 5: `run` orchestrator (instance selection, execution, output, exit code)

**Files:**
- Modify: `gcd/cli/query.py`
- Test: `/tmp/opencode/test_query_run.py` (temporary, not committed)

`run(config, args)` returns an int exit code. It:
1. Selects instances: `--instance NAME` (error if unknown), else `--all-instances` (all), else `config.default_instance`.
2. For each instance, resolves email, builds operators via `build_query`, queries via `config`-provided `GerritCommunication`, collects results.
3. On `--json`: prints a single JSON array of raw change dicts, each annotated with `"instance"`. Errors (dicts containing `"error"`) are included in the array.
4. Otherwise: renders one table per instance; error dicts are printed to stderr and skipped in the table.
5. Returns non-zero if any instance produced an error dict, or on fatal `--mine`/unknown-instance errors.

The `GerritCommunication` instance is passed in via a parameter (default constructs a fresh one) so it can be mocked in tests.

- [ ] **Step 1: Write the failing tests**

Create `/tmp/opencode/test_query_run.py`:
```python
import sys
sys.path.insert(0, "/home/jjurosze/repo/gerrit_changes_dashboard")

import argparse
import json
from unittest.mock import MagicMock

from gcd.cli.query import run
from gcd.core.models import GerritInstance


def _config(instances):
    cfg = MagicMock()
    cfg.instances = instances
    cfg.default_instance = instances[0]
    cfg.get_instance_by_name = lambda n: next((i for i in instances if i.name == n), None)
    return cfg


def _args(**kw):
    base = dict(
        instance=None, all_instances=False, mine=False, owner="x@y.com",
        open=True, submittable=False, project=None, mergedafter=None,
        limit=None, json=False,
    )
    base.update(kw)
    return argparse.Namespace(**base)


def test_run_unknown_instance_returns_nonzero(capsys):
    cfg = _config([GerritInstance("neo", "h", 22, "e@x.com")])
    code = run(cfg, _args(instance="nope"), comm=MagicMock())
    assert code != 0


def test_run_json_annotates_instance(capsys):
    cfg = _config([GerritInstance("neo", "h", 22, "e@x.com")])
    comm = MagicMock()
    comm.query_operators.return_value = [{"number": 1, "url": "u"}]
    code = run(cfg, _args(json=True), comm=comm)
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out == [{"number": 1, "url": "u", "instance": "neo"}]


def test_run_error_dict_sets_nonzero(capsys):
    cfg = _config([GerritInstance("neo", "h", 22, "e@x.com")])
    comm = MagicMock()
    comm.query_operators.return_value = [{"error": "boom"}]
    code = run(cfg, _args(json=True), comm=comm)
    assert code != 0


def test_run_all_instances_queries_each():
    inst = [GerritInstance("a", "h", 22, "e@x"), GerritInstance("b", "h", 22, "f@x")]
    cfg = _config(inst)
    comm = MagicMock()
    comm.query_operators.return_value = []
    run(cfg, _args(all_instances=True), comm=comm)
    assert comm.query_operators.call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest /tmp/opencode/test_query_run.py -v`
Expected: FAIL with `cannot import name 'run'`.

- [ ] **Step 3: Implement `run`**

Add to `gcd/cli/query.py`. Add these imports at the top: `import json`, `import sys`, `import argparse`, and `from gcd.core.config import AppConfig`, `from gcd.core.gerrit import GerritCommunication`, `from gcd.core.models import GerritInstance`:
```python
def _select_instances(config: AppConfig, args: argparse.Namespace) -> list[GerritInstance] | None:
    if args.instance:
        instance = config.get_instance_by_name(args.instance)
        if instance is None:
            print(f"Unknown instance: {args.instance}", file=sys.stderr)
            return None
        return [instance]
    if args.all_instances:
        return list(config.instances)
    return [config.default_instance]


def run(
    config: AppConfig,
    args: argparse.Namespace,
    comm: GerritCommunication | None = None,
) -> int:
    comm = comm or GerritCommunication()
    instances = _select_instances(config, args)
    if instances is None:
        return 1

    arg_map = vars(args)
    json_results: list[dict] = []
    console = Console()
    exit_code = 0

    for instance in instances:
        try:
            operators = build_query(arg_map, instance.email)
        except ValueError as ex:
            print(f"[{instance.name}] {ex}", file=sys.stderr)
            exit_code = 1
            continue

        changes = comm.query_operators(instance, operators)
        errored = any("error" in c for c in changes)
        if errored:
            exit_code = 1

        if args.json:
            for change in changes:
                json_results.append({**change, "instance": instance.name})
        else:
            good = [c for c in changes if "error" not in c]
            for c in changes:
                if "error" in c:
                    print(f"[{instance.name}] query error: {c['error']}", file=sys.stderr)
            render_table(console, instance.name, good)

    if args.json:
        print(json.dumps(json_results, indent=2))

    return exit_code
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest /tmp/opencode/test_query_run.py -v`
Expected: PASS (all four).

- [ ] **Step 5: Format and commit**

```bash
uv run ruff check . --fix && uv run ruff format .
git add gcd/cli/query.py
git commit -m "feat(cli): add query run orchestrator"
```

---

## Task 6: Wire subparsers into `main()`

**Files:**
- Modify: `gcd/tui/app.py:889-942` (the `main()` function)
- Test: manual CLI checks

Restructure `main()`: move config to a global `-c/--config` option, add a `query` subparser with all flags and the two mutually-exclusive groups, keep `--init`/`--clear-cache` as top-level flags used only on the TUI path. Dispatch: if `args.command == "query"` → `sys.exit(query_run(config, args))`; otherwise run the TUI.

- [ ] **Step 1: Replace `main()` with the subparser version**

Replace the entire body of `main()` (`gcd/tui/app.py:889-942`) with:
```python
def main() -> None:
    import argparse
    import sys

    from gcd.cli.query import run as query_run
    from gcd.core.config import generate_example_config
    from gcd.core.logs import setup_logging

    parser = argparse.ArgumentParser(description="Gerrit Changes Dashboard")
    parser.add_argument(
        "-c",
        "--config",
        default="config.toml",
        help="Path to TOML config file (default: config.toml)",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Generate example config.toml, then exit",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Delete the SSH data cache file before starting",
    )

    subparsers = parser.add_subparsers(dest="command")
    query_parser = subparsers.add_parser("query", help="Run a Gerrit search and exit")

    instance_group = query_parser.add_mutually_exclusive_group()
    instance_group.add_argument("--instance", help="Query a single configured instance by name")
    instance_group.add_argument(
        "--all-instances", action="store_true", help="Query every configured instance"
    )

    owner_group = query_parser.add_mutually_exclusive_group()
    owner_group.add_argument("--mine", action="store_true", help="Filter by the instance's own email")
    owner_group.add_argument("--owner", help="Filter by owner email")

    query_parser.add_argument("--open", action="store_true", help="is:open")
    query_parser.add_argument("--submittable", action="store_true", help="is:submittable")
    query_parser.add_argument("--project", help="project:PATH")
    query_parser.add_argument("--mergedafter", help="mergedafter:DATE (input DD-MM-YYYY)")
    query_parser.add_argument("--limit", type=int, help="limit:N")
    query_parser.add_argument("--json", action="store_true", help="Emit JSON instead of a table")

    args = parser.parse_args()
    config_path = Path(args.config)

    if args.init:
        generate_example_config(config_path)
        print(f"Created {config_path} - edit it and run again.")
        sys.exit(0)

    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        print("Run with --init to generate an example, or create it manually.")
        sys.exit(1)

    config = AppConfig(config_path)
    setup_logging(config.log_path)
    _log.info("startup config=%s logs=%s", config_path, config.log_path)

    if args.command == "query":
        sys.exit(query_run(config, args))

    if args.clear_cache:
        config.cache_path.unlink(missing_ok=True)
        _log.info("cleared cache=%s", config.cache_path)

    with NoEcho():
        app = App(config)
        app.run()
```

- [ ] **Step 2: Verify the TUI path still parses (no subcommand)**

Run: `uv run gcd --help`
Expected: help text shows `-c/--config`, `--init`, `--clear-cache`, and a `query` subcommand.

Run: `uv run gcd query --help`
Expected: help lists `--instance/--all-instances`, `--mine/--owner`, `--open`, `--submittable`, `--project`, `--mergedafter`, `--limit`, `--json`.

- [ ] **Step 3: Verify argparse rejects conflicting flags**

Run: `uv run gcd query --instance x --all-instances`
Expected: argparse error `not allowed with argument`.

Run: `uv run gcd query --mine --owner a@b.com`
Expected: argparse error `not allowed with argument`.

- [ ] **Step 4: Format and commit**

```bash
uv run ruff check . --fix && uv run ruff format .
git add gcd/tui/app.py
git commit -m "feat(cli): wire query subparser into main()"
```

---

## Task 7: End-to-end verification against real config

**Files:** none (verification only)

- [ ] **Step 1: JSON output smoke test**

Run (uses the real `config.toml` and live SSH; pick a real instance name from config):
```bash
uv run gcd query --instance gerrit --owner "$(git config user.email)" --open --limit 5 --json
```
Expected: a JSON array on stdout; each element has an `"instance": "gerrit"` key. Exit code `0` (`echo $?`).

- [ ] **Step 2: Table output smoke test**

Run:
```bash
uv run gcd query --instance gerrit --mine --open --limit 5
```
Expected: a Rich table titled `gerrit` with Number/Project/Subject/Owner columns; Numbers are clickable links.

- [ ] **Step 3: all-instances smoke test**

Run:
```bash
uv run gcd query --all-instances --mine --open --limit 3
```
Expected: one table per configured instance, each titled with its name.

- [ ] **Step 4: Clean up temporary tests**

Run:
```bash
rm -f /tmp/opencode/test_query_helpers.py /tmp/opencode/test_query_operators.py /tmp/opencode/test_query_run.py
```

---

## Self-Review notes

- **Spec coverage:** instance selection (Task 5), flag→operator mapping incl. mine/owner/open/submittable/project/mergedafter/limit (Task 2), date reformat (Task 1), `query_operators` reuse of `_query` (Task 3), one-table-per-instance + clickable Number + Owner column (Task 4), JSON flat array annotated with instance incl. error objects (Task 5), global `-c/--config` + subparsers + mutual exclusivity + TUI default (Task 6), error handling and exit codes (Task 5), end-to-end (Task 7). All spec sections map to a task.
- **No placeholders:** every code step shows full code; every run step shows the command and expected result.
- **Type consistency:** `build_query(args: Mapping, instance_email)`, `render_table(console, instance_name, changes)`, `run(config, args, comm=None) -> int`, `query_operators(instance, operators: list[str])` are used consistently across tasks. `run` passes `vars(args)` (a dict, satisfies `Mapping`) into `build_query`.
- **Tests not committed:** all test files live under `/tmp/opencode/` and are deleted in Task 7; only source commits are staged.
