import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor

from rich.console import Console

from gcd.cli.query import render_table
from gcd.core.cache import SshCache
from gcd.core.changes import Changes
from gcd.core.config import AppConfig
from gcd.core.gerrit import GerritCommunication
from gcd.core.models import ApprovalEntry, GerritInstance, TrackedChange


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
            {"label": approval.label, "value": approval.value, "by": approval.by} for approval in ch.approvals
        ],
    }
    if error is not None:
        result["error"] = error
    return result


def _render(console: Console, records: list[dict]) -> None:
    grouped: dict[str, list[dict]] = {}
    for record in records:
        grouped.setdefault(record["instance"], []).append(
            {
                **record,
                "project": record["project"] or "?",
                "subject": record["subject"] or "?",
            }
        )

    for instance_name, instance_records in grouped.items():
        render_table(console, instance_name, instance_records)


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


def _reload_one(comm: GerritCommunication, instance: GerritInstance, ch: TrackedChange) -> dict:
    return comm.query_change(instance, str(ch.number))


def _reload(
    config: AppConfig,
    changes: list[TrackedChange],
    comm: GerritCommunication | None,
) -> list[dict]:
    communication = comm or GerritCommunication()
    query_items: list[tuple[int, GerritInstance, TrackedChange]] = []
    records: list[dict | None] = [None] * len(changes)
    refreshed: list[TrackedChange] = []

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
                try:
                    data = future.result()
                except Exception as ex:
                    records[index] = _record(ch, str(ex))
                    continue
                if "error" in data:
                    records[index] = _record(ch, str(data["error"]))
                    continue
                _apply_query_result(ch, data)
                refreshed.append(ch)
                records[index] = _record(ch)

    if refreshed:
        latest_cache = SshCache(config.cache_path)
        for ch in refreshed:
            latest_cache.cache(ch)
        latest_cache.save_file()
    return [record for record in records if record is not None]


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
        records = _reload(config, changes, comm)

    if args.json:
        print(json.dumps(records, indent=2))
    else:
        for record in records:
            if error := record.get("error"):
                print(f"[{record['instance']}] change {record['number']}: {error}", file=sys.stderr)
        _render(console or Console(), records)

    return int(any("error" in record for record in records))
