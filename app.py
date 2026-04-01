import json
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Lock, Thread
from typing import Iterable

from rich.console import Console
from rich.live import Live
from rich.table import Table

import gerrit
from config import (
    add_change_to_config,
    bulk_update_config_field,
    config_mtime,
    load_config,
    remove_changes_from_config,
    update_config_field,
)
from display import build_table
from gerrit import is_submitted, query_approvals
from input_handler import InputHandler
from models import ApprovalEntry, TrackedChange
from utils import AtomicCounter, NoEcho


class App:
    def __init__(
        self, config_path: Path, changes: list[TrackedChange], interval: int, default_host: str | None
    ) -> None:
        self.config_path = config_path
        self.console = Console()
        self.changes = changes
        self.interval = interval
        self.default_host = default_host
        self.last_mtime: float = config_mtime(config_path)
        self.status_msg: str = ""
        self.running: bool = True
        self.key_queue: Queue[str] = Queue()
        self.input: InputHandler = InputHandler(self)
        self.refresh_done = Event()
        self.refresh_done.set()
        self.refresh_pending: bool = False
        self.seconds_since_refresh: float = 0.0
        self.manual_refresh_lock = Lock()
        self.manual_refresh_counter = AtomicCounter()

    # --- Query methods ---

    def do_queries(self) -> None:
        """Run SSH queries for all non-submitted, non-deleted, non-disabled changes."""
        self.status_msg = ""
        pending = [ch for ch in self.changes if not ch.submitted and not ch.deleted and not ch.disabled]

        def _query(ch: TrackedChange) -> tuple[TrackedChange, dict]:
            return ch, query_approvals(ch.hash, ch.host)

        with ThreadPoolExecutor(max_workers=len(pending) or 1) as pool:
            for ch, data in pool.map(_query, pending):
                if "patchSets" in data:
                    latest_rev = data.get("patchSets")[-1].get("revision", "<no rev>")
                    if latest_rev != ch.hash and not latest_rev.startswith(ch.hash):
                        self.status_msg += f"[orange]Warning: latest patchset mismatch for {ch.host}"
                        self.status_msg += f" - {ch.hash[:7]} vs {latest_rev}[/orange]\n"
                self._store_result(ch, data)

    def query_disabled_once(self) -> None:
        """One-shot query for disabled changes that have no cached data yet."""
        need = [ch for ch in self.changes if ch.disabled and ch.number is None]
        if not need:
            return

        def _query(ch: TrackedChange) -> tuple[TrackedChange, dict]:
            return ch, query_approvals(ch.hash, ch.host)

        with ThreadPoolExecutor(max_workers=len(need)) as pool:
            for ch, data in pool.map(_query, need):
                self._store_result(ch, data)

    def _store_result(self, ch: TrackedChange, data: dict) -> None:
        """Parse raw Gerrit SSH response dict into typed fields on ch."""
        if "error" in data:
            ch.error = data["error"]
            return
        ch.error = None
        ch.number = data.get("number")
        ch.subject = data.get("subject")
        ch.project = data.get("project")
        ch.url = data.get("url")
        patch_sets = data.get("patchSets", [])
        if patch_sets:
            raw = patch_sets[-1].get("approvals", [])
            ch.approvals = [
                ApprovalEntry(a.get("type", "?"), a.get("value", ""), a.get("by", {}).get("name", "")) for a in raw
            ]
        else:
            ch.approvals = []
        new_snapshot = frozenset((a.label, a.value, a.by) for a in ch.approvals)
        if ch.waiting and ch._snapshot and new_snapshot != ch._snapshot:
            ch.waiting = False
            try:
                self.last_mtime = update_config_field(self.config_path, ch.hash, "waiting", False)
            except OSError:
                pass
        ch._snapshot = new_snapshot
        ch.submitted = is_submitted(data)

    def set_automerge(self, row: int) -> None:
        ch = self.changes[row - 1]
        if ch.number is None:
            self.status_msg = f"[red]cannot set automerge for change #{row}[/red]"
            return

        result = gerrit.query_set_automerge(ch.hash, ch.host)
        if "error" in result:
            self.status_msg = f"[red]Automerge failed for change #{row}: {result['error']}[/red]"
        else:
            self.status_msg = f"[green]Automerge +1 set for change #{row}[/green]"
            # Force refresh to show updated approvals and submitted status
            self._start_refresh()

    # --- Config methods ---

    def reload_config(self) -> bool:
        """Check for config changes and reload if needed. Returns True if reloaded."""
        mtime = config_mtime(self.config_path)
        if mtime <= self.last_mtime:
            return False
        try:
            new_changes, new_interval, new_default_host = load_config(self.config_path)
            self.changes = new_changes
            self.interval = new_interval
            self.default_host = new_default_host
            self.last_mtime = mtime

            self.status_msg = "[green]Config reloaded[/green]"
            return True
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            self.status_msg = f"[red]Config error: {exc}[/red]"
            self.last_mtime = mtime
            return False

    # --- Display methods ---

    def build(self, prompt_msg: str = "") -> Table:
        """Build the display table from cached results."""
        return build_table(
            self.changes,
            str(self.config_path),
            self.interval,
            self.status_msg,
            prompt_msg,
            ssh_requests=gerrit.ssh_request_count,
            hints=self.input.hints(),
        )

    def visual_update(self, live: Live) -> None:
        """Redraw the table using cached results (no SSH queries)."""
        live.update(self.build(self.input.prompt(len(self.changes))))

    # --- AppContext interface (called by InputHandler) ---

    def toggle_waiting(self, row: int) -> None:
        ch = self.changes[row - 1]
        if ch.submitted:
            self.status_msg = f"[dim]#{row} already submitted[/dim]"
        elif ch.waiting:
            ch.waiting = False
            try:
                self.last_mtime = update_config_field(self.config_path, ch.hash, "waiting", False)
            except OSError:
                pass
            self.status_msg = f"[yellow]#{row} no longer waiting[/yellow]"
        else:
            ch.waiting = True
            try:
                self.last_mtime = update_config_field(self.config_path, ch.hash, "waiting", True)
            except OSError:
                pass
            self.status_msg = f"[yellow]#{row} marked as waiting[/yellow]"

    def toggle_deleted(self, row: int) -> None:
        ch = self.changes[row - 1]
        ch.deleted = not ch.deleted
        if ch.deleted:
            self.status_msg = f"[red]#{row} marked for deletion[/red]"
        else:
            self.status_msg = f"[green]#{row} restored[/green]"

    def toggle_disabled(self, row: int) -> None:
        ch = self.changes[row - 1]
        if ch.disabled:
            ch.disabled = False
            try:
                self.last_mtime = update_config_field(self.config_path, ch.hash, "disabled", False)
            except OSError:
                pass
            self.status_msg = f"[green]#{row} re-enabled[/green]"
        else:
            ch.disabled = True
            try:
                self.last_mtime = update_config_field(self.config_path, ch.hash, "disabled", True)
            except OSError:
                pass
            self.status_msg = f"[yellow]#{row} disabled[/yellow]"

    def toggle_all_waiting(self) -> None:
        candidates = [ch for ch in self.changes if not ch.deleted and not ch.disabled]
        if not candidates:
            self.status_msg = "[dim]No changes to toggle[/dim]"
            return
        target = not all(ch.waiting for ch in candidates)
        updates = {ch.hash: ("waiting", target) for ch in candidates if ch.waiting != target}
        for ch in candidates:
            ch.waiting = target
        if updates:
            try:
                self.last_mtime = bulk_update_config_field(self.config_path, updates)
            except OSError:
                pass
        if target:
            self.status_msg = f"[yellow]All {len(candidates)} change(s) marked as waiting[/yellow]"
        else:
            self.status_msg = f"[yellow]All {len(candidates)} change(s) no longer waiting[/yellow]"

    def toggle_all_disabled(self) -> None:
        candidates = [ch for ch in self.changes if not ch.deleted]
        if not candidates:
            self.status_msg = "[dim]No changes to toggle[/dim]"
            return
        target = not all(ch.disabled for ch in candidates)
        updates = {ch.hash: ("disabled", target) for ch in candidates if ch.disabled != target}
        for ch in candidates:
            ch.disabled = target
        if updates:
            try:
                self.last_mtime = bulk_update_config_field(self.config_path, updates)
            except OSError:
                pass
        if target:
            self.status_msg = f"[yellow]All {len(candidates)} change(s) disabled[/yellow]"
        else:
            self.status_msg = f"[green]All {len(candidates)} change(s) re-enabled[/green]"

    def refresh_all(self) -> None:
        if self.manual_refresh_counter.value() >= 5:
            self.status_msg = "[red]Manual refresh limit reached[/red]"
            return

        self.manual_refresh_counter.increment()

        if not self.manual_refresh_lock.locked():
            self._process_refresh_queue()

    def _process_refresh_queue(self) -> None:
        with self.manual_refresh_lock:
            while self.manual_refresh_counter.value() > 0:
                self.manual_refresh_counter.decrement()
                try:
                    self._start_refresh()
                except Exception as ex:
                    self.status_msg = f"[red]Error on manual refresh {ex} [/red]"
                    self.manual_refresh_counter.reset()
                    return

    def add_change(self, commit_hash: str, host: str) -> None:
        new_change = TrackedChange(host=host, hash=commit_hash)
        self.changes.append(new_change)
        try:
            self.last_mtime = add_change_to_config(self.config_path, commit_hash, host)
        except OSError:
            pass
        self.status_msg = f"[green]Added {commit_hash[:7]} @ {host}[/green]"

    def delete_all_submitted(self) -> None:
        count = 0
        for ch in self.changes:
            if ch.submitted and not ch.deleted:
                ch.deleted = True
                count += 1
        if count:
            self.status_msg = f"[red]{count} submitted change(s) marked for deletion[/red]"
        else:
            self.status_msg = "[dim]No submitted changes to delete[/dim]"

    def purge_deleted(self) -> None:
        deleted_hashes = {ch.hash for ch in self.changes if ch.deleted}
        if deleted_hashes:
            try:
                self.last_mtime = remove_changes_from_config(self.config_path, deleted_hashes)
            except OSError:
                pass
            self.changes[:] = [ch for ch in self.changes if not ch.deleted]
            self.status_msg = f"[red]{len(deleted_hashes)} change(s) permanently removed[/red]"
        else:
            self.status_msg = "[dim]Nothing to purge[/dim]"

    def restore_all(self) -> None:
        restored = sum(1 for ch in self.changes if ch.deleted)
        for ch in self.changes:
            ch.deleted = False
        if restored:
            self.status_msg = f"[green]{restored} change(s) restored[/green]"
        else:
            self.status_msg = "[dim]Nothing to restore[/dim]"

    def quit(self) -> None:
        """Purge deleted changes from config, then stop the main loop."""
        deleted_hashes = {ch.hash for ch in self.changes if ch.deleted}
        if deleted_hashes:
            try:
                remove_changes_from_config(self.config_path, deleted_hashes)
            except OSError:
                pass
        self.running = False

    # --- Threading ---

    def _key_reader(self) -> None:
        """Background thread: reads keys from stdin and puts them in the queue."""

        no_echo = NoEcho.instance
        if no_echo is None:
            return
        while True:
            k = no_echo.read_key(timeout=0.1)
            if k is not None:
                self.key_queue.put(k)

    def _bg_refresh(self) -> None:
        """Background thread: run SSH queries then signal completion."""
        try:
            self.do_queries()
        finally:
            self.refresh_done.set()

    def _start_refresh(self) -> None:
        """Kick off a background SSH refresh if one isn't running."""
        if self.refresh_done.is_set():
            self.refresh_done.clear()
            self.refresh_pending = True
            self.seconds_since_refresh = 0.0
            Thread(target=self._bg_refresh, daemon=True).start()

    # --- MCP helpers ---

    def get_changes(self) -> Iterable[TrackedChange]:
        return self.changes

    # --- Opem WebUI ---

    def open_change_webui(self, row: int) -> None:
        ch = self.changes[row - 1]

        if ch.number is None:
            self.status_msg = f"[red]cannot open change #{row}[/red]"
            return

        url = ch.url
        if url:
            webbrowser.open(url)
            self.status_msg = f"[green]opened change #{row} in browser[/green]"
        else:
            self.status_msg = f"[red]URL not found for change #{row}[/red]"

    # --- Main loop ---

    def run(self) -> None:
        """Run initial queries, start threads, enter main loop."""
        self.do_queries()
        self.query_disabled_once()

        reader_thread = Thread(target=self._key_reader, daemon=True)
        reader_thread.start()

        try:
            with Live(
                self.build(self.input.prompt(len(self.changes))),
                console=self.console,
                refresh_per_second=10,
                screen=True,
            ) as live:
                while self.running:
                    time.sleep(0.1)
                    self.seconds_since_refresh += 0.1
                    needs_visual_update = False

                    # Check if background refresh just completed
                    if self.refresh_pending and self.refresh_done.is_set():
                        self.refresh_pending = False
                        needs_visual_update = True

                    # Process all pending keys
                    while True:
                        try:
                            key = self.key_queue.get_nowait()
                        except Empty:
                            break
                        self.input.handle_key(key)
                        needs_visual_update = True

                    if self.reload_config():
                        self._start_refresh()
                        self.visual_update(live)
                        needs_visual_update = False
                    elif self.seconds_since_refresh >= self.interval:
                        self.status_msg = ""
                        self._start_refresh()
                        self.visual_update(live)
                        needs_visual_update = False
                    elif needs_visual_update:
                        self.visual_update(live)
                        needs_visual_update = False
        except KeyboardInterrupt:
            pass
        finally:
            self.console.print("\n[dim]Stopped.[/dim]")
