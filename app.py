import shlex
import subprocess
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Lock, Thread
from typing import Literal

from rich.console import Console, Group
from rich.live import Live

import gerrit
from cache import CacheEntry, SshCache
from changes import Changes
from config import (
    AppConfig,
)
from display import build_header, build_layout, build_table
from gerrit import is_submitted, query_approvals, query_open_changes
from input_handler import InputHandler
from logs import app_logger
from models import ApprovalEntry, GerritInstance, TrackedChange
from utils import Arrow, AtomicCounter, NoEcho

_console = Console()
_log = app_logger()

EditorTarget = Literal["changes", "config"]


def _store_result(ch: TrackedChange | None, data: dict, cache: SshCache) -> None:
    if ch is None:
        return

    if "error" in data:
        ch.error = data["error"]
        return

    ch.error = None

    ch.subject = data.get("subject")
    ch.project = data.get("project")
    ch.url = data.get("url")
    patch_sets = data.get("patchSets", [])
    if patch_sets:
        ch.current_revision = patch_sets[-1].get("revision")
        raw = patch_sets[-1].get("approvals", [])
        ch.approvals = [
            ApprovalEntry(a.get("type", "?"), a.get("value", ""), a.get("by", {}).get("name", "")) for a in raw
        ]
    else:
        ch.approvals = []

    new_snapshot = frozenset((a.label, a.value, a.by) for a in ch.approvals)
    if ch.waiting and ch._snapshot and new_snapshot != ch._snapshot:
        ch.waiting = False

    ch._snapshot = new_snapshot
    ch.submitted = is_submitted(data)

    cache.cache(ch)


class App:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.changes = Changes(self.config.changes_path)
        self.cache = SshCache(self.config.cache_path)

        self.status_msg: str = ""
        self.exit_msg: str = ""
        self.running: bool = True
        self.key_queue: Queue[str | Arrow] = Queue()
        self.input: InputHandler = InputHandler(self)
        self.refresh_done = Event()
        self.refresh_done.set()
        self.refresh_pending: bool = False
        self.seconds_since_refresh: float = 0.0
        self.manual_refresh_lock = Lock()
        self.manual_refresh_counter = AtomicCounter()
        self.pending_editor: EditorTarget | None = None
        self._pause_keys = Event()

        self.config_mtime = self.config.mtime()
        self.changes_mtime = self.changes.mtime()

        self._sync_cache_with_changes()

        _log.info(
            "app init config=%s changes=%s cache=%s instances=%d tracked=%d",
            self.config.path,
            self.changes.path,
            self.config.cache_path,
            len(self.config.instances),
            self.changes.count(),
        )

    def _sync_cache_with_changes(self) -> None:
        """Evict orphaned cache entries and hydrate tracked changes from cache."""
        tracked = self.changes.get_all()
        self.cache.evict({(ch.number, ch.instance) for ch in tracked})
        for ch in tracked:
            self.cache.hydrate(ch)

    # --- Query methods ---

    def _query(self, ch: TrackedChange) -> tuple[TrackedChange | None, dict]:
        instance = self.config.get_instance_by_name(ch.instance)
        if instance is None:
            _log.warning("query skipped: unknown instance %r for change %s", ch.instance, ch.number)
            return None, {}

        return ch, query_approvals(str(ch.number), instance.host, instance.port)

    def _do_query(self, changes: list[TrackedChange]) -> None:
        if not changes:
            return

        with ThreadPoolExecutor(max_workers=len(changes) or 1) as pool:
            for ch, data in pool.map(self._query, changes):
                _store_result(ch, data, self.cache)

        self.cache.save_file()
        self.changes_mtime = self.changes.save_changes()

    def query_active_changes(self) -> None:
        self._do_query(self.changes.get_running())

    def query_disabled_once(self) -> None:
        uncached = [ch for ch in self.changes.get_disabled() if not self.cache.has(ch)]
        self._do_query(uncached)

    def set_automerge(self, row: int) -> None:
        ch = self.changes.at(row - 1)

        if ch is None:
            self.status_msg = f"[red]cannot find change for row #{row}[/red]"
            return

        if ch.current_revision is None:
            self.status_msg = f"[red]cannot set automerge for change #{row} - no current revision known[/red]"
            return

        if any(approval.label == "Automerge" for approval in ch.approvals):
            self.status_msg = f"[yellow]Label Automerge already exists for change #{row}[/yellow]"
            return

        instance = self.config.get_instance_by_name(ch.instance)
        if instance is None:
            self.status_msg = f"[red]cannot find instance '{ch.instance}' for change #{row}[/red]"
            return

        result = gerrit.query_set_automerge(ch.current_revision, instance.host, instance.port)

        if "error" in result:
            self.status_msg = f"[red]Automerge failed for change #{row}: {result['error']}[/red]"
            _log.warning("automerge failed change=%s instance=%s error=%s", ch.number, ch.instance, result["error"])
        else:
            self.status_msg = f"[green]Automerge +1 set for change #{row}[/green]"
            _log.info("automerge set change=%s instance=%s", ch.number, ch.instance)
            self._start_refresh()

    # --- Config methods ---

    def reload_config(self, force: bool = False) -> bool:
        """Check both files for changes and reload if needed. Returns True if either was reloaded."""
        new_toml_mtime = self.config.mtime()
        new_changes_mtime = self.changes.mtime()

        if not force and new_toml_mtime <= self.config_mtime and new_changes_mtime <= self.changes_mtime:
            return False
        try:
            self.config.load_config()
            self.config_mtime = new_toml_mtime

            self.changes.load_changes()
            self.changes_mtime = new_changes_mtime

            self._sync_cache_with_changes()

            self.status_msg = "[green]Config reloaded[/green]"
            _log.info("config reloaded instances=%d tracked=%d", len(self.config.instances), self.changes.count())
            return True
        except Exception as exc:
            self.status_msg = f"[red]Config error: {exc}[/red]"
            self.config_mtime = new_toml_mtime
            self.changes_mtime = new_changes_mtime
            _log.error("config reload failed: %s", exc)
            return False

    # --- Editor methods ---

    def open_config_in_editor(self) -> None:
        self.pending_editor = "config"

    def open_changes_in_editor(self) -> None:
        self.pending_editor = "changes"

    def _run_editor(self, target: EditorTarget) -> None:
        editor_cmd = self.config.editor

        if not editor_cmd:
            self.status_msg = "[red]No editor configured. Set EDITOR env var or 'editor' in config.[/red]"
            return

        _targets: dict[EditorTarget, Path] = {
            "config": self.config.path,
            "changes": self.changes.path,
        }

        path = _targets.get(target)

        if not path:
            raise ValueError(f"Unknown editor target {target}")

        # Pause the key reader thread so it doesn't compete with the editor for stdin
        self._pause_keys.set()
        # Give the key reader time to finish any in-flight read_key() call (timeout=0.1s)
        time.sleep(0.15)

        no_echo = NoEcho.instance
        if no_echo is not None:
            no_echo.disable()

        try:
            cmd = [*shlex.split(editor_cmd), str(path)]
            subprocess.run(cmd, check=False)
        except (FileNotFoundError, OSError) as exc:
            self.status_msg = f"[red]Failed to open editor '{editor_cmd}': {exc}[/red]"
        finally:
            if no_echo is not None:
                # Re-apply cbreak mode for key reading
                no_echo.enable()
            # Drain any stale keys that accumulated during the editor session
            while True:
                try:
                    self.key_queue.get_nowait()
                except Empty:
                    break
            self._pause_keys.clear()

    # --- Display methods ---

    def build(self, prompt_msg: str = "") -> Group:
        """Build the display layout (header, optional prompt, table with hints in caption)."""
        header = build_header(ssh_requests=gerrit.ssh_request_count)
        table = build_table(
            self.changes,
            self.config.path,
            self.config.interval,
            self.status_msg,
            gerrit.ssh_request_count,
            self.input.hints(),
        )
        return build_layout(header, table, prompt=prompt_msg)

    def visual_update(self, live: Live) -> None:
        live.update(self.build(self.input.prompt()))

    # --- AppContext interface (called by InputHandler) ---

    def toggle_waiting(self, row: int) -> None:
        with self.changes.edit_change(row - 1) as ch:
            if ch is None:
                self.status_msg = f"[red]no change at index {row}[/red]"
                return

            ch.waiting = not ch.waiting

            if ch.waiting:
                self.status_msg = f"[yellow]#{row} marked as waiting[/yellow]"
            else:
                self.status_msg = f"[yellow]#{row} no longer waiting[/yellow]"

        self.changes_mtime = self.changes.mtime()

    def toggle_deleted(self, row: int) -> None:
        with self.changes.edit_change(row - 1) as ch:
            if ch is None:
                self.status_msg = f"[red]no change at index {row}[/red]"
                return

            ch.deleted = not ch.deleted

            if ch.deleted:
                self.status_msg = f"[red]#{row} marked for deletion[/red]"
            else:
                self.status_msg = f"[green]#{row} restored[/green]"

        self.changes_mtime = self.changes.mtime()

    def toggle_disabled(self, row: int) -> None:
        with self.changes.edit_change(row - 1) as ch:
            if ch is None:
                self.status_msg = f"[red]no change at index {row}[/red]"
                return

            ch.disabled = not ch.disabled

            if ch.disabled:
                self.status_msg = f"[yellow]#{row} disabled[/yellow]"
            else:
                self.status_msg = f"[green]#{row} re-enabled[/green]"

        self.changes_mtime = self.changes.mtime()

    def toggle_all_waiting(self) -> None:
        candidates = self.changes.get_active()
        if not candidates:
            self.status_msg = "[dim]No active changes to toggle[/dim]"
            return

        target = not all(ch.waiting for ch in candidates)
        for ch in candidates:
            ch.waiting = target

        self.changes_mtime = self.changes.save_changes()

        if target:
            self.status_msg = f"[yellow]All {len(candidates)} change(s) marked as waiting[/yellow]"
        else:
            self.status_msg = f"[yellow]All {len(candidates)} change(s) no longer waiting[/yellow]"

    def toggle_all_disabled(self) -> None:
        candidates = self.changes.get_active()
        if not candidates:
            self.status_msg = "[dim]No active changes to toggle[/dim]"
            return

        target = not all(ch.disabled for ch in candidates)
        for ch in candidates:
            ch.disabled = target

        self.changes_mtime = self.changes.save_changes()

        if target:
            self.status_msg = f"[yellow]All {len(candidates)} change(s) disabled[/yellow]"
        else:
            self.status_msg = f"[green]All {len(candidates)} change(s) re-enabled[/green]"

    def refresh_all(self) -> None:
        # I know this is not a obvious place for cleaning status msg but I want to have easy way for it
        self.status_msg = ""

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

    def add_change(self, number: int, instance: str) -> None:
        new_change = TrackedChange(number=number, instance=instance)
        self.changes.append(new_change)
        self.status_msg = f"[green]Added {number} @ {instance}[/green]"
        self.changes_mtime = self.changes.save_changes()
        _log.info("change added number=%d instance=%s", number, instance)

    def delete_all_submitted(self) -> None:
        count = 0
        for ch in self.changes.get_submitted():
            if not ch.deleted:
                count += 1
                ch.deleted = True

        if count > 0:
            self.status_msg = f"[red]{count} submitted change(s) marked for deletion[/red]"
            self.changes_mtime = self.changes.save_changes()
        else:
            self.status_msg = "[dim]No submitted changes to delete[/dim]"

    def purge_deleted(self) -> None:
        count_before = self.changes.count()
        self.changes.remove_all_deleted()
        deleted_hashes = count_before - self.changes.count()

        if deleted_hashes > 0:
            self.status_msg = f"[red]{deleted_hashes} change(s) permanently removed[/red]"
            self.changes_mtime = self.changes.save_changes()
        else:
            self.status_msg = "[dim]Nothing to purge[/dim]"

    def restore_all(self) -> None:
        count = 0
        for ch in self.changes.get_deleted():
            if ch.deleted:
                count += 1
                ch.deleted = False

        if count > 0:
            self.status_msg = f"[green]{count} change(s) restored[/green]"
            self.changes_mtime = self.changes.save_changes()
        else:
            self.status_msg = "[dim]Nothing to restore[/dim]"

    def _fetch_open_changes_from_instance(self, instance: GerritInstance) -> int:
        host = instance.host
        port = instance.port
        email = self.config.resolve_email(instance)

        if not email:
            self.status_msg = (
                f"[red]Insufficient configuration for auto-fetching: email={email} host={host} port={port}[/red]"
            )
            return 0

        results = query_open_changes(email, host, port)

        added = 0
        numbers_in_changes = {ch.number for ch in self.changes.get_all()}

        for change_data in results:
            if change_data.get("wip"):
                continue

            number = change_data.get("number")

            if number is None or number in numbers_in_changes:
                continue

            ch = TrackedChange(number=number, instance=instance.name)
            _store_result(ch, change_data, self.cache)
            self.changes.append(ch)
            numbers_in_changes.add(number)
            added += 1

        return added

    def fetch_open_changes(self) -> None:
        added = 0

        for instance in self.config.instances:
            added += self._fetch_open_changes_from_instance(instance)

        _log.info("fetch_open_changes added=%d instances=%d", added, len(self.config.instances))

        if added:
            self.status_msg = f"[green]Added {added} change(s)[/green]"
            self.changes_mtime = self.changes.save_changes()
            self._start_refresh()
        else:
            self.status_msg = f"[dim] No new changes on {len(self.config.instances)} instances[/dim]"

    def quit(self) -> None:
        self.changes.remove_all_deleted()
        self.changes_mtime = self.changes.save_changes()
        self.exit_msg = f"{len(self.changes.get_all())} change(s) saved. Bye!"
        _log.info("app quit tracked=%d", self.changes.count())
        self.running = False

    # --- Comments ---

    def add_comment(self, row: int, text: str) -> None:
        with self.changes.edit_change(row - 1) as ch:
            if ch is None:
                self.status_msg = f"[red]no change at index {row}[/red]"
                return

            ch.comments.append(text)

    def replace_all_comments(self, row: int, text: str) -> None:
        with self.changes.edit_change(row - 1) as ch:
            if ch is None:
                self.status_msg = f"[red]no change at index {row}[/red]"
                return

            ch.comments = [text]

    def edit_last_comment(self, row: int, text: str) -> None:
        with self.changes.edit_change(row - 1) as ch:
            if ch is None:
                self.status_msg = f"[red]no change at index {row}[/red]"
                return

            if ch.comments:
                ch.comments[-1] = text

    def delete_comment(self, row: int, comment_idx: int) -> None:
        with self.changes.edit_change(row - 1) as ch:
            if ch is None:
                self.status_msg = f"[red]no change at index {row}[/red]"
                return

            array_idx = comment_idx - 1
            if 0 <= array_idx < len(ch.comments):
                ch.comments.pop(array_idx)
            else:
                self.status_msg = f"[red]No comment at index {comment_idx}[/red]"

    def delete_all_comments(self, row: int) -> None:
        with self.changes.edit_change(row - 1) as ch:
            if ch is None:
                self.status_msg = f"[red]no change at index {row}[/red]"
                return

            ch.comments.clear()

    # --- Threading ---

    def _key_reader(self) -> None:
        """Background thread: reads keys from stdin and puts them in the queue."""

        no_echo = NoEcho.instance
        if no_echo is None:
            return
        while True:
            if self._pause_keys.is_set():
                time.sleep(0.05)
                continue
            k = no_echo.read_key(timeout=0.1)
            if k is not None:
                self.key_queue.put(k)

    def _bg_refresh(self) -> None:
        """Background thread: run SSH queries then signal completion."""
        try:
            self.query_active_changes()
        finally:
            self.refresh_done.set()

    def _start_refresh(self) -> None:
        """Kick off a background SSH refresh if one isn't running."""
        if self.refresh_done.is_set():
            self.refresh_done.clear()
            self.refresh_pending = True
            self.seconds_since_refresh = 0.0
            Thread(target=self._bg_refresh, daemon=True).start()

    # --- Open WebUI ---

    def open_change_webui(self, row: int) -> None:
        ch = self.changes.at(row - 1)

        if not ch:
            self.status_msg = f"[red]cannot open change #{row}[/red]"
            return

        if ch.url:
            webbrowser.open(ch.url)
            self.status_msg = f"[green]opened change #{row} in browser[/green]"
        else:
            self.status_msg = f"[red]URL not found for change #{row}[/red]"

    # --- Main loop ---

    def run(self) -> None:
        """Run initial queries, start threads, enter main loop."""
        self.query_active_changes()
        self.query_disabled_once()

        reader_thread = Thread(target=self._key_reader, daemon=True)
        reader_thread.start()

        try:
            with Live(
                self.build(self.input.prompt()),
                console=_console,
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
                        if not self.running:
                            break

                        needs_visual_update = True

                    if not self.running:
                        break

                    if self.pending_editor:
                        target = self.pending_editor
                        self.pending_editor = None

                        live.stop()
                        try:
                            self._run_editor(target)
                            self.reload_config(force=True)
                        finally:
                            live.start()
                        needs_visual_update = True

                    if self.reload_config():
                        self._start_refresh()
                        self.visual_update(live)
                        needs_visual_update = False

                    elif self.seconds_since_refresh >= self.config.interval:
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
            _console.print(f"\n[dim]Stopped. {self.exit_msg}[/dim]")
