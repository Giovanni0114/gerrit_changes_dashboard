#!/usr/bin/env python3

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread

from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text

from utils import NoEcho

DEFAULT_INTERVAL = 30


@dataclass
class Change:
    host: str
    hash: str
    waiting: bool = False
    deleted: bool = False


def load_config(path: Path) -> tuple[list[Change], int]:
    data = json.loads(path.read_text())
    interval = int(data.get("interval", DEFAULT_INTERVAL))
    if interval < 1:
        raise ValueError(f"interval must be >= 1, got {interval}")
    default_host = data.get("default_host", None)
    changes = []
    for entry in data.get("changes", []):
        host = entry.get("host", default_host)
        commit_hash = entry["hash"]
        if not host:
            raise ValueError(f"Change '{commit_hash}' has no host and no default_host is set")
        changes.append(Change(host=host, hash=commit_hash, waiting=bool(entry.get("waiting", False))))
    return changes, interval


def config_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def query_approvals(commit_hash: str, host: str) -> dict:
    cmd = [
        "ssh",
        "-x",
        host,
        "gerrit",
        "query",
        "--format=json",
        "--all-approvals",
        commit_hash,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        lines = result.stdout.strip().splitlines()
        if not lines:
            stderr = result.stderr.strip()
            msg = f"No output from Gerrit ({stderr})" if stderr else "No output from Gerrit"
            return {"error": msg}
        data = json.loads(lines[0])
        if "type" in data and data["type"] == "stats":
            return {"error": "Change not found"}
        return data
    except subprocess.TimeoutExpired:
        return {"error": "SSH timeout"}
    except (json.JSONDecodeError, IndexError) as exc:
        return {"error": str(exc)}


def format_value(value_str: str) -> Text:
    try:
        v = int(value_str)
    except (ValueError, TypeError):
        return Text(value_str)
    if v >= 2:
        return Text(f"+{v}", style="bold green")
    if v == 1:
        return Text(f"+{v}", style="green")
    if v == 0:
        return Text(f" {v}", style="dim")
    if v == -1:
        return Text(str(v), style="yellow")
    return Text(str(v), style="bold red")


def build_table(
    changes: list[Change],
    results: dict[tuple[str, str], dict],
    config_path: str,
    interval: float,
    status_msg: str = "",
    prompt_msg: str = "",
) -> Table:
    """
    VIBE CODED, don't trust it
    """
    caption = (
        f"[dim]config:[/dim] {config_path} | [dim]interval:[/dim] {interval}s"
        f" | [dim]w[/dim] wait  [dim]d[/dim] delete  [dim]q[/dim] quit"
    )
    if status_msg:
        caption = f"{status_msg}\n{caption}"
    table = Table(
        title=f"Gerrit Approvals  (refreshed {datetime.now():%H:%M:%S})",
        caption=caption,
        expand=True,
        box=None,
        show_edge=False,
        row_styles=["", "on #1a1a2e"],
        pad_edge=False,
    )
    table.add_column("#", style="dim", no_wrap=True, width=3)
    table.add_column("Number", style="magenta", no_wrap=True)
    table.add_column("Commit", style="cyan", no_wrap=True)
    table.add_column("Subject", max_width=60)
    table.add_column("Project", no_wrap=True)
    table.add_column("Approvals")

    if prompt_msg:
        table.add_row("", "", "", Text(prompt_msg, style="bold yellow"), "", "")

    for idx, ch in enumerate(changes, 1):
        short = ch.hash[:7]
        data = results.get((ch.host, ch.hash), {})

        if ch.deleted:
            # Show minimal info for deleted rows
            subject = Text(data.get("subject", ""), style="strike dim")
            number_str = str(data.get("number", ""))
            table.add_row(
                str(idx),
                Text(number_str, style="dim"),
                Text(short, style="dim"),
                subject,
                Text(data.get("project", ""), style="dim"),
                Text("deleted", style="dim red"),
                style="on #1c1c1c",
            )
            continue

        if "error" in data:
            table.add_row(str(idx), "", short, Text(data["error"], style="red"), "", "")
            continue

        url = data.get("url", "")
        style = "magenta"
        if url:
            style += f" link {url}"
        number_text = Text(str(data.get("number", "")), style=style)

        subject = Text(data.get("subject", ""))
        project = data.get("project", "<unknown>")

        patch_sets = data.get("patchSets", [])
        approvals_text = Text()
        row_style = None
        if patch_sets:
            approvals = patch_sets[-1].get("approvals", [])
            is_submitted = any(appr.get("type", "?") == "SUBM" for appr in approvals)
            if is_submitted:
                approvals = [appr for appr in approvals if appr.get("type", "?") == "SUBM"]
            seen = set()
            for appr in approvals:
                key = (appr.get("type", ""), appr.get("by", {}).get("name", ""))
                if key in seen:
                    continue
                seen.add(key)

                if appr.get("type", "?") == "SUBM":
                    row_style = "on #019424"
                elif appr.get("value") in ("1", "2") and appr.get("type", "?") == "Verified":
                    row_style = row_style or "on #1e5944"
                elif appr.get("value") == "-2" and appr.get("type", "?") == "Verified":
                    row_style = "on #320000"
                elif appr.get("value") == "-1":
                    row_style = "on #8B4000"

                if approvals_text:
                    approvals_text.append("\n")
                approvals_text.append(f"{appr.get('type', '?')}: ")
                approvals_text.append_text(format_value(appr.get("value")))
                by_name = appr.get("by", {}).get("name", "")
                if by_name:
                    approvals_text.append(f" ({by_name})", style="dim")

        table.add_row(
            str(idx),
            number_text,
            short,
            subject,
            project,
            approvals_text,
            style="dim on #2a2a2a" if ch.waiting else row_style,
        )

    return table


def generate_example_config(path: Path):
    example = {
        "$schema": "./approvals.schema.json",
        "interval": 30,
        "changes": [
            {"host": "gerrit.example.com", "hash": "REPLACE_WITH_COMMIT_HASH"},
            {"host": "gerrit.example.com", "hash": "ANOTHER_HASH", "waiting": True},
        ],
    }
    path.write_text(json.dumps(example, indent=2) + "\n")


def _approval_snapshot(data: dict) -> frozenset[tuple[str, str, str]]:
    """Return a fingerprint of the current approvals for change-detection."""
    patch_sets = data.get("patchSets", [])
    if not patch_sets:
        return frozenset()
    approvals = patch_sets[-1].get("approvals", [])
    return frozenset(
        (appr.get("type", ""), appr.get("value", ""), appr.get("by", {}).get("name", "")) for appr in approvals
    )


def _clear_waiting_in_config(config_path: Path, commit_hash: str) -> float:
    """Set waiting=false for the given hash in the config file. Returns new mtime."""
    data = json.loads(config_path.read_text())
    for entry in data.get("changes", []):
        if entry.get("hash") == commit_hash:
            entry["waiting"] = False
    config_path.write_text(json.dumps(data, indent=2) + "\n")
    return config_mtime(config_path)


def _set_waiting_in_config(config_path: Path, commit_hash: str) -> float:
    """Set waiting=true for the given hash in the config file. Returns new mtime."""
    data = json.loads(config_path.read_text())
    for entry in data.get("changes", []):
        if entry.get("hash") == commit_hash:
            entry["waiting"] = True
    config_path.write_text(json.dumps(data, indent=2) + "\n")
    return config_mtime(config_path)


def main():
    parser = argparse.ArgumentParser(
        description="Config-file driven gerrit approvals dashboard ",
    )
    parser.add_argument(
        "config",
        nargs="?",
        default="approvals.json",
        help="Path to JSON config file (default: approvals.json)",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Generate an example config file and exit",
    )
    args = parser.parse_args()

    config_path = Path(args.config)

    if args.init:
        if config_path.exists():
            print(f"Config file already exists: {config_path}")
            sys.exit(1)
        generate_example_config(config_path)
        print(f"Example config written to {config_path} - edit it and run again.")
        sys.exit(0)

    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        print("Run with --init to generate an example, or create it manually.")
        sys.exit(1)

    console = Console()
    results: dict[tuple[str, str], dict] = {}
    submitted_keys: set[tuple[str, str]] = set()
    prev_approvals: dict[tuple[str, str], frozenset[tuple[str, str, str]]] = {}
    last_mtime = 0.0
    status_msg = ""

    try:
        changes, interval = load_config(config_path)
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        console.print(f"[red]Error loading config:[/red] {exc}")
        sys.exit(1)
    last_mtime = config_mtime(config_path)

    def _is_submitted(data: dict) -> bool:
        for ps in data.get("patchSets", []):
            if any(appr.get("type", "?") == "SUBM" for appr in ps.get("approvals", [])):
                return True
        return False

    def _do_queries() -> None:
        """Run SSH queries for all non-submitted, non-deleted changes. Updates results in place."""
        nonlocal last_mtime
        pending = [ch for ch in changes if (ch.host, ch.hash) not in submitted_keys and not ch.deleted]

        def _query(ch: Change) -> tuple[tuple[str, str], dict]:
            return (ch.host, ch.hash), query_approvals(ch.hash, ch.host)

        with ThreadPoolExecutor(max_workers=len(pending) or 1) as pool:
            for key, data in pool.map(_query, pending):
                results[key] = data
                if "error" not in data and _is_submitted(data):
                    submitted_keys.add(key)

                if "error" not in data:
                    snapshot = _approval_snapshot(data)
                    ch = next(c for c in changes if (c.host, c.hash) == key)
                    if ch.waiting and key in prev_approvals and snapshot != prev_approvals[key]:
                        ch.waiting = False
                        try:
                            last_mtime = _clear_waiting_in_config(config_path, ch.hash)
                        except OSError:
                            pass
                    prev_approvals[key] = snapshot

    def _build(prompt_msg: str = "") -> Table:
        """Build the display table from cached results."""
        return build_table(changes, results, str(config_path), interval, status_msg, prompt_msg)

    def should_reload() -> bool:
        nonlocal changes, interval, last_mtime, status_msg
        mtime = config_mtime(config_path)
        if mtime <= last_mtime:
            return False
        try:
            new_changes, new_interval = load_config(config_path)
            changes = new_changes
            interval = new_interval
            last_mtime = mtime

            valid_keys = {(ch.host, ch.hash) for ch in changes}
            for k in list(results):
                if k not in valid_keys:
                    del results[k]

            status_msg = "[green]Config reloaded[/green]"
            return True
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            status_msg = f"[red]Config error: {exc}[/red]"
            last_mtime = mtime
            return False

    def _build_prompt() -> str:
        if not input_state["active"]:
            return ""
        buf = input_state["buf"]
        action = input_state["action"]
        if action == "w":
            label = "Toggle waiting"
        else:
            label = "Toggle deleted"
        hint = f"{label} — enter row # (1-{len(changes)}): {buf}_  [ESC=cancel]"
        if action == "d" and not buf:
            hint += "  [a=all submitted  d=purge deleted  r=restore all]"
        return hint

    input_state: dict = {"active": False, "buf": "", "action": ""}
    key_queue: Queue[str] = Queue()

    def _key_reader() -> None:
        """Background thread: reads keys from stdin and puts them in the queue."""
        no_echo = NoEcho.instance
        if no_echo is None:
            return
        while True:
            k = no_echo.read_key(timeout=0.1)
            if k is not None:
                key_queue.put(k)

    reader_thread = Thread(target=_key_reader, daemon=True)
    reader_thread.start()

    # Run initial queries synchronously so the first display has data
    _do_queries()

    refresh_done = Event()
    refresh_done.set()  # no refresh in progress initially
    refresh_pending = False  # True while a bg refresh is in flight

    def _bg_refresh() -> None:
        """Background thread: run SSH queries then signal completion."""
        try:
            _do_queries()
        finally:
            refresh_done.set()

    try:
        with Live(_build(_build_prompt()), console=console, refresh_per_second=1, screen=True) as live:
            seconds_since_refresh = 0.0

            def _visual_update() -> None:
                """Redraw the table using cached results (no SSH queries)."""
                live.update(_build(_build_prompt()))

            def _start_refresh() -> None:
                """Kick off a background SSH refresh if one isn't running."""
                nonlocal seconds_since_refresh, refresh_pending
                if refresh_done.is_set():
                    refresh_done.clear()
                    refresh_pending = True
                    seconds_since_refresh = 0.0
                    Thread(target=_bg_refresh, daemon=True).start()

            while True:
                time.sleep(0.1)
                seconds_since_refresh += 0.1
                needs_visual_update = False

                # Check if background refresh just completed
                if refresh_pending and refresh_done.is_set():
                    refresh_pending = False
                    needs_visual_update = True

                # Process all pending keys
                while True:
                    try:
                        key = key_queue.get_nowait()
                    except Empty:
                        break

                    if input_state["active"]:
                        if key == "ESC":
                            input_state["active"] = False
                            input_state["buf"] = ""
                        elif key in ("\r", "\n"):
                            buf = input_state["buf"]
                            action = input_state["action"]
                            if buf.isdigit():
                                row_num = int(buf)
                                if 1 <= row_num <= len(changes):
                                    ch = changes[row_num - 1]
                                    if action == "w":
                                        if (ch.host, ch.hash) in submitted_keys:
                                            status_msg = f"[dim]#{row_num} already submitted[/dim]"
                                        elif ch.waiting:
                                            ch.waiting = False
                                            try:
                                                last_mtime = _clear_waiting_in_config(config_path, ch.hash)
                                            except OSError:
                                                pass
                                            status_msg = f"[yellow]#{row_num} no longer waiting[/yellow]"
                                        else:
                                            ch.waiting = True
                                            try:
                                                last_mtime = _set_waiting_in_config(config_path, ch.hash)
                                            except OSError:
                                                pass
                                            status_msg = f"[yellow]#{row_num} marked as waiting[/yellow]"
                                    elif action == "d":
                                        ch.deleted = not ch.deleted
                                        if ch.deleted:
                                            status_msg = f"[red]#{row_num} marked for deletion[/red]"
                                        else:
                                            status_msg = f"[green]#{row_num} restored[/green]"
                                else:
                                    status_msg = f"[red]Invalid row: {buf}[/red]"
                            else:
                                status_msg = f"[red]Invalid input: {buf}[/red]"
                            input_state["active"] = False
                            input_state["buf"] = ""
                        elif key in ("\x7f", "\x08"):
                            input_state["buf"] = input_state["buf"][:-1]
                        elif input_state["action"] == "d" and not input_state["buf"] and key == "a":
                            # Delete all submitted changes
                            count = 0
                            for ch in changes:
                                if (ch.host, ch.hash) in submitted_keys and not ch.deleted:
                                    ch.deleted = True
                                    count += 1
                            if count:
                                status_msg = f"[red]{count} submitted change(s) marked for deletion[/red]"
                            else:
                                status_msg = "[dim]No submitted changes to delete[/dim]"
                            input_state["active"] = False
                            input_state["buf"] = ""
                        elif input_state["action"] == "d" and not input_state["buf"] and key == "d":
                            # Purge all deleted changes from config now
                            deleted_hashes = {ch.hash for ch in changes if ch.deleted}
                            if deleted_hashes:
                                try:
                                    cfg = json.loads(config_path.read_text())
                                    cfg["changes"] = [
                                        e for e in cfg.get("changes", []) if e.get("hash") not in deleted_hashes
                                    ]
                                    config_path.write_text(json.dumps(cfg, indent=2) + "\n")
                                    last_mtime = config_mtime(config_path)
                                except OSError:
                                    pass
                                changes[:] = [ch for ch in changes if not ch.deleted]
                                # Clean up stale results
                                valid_keys = {(ch.host, ch.hash) for ch in changes}
                                for k in list(results):
                                    if k not in valid_keys:
                                        del results[k]
                                status_msg = f"[red]{len(deleted_hashes)} change(s) permanently removed[/red]"
                            else:
                                status_msg = "[dim]Nothing to purge[/dim]"
                            input_state["active"] = False
                            input_state["buf"] = ""
                        elif input_state["action"] == "d" and not input_state["buf"] and key == "r":
                            # Restore all deleted changes
                            restored = sum(1 for ch in changes if ch.deleted)
                            for ch in changes:
                                ch.deleted = False
                            if restored:
                                status_msg = f"[green]{restored} change(s) restored[/green]"
                            else:
                                status_msg = "[dim]Nothing to restore[/dim]"
                            input_state["active"] = False
                            input_state["buf"] = ""
                        elif key.isdigit():
                            input_state["buf"] += key
                    else:
                        if key == "w":
                            input_state["active"] = True
                            input_state["buf"] = ""
                            input_state["action"] = "w"
                        elif key == "d":
                            input_state["active"] = True
                            input_state["buf"] = ""
                            input_state["action"] = "d"
                        elif key == "q":
                            # Purge deleted changes from config before exit
                            deleted_hashes = {ch.hash for ch in changes if ch.deleted}
                            if deleted_hashes:
                                try:
                                    data = json.loads(config_path.read_text())
                                    data["changes"] = [
                                        e for e in data.get("changes", []) if e.get("hash") not in deleted_hashes
                                    ]
                                    config_path.write_text(json.dumps(data, indent=2) + "\n")
                                except OSError:
                                    pass
                            return

                    needs_visual_update = True

                if should_reload():
                    _start_refresh()
                    _visual_update()
                    needs_visual_update = False
                elif seconds_since_refresh >= interval:
                    status_msg = ""
                    _start_refresh()
                    _visual_update()
                    needs_visual_update = False
                elif needs_visual_update:
                    _visual_update()
                    needs_visual_update = False
    except KeyboardInterrupt:
        pass
    finally:
        console.print("\n[dim]Stopped.[/dim]")


if __name__ == "__main__":
    with NoEcho() as no_echo:
        main()
