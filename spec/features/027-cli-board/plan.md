# CLI Tracked Changes Board Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `gcd board`, which prints every TUI-tracked change from local cache without network access by default and refreshes successful cache entries only when `--reload` is supplied.

**Architecture:** Extend the tracked-change/cache model with optional Gerrit owner data, then add a focused `gcd/cli/board.py` orchestration module. The board runner always hydrates `changes.json` entries from `cache.json`; only its reload branch constructs or calls Gerrit communication, using concurrent queries while collecting output in file order. Output uses one normalized record schema and reuses the compact `query` table renderer.

**Tech Stack:** Python 3.12+, argparse, concurrent futures, JSON, Rich, pytest, Ruff.

---

## File Map

- Modify `gcd/core/models.py`: add optional raw Gerrit owner data to `TrackedChange`.
- Modify `gcd/core/cache.py`: persist and hydrate optional owner data while remaining compatible with old cache files.
- Modify `gcd/tui/app.py`: capture owner during normal TUI refresh; register and dispatch the new CLI command.
- Create `gcd/cli/board.py`: cache hydration, normalized records, table/JSON output, optional concurrent reload, and aggregate exit status.
- Modify `gcd/cli/query.py`: make compact table rendering tolerate normalized board records with unavailable fields.
- Modify `tests/test_cache_persistence.py`: cover owner round-trip and old-cache compatibility.
- Create `tests/test_cli_board.py`: cover cache-only behavior, reload behavior, ordering, output, errors, and CLI dispatch.
- Modify `README.md`: document `board`, `--json`, and `--reload` with the no-network default.

No commit steps are included because repository operations must only be performed when explicitly requested.

## Task 1: Persist Optional Owner Data

**Files:**
- Modify: `gcd/core/models.py:60-83`
- Modify: `gcd/core/cache.py:10-67,124-154`
- Modify: `gcd/tui/app.py:58-81`
- Modify: `tests/test_cache_persistence.py`

- [ ] **Step 1: Write failing owner cache tests**

Append to `tests/test_cache_persistence.py`:

```python
def test_owner_round_trips_through_cache(tmp_path):
    path = tmp_path / "cache.json"
    cache = SshCache(path)
    source = TrackedChange(
        number=1,
        instance="prod",
        owner={"name": "Jane Doe", "email": "jane@example.com"},
    )

    cache.cache(source)
    assert cache.save_file() is True

    target = TrackedChange(number=1, instance="prod")
    SshCache(path).hydrate(target)

    assert target.owner == {"name": "Jane Doe", "email": "jane@example.com"}


def test_cache_without_owner_remains_readable(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text(
        json.dumps(
            {
                "1:prod": {
                    "subject": "cached subject",
                    "project": "team/project",
                    "url": None,
                    "current_revision": None,
                    "current_patchset_number": None,
                    "submitted": False,
                    "abandoned": False,
                    "is_wip": False,
                    "approvals": [],
                }
            }
        )
        + "\n"
    )
    target = TrackedChange(number=1, instance="prod")

    SshCache(path).hydrate(target)

    assert target.subject == "cached subject"
    assert target.owner is None
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```bash
uv run pytest tests/test_cache_persistence.py -v
```

Expected: `test_owner_round_trips_through_cache` fails because `TrackedChange` does not accept `owner`.

- [ ] **Step 3: Add owner to the tracked and cached models**

In `gcd/core/models.py`, add the field beside the other Gerrit-derived data:

```python
    # --- data from gerrit ---
    subject: str | None = None
    project: str | None = None
    owner: dict | None = None
    url: str | None = None
```

In `gcd/core/cache.py`, add the corresponding `CacheEntry` field and mappings:

```python
@dataclass
class CacheEntry:
    subject: str | None = None
    project: str | None = None
    owner: dict | None = None
    url: str | None = None
```

Add `owner=ch.owner.copy() if ch.owner else None` to `CacheEntry.from_change`.
Add `"owner": self.owner` to `CacheEntry.to_json`.
Add `owner=data.get("owner") if isinstance(data.get("owner"), dict) else None` to `CacheEntry.from_json`.
Add this assignment to `SshCache.hydrate`:

```python
        ch.owner = entry.owner.copy() if entry.owner else None
        ch.current_patchset_number = entry.current_patchset_number
```

The patch-set assignment fixes the existing omission so normalized cached JSON
matches freshly reloaded JSON.

- [ ] **Step 4: Capture owner during ordinary TUI refresh**

In `gcd/tui/app.py::_store_result`, add the assignment with the other Gerrit fields:

```python
    ch.subject = data.get("subject")
    ch.project = data.get("project")
    owner = data.get("owner")
    ch.owner = owner.copy() if isinstance(owner, dict) else None
    ch.url = data.get("url")
```

This ensures normal TUI refreshes populate owner for later cache-only board runs.

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run pytest tests/test_cache_persistence.py tests/test_app_behaviors.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Run Ruff on the touched model/cache files**

Run:

```bash
uv run ruff check gcd/core/models.py gcd/core/cache.py gcd/tui/app.py tests/test_cache_persistence.py
```

Expected: no lint errors.

## Task 2: Implement Cache-Only Board Output

**Files:**
- Create: `gcd/cli/board.py`
- Modify: `gcd/cli/query.py:90-108`
- Create: `tests/test_cli_board.py`

- [ ] **Step 1: Create cache-only board tests and helpers**

Create `tests/test_cli_board.py` with imports and helpers:

```python
from __future__ import annotations

import argparse
import json
from io import StringIO
from threading import Event

from rich.console import Console

from gcd.cli.board import run
from gcd.core.cache import SshCache
from gcd.core.models import ApprovalEntry, TrackedChange


class FailIfCalledGerrit:
    def query_change(self, instance, change_id):
        raise AssertionError("plain board must not query Gerrit")


def _args(*, json_output: bool = False, reload: bool = False) -> argparse.Namespace:
    return argparse.Namespace(json=json_output, reload=reload)


def _track(config, *entries: dict) -> None:
    config.changes_path.write_text(json.dumps(list(entries)) + "\n")


def _cache(config, *changes: TrackedChange) -> None:
    cache = SshCache(config.cache_path)
    for change in changes:
        cache.cache(change)
    cache.save_file()


def _console() -> tuple[Console, StringIO]:
    stream = StringIO()
    return Console(file=stream, force_terminal=False, width=120), stream
```

Then add the initial behavior tests:

```python
def test_plain_board_reads_cache_without_querying(config):
    _track(config, {"number": 101, "instance": "prod"})
    _cache(
        config,
        TrackedChange(
            number=101,
            instance="prod",
            subject="Cached subject",
            project="team/project",
            owner={"name": "Jane Doe"},
            url="https://gerrit.example.com/c/101",
        ),
    )
    console, output = _console()

    status = run(config, _args(), comm=FailIfCalledGerrit(), console=console)

    assert status == 0
    assert "Cached subject" in output.getvalue()
    assert "Jane Doe" in output.getvalue()


def test_plain_board_includes_all_local_states(config):
    entries = [
        {"number": 1, "instance": "prod"},
        {"number": 2, "instance": "prod", "waiting": True},
        {"number": 3, "instance": "prod", "disabled": True},
        {"number": 4, "instance": "prod", "deleted": True},
    ]
    _track(config, *entries)
    _cache(
        config,
        *(TrackedChange(number=n, instance="prod", subject=f"subject {n}") for n in range(1, 5)),
    )
    console, output = _console()

    status = run(config, _args(), comm=FailIfCalledGerrit(), console=console)

    assert status == 0
    assert all(f"subject {n}" in output.getvalue() for n in range(1, 5))


def test_plain_board_missing_cache_is_visible_and_fails(config, capsys):
    _track(config, {"number": 101, "instance": "prod"})
    console, output = _console()

    status = run(config, _args(), comm=FailIfCalledGerrit(), console=console)

    assert status == 1
    assert "101" in output.getvalue()
    assert "no cached data; run board --reload" in capsys.readouterr().err


def test_plain_board_does_not_rewrite_cache(config):
    _track(config, {"number": 101, "instance": "prod"})
    _cache(config, TrackedChange(number=101, instance="prod", subject="cached"))
    before = config.cache_path.read_bytes()
    console, _ = _console()

    run(config, _args(), comm=FailIfCalledGerrit(), console=console)

    assert config.cache_path.read_bytes() == before


def test_empty_board_succeeds_without_output(config):
    console, output = _console()

    status = run(config, _args(), comm=FailIfCalledGerrit(), console=console)

    assert status == 0
    assert output.getvalue() == ""
```

- [ ] **Step 2: Run cache-only tests and verify import failure**

Run:

```bash
uv run pytest tests/test_cli_board.py -v
```

Expected: test collection fails because `gcd.cli.board` does not exist.

- [ ] **Step 3: Implement normalized board records and cache-only run path**

Create `gcd/cli/board.py`:

```python
import argparse
import json
import sys
from collections import defaultdict

from rich.console import Console

from gcd.cli.query import render_table
from gcd.core.cache import SshCache
from gcd.core.changes import Changes
from gcd.core.config import AppConfig
from gcd.core.gerrit import GerritCommunication
from gcd.core.models import TrackedChange


def _record(ch: TrackedChange, error: str | None = None) -> dict:
    result = {
        "number": ch.number,
        "instance": ch.instance,
        "project": ch.project,
        "subject": ch.subject,
        "owner": ch.owner,
        "url": ch.url,
        "current_revision": ch.current_revision,
        "current_patchset_number": ch.current_patchset_number,
        "submitted": ch.submitted,
        "abandoned": ch.abandoned,
        "is_wip": ch.is_wip,
        "approvals": [
            {"label": approval.label, "value": approval.value, "by": approval.by}
            for approval in ch.approvals
        ],
    }
    if error is not None:
        result["error"] = error
    return result


def _render(console: Console, records: list[dict]) -> None:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[record["instance"]].append(
            {
                **record,
                "project": record["project"] or "?",
                "subject": record["subject"] or "?",
            }
        )
    for instance_name, instance_records in grouped.items():
        render_table(console, instance_name, instance_records)


def run(
    config: AppConfig,
    args: argparse.Namespace,
    comm: GerritCommunication | None = None,
    console: Console | None = None,
) -> int:
    changes = Changes(config.changes_path).get_all()
    if not changes:
        if args.json:
            print("[]")
        return 0

    cache = SshCache(config.cache_path)
    records: list[dict] = []
    for ch in changes:
        cached = cache.has(ch)
        cache.hydrate(ch)
        error = None if cached else "no cached data; run board --reload"
        records.append(_record(ch, error))

    if args.reload:
        records = _reload(config, changes, cache, comm)

    if args.json:
        print(json.dumps(records, indent=2))
    else:
        for record in records:
            if error := record.get("error"):
                print(
                    f"[{record['instance']}] change {record['number']}: {error}",
                    file=sys.stderr,
                )
        _render(console or Console(), records)

    return int(any("error" in record for record in records))
```

Add a temporary `_reload` stub below `_render` so cache-only tests can import the module:

```python
def _reload(config, changes, cache, comm):
    raise NotImplementedError
```

The `comm` parameter intentionally remains unused on the plain path. This lets tests prove that supplying a communication object cannot cause accidental queries.

- [ ] **Step 4: Make query table rendering accept unavailable normalized values**

In `gcd/cli/query.py::render_table`, normalize values before truncation/Text construction:

```python
        table.add_row(
            number_cell,
            _truncate_project(change.get("project") or "?"),
            Text(change.get("subject") or "?"),
            _owner_name(change),
        )
```

This does not change successful query output and allows board error rows to remain visible.

- [ ] **Step 5: Run cache-only tests**

Run:

```bash
uv run pytest tests/test_cli_board.py -v
```

Expected: the five cache-only tests pass.

- [ ] **Step 6: Add ordering and normalized JSON tests**

Append to `tests/test_cli_board.py`:

```python
def test_tables_follow_instance_first_appearance_and_row_order(config):
    _track(
        config,
        {"number": 1, "instance": "staging"},
        {"number": 2, "instance": "prod"},
        {"number": 3, "instance": "staging"},
    )
    _cache(
        config,
        TrackedChange(number=1, instance="staging", subject="first"),
        TrackedChange(number=2, instance="prod", subject="second"),
        TrackedChange(number=3, instance="staging", subject="third"),
    )
    console, output = _console()

    assert run(config, _args(), console=console) == 0

    text = output.getvalue()
    assert text.index("staging") < text.index("prod")
    assert text.index("first") < text.index("third")


def test_cached_json_uses_normalized_schema(config, capsys):
    _track(config, {"number": 101, "instance": "prod"})
    _cache(
        config,
        TrackedChange(
            number=101,
            instance="prod",
            subject="cached",
            project="team/project",
            owner={"name": "Jane Doe"},
            approvals=[ApprovalEntry("Code-Review", "2", "Reviewer")],
        ),
    )

    assert run(config, _args(json_output=True), comm=FailIfCalledGerrit()) == 0

    records = json.loads(capsys.readouterr().out)
    assert set(records[0]) == {
        "number",
        "instance",
        "project",
        "subject",
        "owner",
        "url",
        "current_revision",
        "current_patchset_number",
        "submitted",
        "abandoned",
        "is_wip",
        "approvals",
    }
    assert records[0]["approvals"] == [
        {"label": "Code-Review", "value": "2", "by": "Reviewer"}
    ]


def test_missing_cache_json_contains_identity_and_error(config, capsys):
    _track(config, {"number": 101, "instance": "prod"})

    assert run(config, _args(json_output=True), comm=FailIfCalledGerrit()) == 1

    record = json.loads(capsys.readouterr().out)[0]
    assert record["number"] == 101
    assert record["instance"] == "prod"
    assert record["error"] == "no cached data; run board --reload"
```

- [ ] **Step 7: Run board and existing query tests**

Run:

```bash
uv run pytest tests/test_cli_board.py -v
uv run ruff check gcd/cli/board.py gcd/cli/query.py tests/test_cli_board.py
```

Expected: all board tests pass and Ruff reports no errors.

## Task 3: Add Optional Concurrent Reload And Cache Persistence

**Files:**
- Modify: `gcd/cli/board.py`
- Modify: `tests/test_cli_board.py`

- [ ] **Step 1: Add a configurable Gerrit fake and reload tests**

Add to `tests/test_cli_board.py`:

```python
class FakeBoardGerrit:
    def __init__(self, responses: dict[tuple[str, str], dict]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str]] = []

    def query_change(self, instance, change_id):
        key = (instance.name, change_id)
        self.calls.append(key)
        return dict(self.responses[key])


class OutOfOrderGerrit(FakeBoardGerrit):
    def __init__(self, responses: dict[tuple[str, str], dict]) -> None:
        super().__init__(responses)
        self.second_completed = Event()

    def query_change(self, instance, change_id):
        key = (instance.name, change_id)
        self.calls.append(key)
        if change_id == "1":
            assert self.second_completed.wait(timeout=2)
        else:
            self.second_completed.set()
        return dict(self.responses[key])


def _gerrit_change(number: int, subject: str, owner: str = "Jane Doe") -> dict:
    return {
        "number": str(number),
        "project": "team/project",
        "subject": subject,
        "owner": {"name": owner},
        "url": f"https://gerrit.example.com/c/{number}",
        "status": "NEW",
        "wip": False,
        "currentPatchSet": {
            "number": "4",
            "revision": f"revision-{number}",
            "approvals": [
                {"type": "Code-Review", "value": "2", "by": {"name": "Reviewer"}}
            ],
        },
        "rawOnly": "must not leak",
    }
```

Add these tests:

```python
def test_reload_queries_every_state_and_persists_successes(config):
    entries = [
        {"number": 1, "instance": "prod"},
        {"number": 2, "instance": "prod", "waiting": True},
        {"number": 3, "instance": "prod", "disabled": True},
        {"number": 4, "instance": "prod", "deleted": True},
    ]
    _track(config, *entries)
    comm = FakeBoardGerrit(
        {("prod", str(n)): _gerrit_change(n, f"fresh {n}") for n in range(1, 5)}
    )
    console, _ = _console()

    assert run(config, _args(reload=True), comm=comm, console=console) == 0

    assert set(comm.calls) == {("prod", str(n)) for n in range(1, 5)}
    cached = SshCache(config.cache_path)
    target = TrackedChange(number=1, instance="prod")
    cached.hydrate(target)
    assert target.subject == "fresh 1"
    assert target.owner == {"name": "Jane Doe"}


def test_reload_unknown_instance_does_not_query_it(config, capsys):
    _track(
        config,
        {"number": 1, "instance": "retired"},
        {"number": 2, "instance": "prod"},
    )
    comm = FakeBoardGerrit({("prod", "2"): _gerrit_change(2, "fresh")})
    console, _ = _console()

    assert run(config, _args(reload=True), comm=comm, console=console) == 1

    assert comm.calls == [("prod", "2")]
    assert 'unknown instance "retired"' in capsys.readouterr().err


def test_failed_reload_keeps_stale_cache_and_saves_other_successes(config, capsys):
    _track(
        config,
        {"number": 1, "instance": "prod"},
        {"number": 2, "instance": "prod"},
    )
    _cache(
        config,
        TrackedChange(number=1, instance="prod", subject="stale one"),
        TrackedChange(number=2, instance="prod", subject="stale two"),
    )
    comm = FakeBoardGerrit(
        {
            ("prod", "1"): {"error": "connection failed"},
            ("prod", "2"): _gerrit_change(2, "fresh two"),
        }
    )
    console, output = _console()

    assert run(config, _args(reload=True), comm=comm, console=console) == 1

    text = output.getvalue()
    assert "stale one" in text
    assert "fresh two" in text
    assert "connection failed" in capsys.readouterr().err
    cache = SshCache(config.cache_path)
    first = TrackedChange(number=1, instance="prod")
    second = TrackedChange(number=2, instance="prod")
    cache.hydrate(first)
    cache.hydrate(second)
    assert first.subject == "stale one"
    assert second.subject == "fresh two"


def test_reload_json_uses_normalized_schema_and_file_order(config, capsys):
    _track(
        config,
        {"number": 1, "instance": "staging"},
        {"number": 2, "instance": "prod"},
    )
    comm = OutOfOrderGerrit(
        {
            ("staging", "1"): _gerrit_change(1, "first"),
            ("prod", "2"): _gerrit_change(2, "second"),
        }
    )

    assert run(config, _args(json_output=True, reload=True), comm=comm) == 0

    records = json.loads(capsys.readouterr().out)
    assert [record["number"] for record in records] == [1, 2]
    assert all("rawOnly" not in record for record in records)
    assert records[0]["current_patchset_number"] == 4
```

`OutOfOrderGerrit` blocks change 1 until change 2 completes, proving collection
uses tracked order without relying on sleep durations.

- [ ] **Step 2: Run reload tests and verify the stub fails**

Run:

```bash
uv run pytest tests/test_cli_board.py -v
```

Expected: cache-only tests pass; reload tests fail at `_reload` with `NotImplementedError`.

- [ ] **Step 3: Implement raw Gerrit response mapping**

In `gcd/cli/board.py`, import concurrency and approval types:

```python
from concurrent.futures import ThreadPoolExecutor

from gcd.core.models import ApprovalEntry, GerritInstance, TrackedChange
```

Add:

```python
def _apply_query_result(ch: TrackedChange, data: dict) -> None:
    ch.subject = data.get("subject")
    ch.project = data.get("project")
    owner = data.get("owner")
    ch.owner = owner.copy() if isinstance(owner, dict) else None
    ch.url = data.get("url")

    patch_set = data.get("currentPatchSet") or {}
    ch.current_revision = patch_set.get("revision")
    patchset_number = patch_set.get("number")
    ch.current_patchset_number = int(patchset_number) if patchset_number is not None else None
    ch.approvals = [
        ApprovalEntry(
            label=approval.get("type", "?"),
            value=approval.get("value", ""),
            by=(approval.get("by") or {}).get("name", ""),
        )
        for approval in patch_set.get("approvals", [])
    ]
    ch.submitted = any(approval.is_submitted() for approval in ch.approvals)
    ch.abandoned = data.get("status") == "ABANDONED"
    ch.is_wip = bool(data.get("wip", False))
```

- [ ] **Step 4: Replace the reload stub with ordered concurrent reload**

Use explicit optional result slots so `ThreadPoolExecutor` completion order cannot change output order:

```python
def _reload_one(
    comm: GerritCommunication,
    instance: GerritInstance,
    ch: TrackedChange,
) -> dict:
    return comm.query_change(instance, str(ch.number))


def _reload(
    config: AppConfig,
    changes: list[TrackedChange],
    cache: SshCache,
    comm: GerritCommunication | None,
) -> list[dict]:
    communication = comm or GerritCommunication()
    query_items: list[tuple[int, GerritInstance, TrackedChange]] = []
    records: list[dict | None] = [None] * len(changes)

    for index, ch in enumerate(changes):
        instance = config.get_instance_by_name(ch.instance)
        if instance is None:
            records[index] = _record(ch, f'unknown instance "{ch.instance}"')
        else:
            query_items.append((index, instance, ch))

    if query_items:
        with ThreadPoolExecutor(max_workers=len(query_items)) as pool:
            futures = [
                (index, ch, pool.submit(_reload_one, communication, instance, ch))
                for index, instance, ch in query_items
            ]
            for index, ch, future in futures:
                data = future.result()
                if "error" in data:
                    records[index] = _record(ch, str(data["error"]))
                    continue
                _apply_query_result(ch, data)
                cache.cache(ch)
                records[index] = _record(ch)

    cache.save_file()
    return [record for record in records if record is not None]
```

Keep `cache.save_file()` outside the query loop. Failed and unknown entries are never passed to `cache.cache`, so their prior entries remain unchanged.

- [ ] **Step 5: Run reload and cache tests**

Run:

```bash
uv run pytest tests/test_cli_board.py tests/test_cache_persistence.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Verify no Gerrit communication is constructed in plain mode**

Add this test using monkeypatch:

```python
def test_plain_board_does_not_construct_gerrit(config, monkeypatch):
    _track(config, {"number": 101, "instance": "prod"})
    _cache(config, TrackedChange(number=101, instance="prod", subject="cached"))
    console, _ = _console()

    def fail_constructor():
        raise AssertionError("plain board must not construct GerritCommunication")

    monkeypatch.setattr("gcd.cli.board.GerritCommunication", fail_constructor)

    assert run(config, _args(), console=console) == 0
```

- [ ] **Step 7: Run board tests and Ruff**

Run:

```bash
uv run pytest tests/test_cli_board.py -v
uv run ruff check gcd/cli/board.py tests/test_cli_board.py
uv run ruff format --check gcd/cli/board.py tests/test_cli_board.py
```

Expected: all tests pass; Ruff check and format check succeed.

## Task 4: Register The Command And Document It

**Files:**
- Modify: `gcd/tui/app.py:920-989`
- Modify: `tests/test_cli_board.py`
- Modify: `README.md:27-49`

- [ ] **Step 1: Add a failing parser dispatch test**

Append imports to `tests/test_cli_board.py`:

```python
import sys

import pytest

from gcd.tui import app as app_module
```

Add:

```python
@pytest.mark.parametrize(
    ("extra_args", "expected"),
    [
        ([], (False, False)),
        (["--json"], (True, False)),
        (["--reload"], (False, True)),
        (["--json", "--reload"], (True, True)),
    ],
)
def test_main_dispatches_board_flags(config_path, monkeypatch, extra_args, expected):
    received = []

    def fake_board_run(config, args):
        received.append((args.json, args.reload))
        return 7

    monkeypatch.setattr("gcd.cli.board.run", fake_board_run)
    monkeypatch.setattr(
        sys,
        "argv",
        ["gcd", "--config", str(config_path), "board", *extra_args],
    )

    with pytest.raises(SystemExit) as exit_info:
        app_module.main()

    assert exit_info.value.code == 7
    assert received == [expected]
```

- [ ] **Step 2: Run dispatch test and verify argparse rejects board**

Run:

```bash
uv run pytest tests/test_cli_board.py::test_main_dispatches_board_flags -v
```

Expected: all parameter cases fail because `board` is not a registered subcommand.

- [ ] **Step 3: Register and dispatch board**

In `gcd/tui/app.py::main`, import the runner beside query:

```python
    from gcd.cli.board import run as board_run
    from gcd.cli.query import run as query_run
```

After creating the query parser and its arguments, register board:

```python
    board_parser = subparsers.add_parser(
        "board",
        help="Print tracked changes from local cache",
    )
    board_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of tables",
    )
    board_parser.add_argument(
        "--reload",
        action="store_true",
        help="Refresh tracked changes from Gerrit and update cache",
    )
```

Dispatch before TUI cache clearing/initialization:

```python
    if args.command == "query":
        sys.exit(query_run(config, args))
    if args.command == "board":
        sys.exit(board_run(config, args))
```

- [ ] **Step 4: Run parser dispatch and board tests**

Run:

```bash
uv run pytest tests/test_cli_board.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Document cache-only and reload usage**

Add a `CLI board` subsection after the custom-config usage in `README.md` with
this content (the four-space indentation below represents the nested code blocks
inside the Markdown example):

```markdown
### CLI board

Print every change currently tracked by the TUI using only local `cache.json`
data:

    uv run gcd board

The default command makes no Gerrit or SSH requests. Refresh tracked changes and
save successful results back to the cache explicitly:

    uv run gcd board --reload

Use `--json` with either mode for normalized machine-readable output:

    uv run gcd board --json
    uv run gcd board --reload --json
```

- [ ] **Step 6: Run the full verification suite**

Run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

Expected: Ruff check succeeds, all files are formatted, and the full pytest suite passes.

- [ ] **Step 7: Smoke-test help without network access**

Run:

```bash
uv run gcd board --help
```

Expected: help lists `--json` and `--reload`; no config, cache, or SSH access occurs because argparse exits after rendering help.

## Completion Checklist

- [ ] Plain `gcd board` constructs no Gerrit communication and makes no SSH requests.
- [ ] `--reload` queries every resolvable tracked entry, including disabled/deleted entries.
- [ ] Successful reloads persist once; failed reloads retain stale cache data.
- [ ] Existing cache files without owner remain readable.
- [ ] Table grouping and JSON records preserve tracked order.
- [ ] Cached and reload JSON use the same normalized schema.
- [ ] Missing cache and reload failures remain visible and return status `1`.
- [ ] Existing `query` and no-subcommand TUI behavior remain unchanged.
- [ ] README states that network access requires `--reload`.
