import argparse
import json
import re
import sys
from collections.abc import Mapping
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.text import Text

from gcd.core.config import AppConfig
from gcd.core.gerrit import GerritCommunication
from gcd.core.models import GerritInstance

_BARE_WORD = re.compile(r"^[A-Za-z0-9@._/-]+$")

PROJECT_WIDTH = 30


def convert_date(value: str) -> str:
    """Convert a DD-MM-YYYY date string into Gerrit's YYYY-MM-DD format."""
    parsed = datetime.strptime(value, "%d-%m-%Y")
    return parsed.strftime("%Y-%m-%d")


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


def _owner_name(change: dict) -> str:
    owner = change.get("owner") or {}
    return owner.get("name") or owner.get("email") or owner.get("username") or "?"


def _truncate_project(path: str, width: int = PROJECT_WIDTH) -> str:
    """Fit a project path into ``width`` chars.

    Drops leading ``/``-separated segments, replacing them with ``...``
    (``a/b/c/d`` -> ``.../b/c/d`` -> ``.../c/d`` -> ``.../d``). If the final
    segment alone still does not fit, its head is trimmed too, keeping the
    tail (``...restoftheword``).
    """
    if len(path) <= width:
        return path

    segments = path.split("/")
    for i in range(1, len(segments)):
        candidate = ".../" + "/".join(segments[i:])
        if len(candidate) <= width:
            return candidate

    last = segments[-1]
    tail_len = max(0, width - 3)
    return "..." + last[len(last) - tail_len :]


def render_table(console: Console, instance_name: str, changes: list[dict]) -> None:
    table = Table(title=instance_name, title_style="bold white reverse", expand=True)
    table.add_column("Number", style="magenta", no_wrap=True)
    table.add_column("Project", width=PROJECT_WIDTH, no_wrap=True)
    table.add_column("Subject", ratio=1)
    table.add_column("Owner", no_wrap=True)

    for change in changes:
        number = str(change.get("number", "?"))
        url = change.get("url")
        number_cell = Text(number, style=f"link {url}") if url else Text(number)
        table.add_row(
            number_cell,
            _truncate_project(change.get("project", "")),
            change.get("subject", ""),
            _owner_name(change),
        )

    console.print(table)


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
            if good:
                render_table(console, instance.name, good)

    if args.json:
        print(json.dumps(json_results, indent=2))

    return exit_code
