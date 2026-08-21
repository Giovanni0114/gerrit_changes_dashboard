from __future__ import annotations

import argparse
import json
import sys
from io import StringIO
from threading import Event

import pytest
from rich.console import Console

from gcd.cli.board import run
from gcd.cli.query import render_table
from gcd.core.cache import SshCache
from gcd.core.models import ApprovalEntry, TrackedChange
from gcd.tui import app as app_module


class FailIfCalledGerrit:
    def query_change(self, instance, change_id):
        raise AssertionError("plain board must not query Gerrit")


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


class ExternalCacheUpdateGerrit(FakeBoardGerrit):
    def __init__(self, config, responses: dict[tuple[str, str], dict]) -> None:
        super().__init__(responses)
        self.config = config

    def query_change(self, instance, change_id):
        external = SshCache(self.config.cache_path)
        external.cache(TrackedChange(number=99, instance="prod", subject="external update"))
        external.save_file()
        return super().query_change(instance, change_id)


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
            "approvals": [{"type": "Code-Review", "value": "2", "by": {"name": "Reviewer"}}],
        },
        "rawOnly": "must not leak",
    }


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


def test_query_renderer_keeps_missing_fields_blank():
    console, output = _console()

    render_table(console, "prod", [{"number": 101}])

    assert output.getvalue().count("?") == 1  # Existing Owner fallback only.


def test_plain_board_does_not_rewrite_cache(config):
    _track(config, {"number": 101, "instance": "prod"})
    _cache(config, TrackedChange(number=101, instance="prod", subject="cached"))
    before = config.cache_path.read_bytes()
    console, _ = _console()

    run(config, _args(), comm=FailIfCalledGerrit(), console=console)

    assert config.cache_path.read_bytes() == before


def test_empty_board_succeeds_without_table_output(config):
    console, output = _console()

    status = run(config, _args(), comm=FailIfCalledGerrit(), console=console)

    assert status == 0
    assert output.getvalue() == ""


def test_empty_board_json_is_empty_array(config, capsys):
    status = run(config, _args(json_output=True), comm=FailIfCalledGerrit())

    assert status == 0
    assert json.loads(capsys.readouterr().out) == []


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
    assert records[0]["approvals"] == [{"label": "Code-Review", "value": "2", "by": "Reviewer"}]


def test_missing_cache_json_contains_identity_and_error(config, capsys):
    _track(config, {"number": 101, "instance": "prod"})

    assert run(config, _args(json_output=True), comm=FailIfCalledGerrit()) == 1

    record = json.loads(capsys.readouterr().out)[0]
    assert record["number"] == 101
    assert record["instance"] == "prod"
    assert record["error"] == "no cached data; run board --reload"


def test_plain_board_does_not_construct_gerrit(config, monkeypatch):
    _track(config, {"number": 101, "instance": "prod"})
    _cache(config, TrackedChange(number=101, instance="prod", subject="cached"))
    console, _ = _console()

    def fail_constructor():
        raise AssertionError("plain board must not construct GerritCommunication")

    monkeypatch.setattr("gcd.cli.board.GerritCommunication", fail_constructor)

    assert run(config, _args(), console=console) == 0


def test_reload_queries_every_state_and_persists_successes(config):
    entries = [
        {"number": 1, "instance": "prod"},
        {"number": 2, "instance": "prod", "waiting": True},
        {"number": 3, "instance": "prod", "disabled": True},
        {"number": 4, "instance": "prod", "deleted": True},
    ]
    _track(config, *entries)
    comm = FakeBoardGerrit({("prod", str(n)): _gerrit_change(n, f"fresh {n}") for n in range(1, 5)})
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


def test_reload_exception_keeps_stale_cache_and_continues(config, capsys):
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

    class RaisingGerrit(FakeBoardGerrit):
        def query_change(self, instance, change_id):
            if change_id == "1":
                raise OSError("transport broke")
            return super().query_change(instance, change_id)

    comm = RaisingGerrit({("prod", "2"): _gerrit_change(2, "fresh two")})
    console, output = _console()

    assert run(config, _args(reload=True), comm=comm, console=console) == 1

    assert "stale one" in output.getvalue()
    assert "fresh two" in output.getvalue()
    assert "transport broke" in capsys.readouterr().err


def test_reload_preserves_external_cache_updates(config):
    _track(config, {"number": 1, "instance": "prod"})
    comm = ExternalCacheUpdateGerrit(config, {("prod", "1"): _gerrit_change(1, "fresh one")})
    console, _ = _console()

    assert run(config, _args(reload=True), comm=comm, console=console) == 0

    cache = SshCache(config.cache_path)
    external = TrackedChange(number=99, instance="prod")
    refreshed = TrackedChange(number=1, instance="prod")
    cache.hydrate(external)
    cache.hydrate(refreshed)
    assert external.subject == "external update"
    assert refreshed.subject == "fresh one"


def test_reload_saves_cache_once(config, monkeypatch):
    _track(
        config,
        {"number": 1, "instance": "prod"},
        {"number": 2, "instance": "prod"},
    )
    comm = FakeBoardGerrit(
        {
            ("prod", "1"): _gerrit_change(1, "fresh one"),
            ("prod", "2"): _gerrit_change(2, "fresh two"),
        }
    )
    save_count = 0
    original_save = SshCache.save_file

    def counted_save(cache):
        nonlocal save_count
        save_count += 1
        return original_save(cache)

    monkeypatch.setattr(SshCache, "save_file", counted_save)
    console, _ = _console()

    assert run(config, _args(reload=True), comm=comm, console=console) == 0
    assert save_count == 1


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
    monkeypatch.setattr(sys, "argv", ["gcd", "--config", str(config_path), "board", *extra_args])

    with pytest.raises(SystemExit) as exit_info:
        app_module.main()

    assert exit_info.value.code == 7
    assert received == [expected]
