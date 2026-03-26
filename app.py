import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread

from rich.console import Console
from rich.live import Live
from rich.table import Table

from config import (
    add_change_to_config,
    config_mtime,
    load_config,
    remove_changes_from_config,
    update_config_field,
)
from display import build_table
from gerrit import approval_snapshot, is_submitted, query_approvals
from input_handler import InputHandler
from models import Change


class App:
    def __init__(self, config_path: Path, changes: list[Change], interval: int, default_host: str | None) -> None:
        self.config_path = config_path
        self.console = Console()
        self.changes = changes
        self.interval = interval
        self.default_host = default_host
        self.results: dict[tuple[str, str], dict] = {}
        self.submitted_keys: set[tuple[str, str]] = set()
        self.prev_approvals: dict[tuple[str, str], frozenset[tuple[str, str, str]]] = {}
        self.last_mtime: float = config_mtime(config_path)
        self.status_msg: str = ""
        self.running: bool = True
        self.key_queue: Queue[str] = Queue()
        self.input: InputHandler = InputHandler()
        self.refresh_done = Event()
        self.refresh_done.set()
        self.refresh_pending: bool = False
        self.seconds_since_refresh: float = 0.0

    # --- Query methods ---

    def do_queries(self) -> None:
        """Run SSH queries for all non-submitted, non-deleted, non-disabled changes."""
        pending = [
            ch
            for ch in self.changes
            if (ch.host, ch.hash) not in self.submitted_keys and not ch.deleted and not ch.disabled
        ]

        def _query(ch: Change) -> tuple[tuple[str, str], dict]:
            return (ch.host, ch.hash), query_approvals(ch.hash, ch.host)

        with ThreadPoolExecutor(max_workers=len(pending) or 1) as pool:
            for key, data in pool.map(_query, pending):
                self.results[key] = data
                if "error" not in data and is_submitted(data):
                    self.submitted_keys.add(key)

                if "error" not in data:
                    snapshot = approval_snapshot(data)
                    ch = next(c for c in self.changes if (c.host, c.hash) == key)
                    if ch.waiting and key in self.prev_approvals and snapshot != self.prev_approvals[key]:
                        ch.waiting = False
                        try:
                            self.last_mtime = update_config_field(self.config_path, ch.hash, "waiting", False)
                        except OSError:
                            pass
                    self.prev_approvals[key] = snapshot

    def query_disabled_once(self) -> None:
        """One-shot query for disabled changes that have no cached data yet."""
        need = [ch for ch in self.changes if ch.disabled and (ch.host, ch.hash) not in self.results]
        if not need:
            return

        def _query(ch: Change) -> tuple[tuple[str, str], dict]:
            return (ch.host, ch.hash), query_approvals(ch.hash, ch.host)

        with ThreadPoolExecutor(max_workers=len(need)) as pool:
            for key, data in pool.map(_query, need):
                self.results[key] = data

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

            valid_keys = {(ch.host, ch.hash) for ch in self.changes}
            for k in list(self.results):
                if k not in valid_keys:
                    del self.results[k]

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
            self.changes, self.results, str(self.config_path), self.interval, self.status_msg, prompt_msg
        )

    def visual_update(self, live: Live) -> None:
        """Redraw the table using cached results (no SSH queries)."""
        live.update(self.build(self.input.prompt(len(self.changes))))

    # --- AppContext interface (called by InputHandler) ---

    def toggle_waiting(self, row: int) -> None:
        ch = self.changes[row - 1]
        if (ch.host, ch.hash) in self.submitted_keys:
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

    def add_change(self, commit_hash: str, host: str) -> None:
        new_change = Change(host=host, hash=commit_hash)
        self.changes.append(new_change)
        try:
            self.last_mtime = add_change_to_config(self.config_path, commit_hash, host)
        except OSError:
            pass
        self.status_msg = f"[green]Added {commit_hash[:7]} @ {host}[/green]"

    def delete_all_submitted(self) -> None:
        count = 0
        for ch in self.changes:
            if (ch.host, ch.hash) in self.submitted_keys and not ch.deleted:
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
            # Clean up stale caches
            valid_keys = {(ch.host, ch.hash) for ch in self.changes}
            for k in list(self.results):
                if k not in valid_keys:
                    del self.results[k]
            for k in list(self.prev_approvals):
                if k not in valid_keys:
                    del self.prev_approvals[k]
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
        from utils import NoEcho

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
                refresh_per_second=1,
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
                        self.input.handle_key(key, self)
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
