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
from cache import SshCache
from changes import Changes
from config import (
    AppConfig,
)
from display import build_header, build_layout, build_table
from gerrit import is_submitted, query_approvals, query_open_changes
from input_handler import InputHandler
from logs import app_logger
from models import ApprovalEntry, GerritInstance, Index, TrackedChange
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

        self.needs_visual_update = False

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

    def _resolve_index(self, rows: Index) -> list[TrackedChange]:
        changes = self.changes.get_running() if rows.wildcard else rows.resolve(self.changes)
        if not changes:
            self.status_msg = "[red]No matching changes for operation[/red]"

        return changes

    def _resolve_index_for_all(self, rows: Index) -> list[TrackedChange]:
        changes = self.changes.get_all() if rows.wildcard else rows.resolve(self.changes)
        if not changes:
            self.status_msg = "[red]No matching changes for operation[/red]"

        return changes

    # --- Query methods ---

    def _query(self, ch: TrackedChange) -> tuple[TrackedChange | None, dict]:
        instance = self.config.get_instance_by_name(ch.instance)
        if instance is None:
            ch.error = f'unknown instance "{ch.instance}"'
            _log.warning("query skipped: unknown instance %r for change %s", ch.instance, ch.number)
            return None, {}

        return ch, query_approvals(str(ch.number), instance.host, instance.port)

    def _do_query(self, changes: list[TrackedChange]) -> None:
        if not changes:
            return

        with ThreadPoolExecutor(max_workers=len(changes) or 1) as pool:
            for ch, data in pool.map(self._query, changes):
                _store_result(ch, data, self.cache)

    def query_active_changes(self) -> None:
        self._do_query(self.changes.get_running())

    def query_disabled_once(self) -> None:
        uncached = [ch for ch in self.changes.get_disabled() if not self.cache.has(ch)]
        self._do_query(uncached)

    # --- Review methods ---

    def review_set_automerge(self, rows: Index) -> None:
        for ch in self._resolve_index(rows):
            self._review_set_automerge(ch)

    def _review_set_automerge(self, ch: TrackedChange) -> None:
        if ch.current_revision is None:
            self.status_msg = f"[red]cannot set automerge for change {ch.number} - no current revision known[/red]"
            return

        if ch.submitted:
            self.status_msg = (
                f"[yellow]cannot set automerge for change {ch.number} - change is already submitted[/yellow]"
            )
            return

        if any(approval.label == "Automerge" for approval in ch.approvals):
            self.status_msg = f"[yellow]Label Automerge already exists for change {ch.number}[/yellow]"
            return

        instance = self.config.get_instance_by_name(ch.instance)
        if instance is None:
            self.status_msg = f"[red]cannot find instance '{ch.instance}' for change #{ch.number}[/red]"
            return

        result = gerrit.query_set_automerge(ch.current_revision, instance.host, instance.port)

        if "error" in result:
            self.status_msg = f"[red]Automerge failed for change #{ch.number}: {result['error']}[/red]"
            _log.warning("automerge failed change=%s instance=%s error=%s", ch.number, ch.instance, result["error"])
        else:
            self.status_msg = f"[green]Automerge +1 set for change #{ch.number}[/green]"
            _log.info("automerge set change=%s instance=%s", ch.number, ch.instance)
            self._start_refresh()

    def review_code_review(self, rows: Index, score: int) -> None:
        for ch in self._resolve_index(rows):
            self._review_code_review(ch, score)

    def _review_code_review(self, ch: TrackedChange, score: int) -> None:
        if score < -2 or score > 2:
            self.status_msg = f"[red]Score out of range: {score}[/red]"
            return

        if ch.current_revision is None:
            self.status_msg = f"[red]cannot set code-review for change {ch.number} - no current revision known[/red]"
            return

        instance = self.config.get_instance_by_name(ch.instance)
        if instance is None:
            self.status_msg = f"[red]cannot find instance '{ch.instance}' for change {ch.number}[/red]"
            return

        result = gerrit.query_review_code_review(ch.current_revision, score, instance.host, instance.port)

        if "error" in result:
            self.status_msg = f"[red]Code-Review failed for change #{ch.number}: {result['error']}[/red]"
            _log.warning(
                "code-review failed change=%s instance=%s score=%d error=%s",
                ch.number,
                ch.instance,
                score,
                result["error"],
            )
        else:
            sign = "+" if score > 0 else ""
            self.status_msg = f"[green]Code-Review {sign}{score} set for change #{ch.number}[/green]"
            _log.info("code-review set change=%s instance=%s score=%d", ch.number, ch.instance, score)
            self._start_refresh()

    def review_abandon(self, rows: Index) -> None:
        for ch in self._resolve_index(rows):
            self._review_abandon(ch)

    def _review_abandon(self, ch: TrackedChange) -> None:
        if ch.current_revision is None:
            self.status_msg = f"[red]cannot abandon change {ch.number} - no current revision known[/red]"
            return

        instance = self.config.get_instance_by_name(ch.instance)
        if instance is None:
            self.status_msg = f"[red]cannot find instance '{ch.instance}' for change {ch.number}[/red]"
            return

        result = gerrit.query_review_abandon(ch.current_revision, instance.host, instance.port)

        if "error" in result:
            self.status_msg = f"[red]Abandon failed for change {ch.number}: {result['error']}[/red]"
            _log.warning("abandon failed change=%s instance=%s error=%s", ch.number, ch.instance, result["error"])
        else:
            self.status_msg = f"[green]Change {ch.number} abandoned[/green]"
            _log.info("change abandoned change=%s instance=%s", ch.number, ch.instance)
            self._start_refresh()

    def review_restore(self, rows: Index) -> None:
        for ch in self._resolve_index(rows):
            self._review_restore(ch)

    def _review_restore(self, ch: TrackedChange) -> None:
        if ch.current_revision is None:
            self.status_msg = f"[red]cannot restore change {ch.number} - no current revision known[/red]"
            return

        instance = self.config.get_instance_by_name(ch.instance)
        if instance is None:
            self.status_msg = f"[red]cannot find instance '{ch.instance}' for change {ch.number}[/red]"
            return

        result = gerrit.query_review_restore(ch.current_revision, instance.host, instance.port)

        if "error" in result:
            self.status_msg = f"[red]Restore failed for change {ch.number}: {result['error']}[/red]"
            _log.warning("restore failed change=%s instance=%s error=%s", ch.number, ch.instance, result["error"])
        else:
            self.status_msg = f"[green]Change {ch.number} restored[/green]"
            _log.info("change restored change=%s instance=%s", ch.number, ch.instance)
            self._start_refresh()

    def review_submit(self, rows: Index) -> None:
        for ch in self._resolve_index(rows):
            self._review_submit(ch)

    def _review_submit(self, ch: TrackedChange) -> None:
        if ch.current_revision is None:
            self.status_msg = f"[red]cannot submit change {ch.number} - no current revision known[/red]"
            return

        instance = self.config.get_instance_by_name(ch.instance)
        if instance is None:
            self.status_msg = f"[red]cannot find instance '{ch.instance}' for change {ch.number}[/red]"
            return

        result = gerrit.query_review_submit(ch.current_revision, instance.host, instance.port)

        if "error" in result:
            self.status_msg = f"[red]Submit failed for change {ch.number}: {result['error']}[/red]"
            _log.warning("submit failed change=%s instance=%s error=%s", ch.number, ch.instance, result["error"])
        else:
            self.status_msg = f"[green]Change {ch.number} submitted[/green]"
            _log.info("change submitted change=%s instance=%s", ch.number, ch.instance)
            self._start_refresh()

    def review_rebase(self, rows: Index) -> None:
        for ch in self._resolve_index(rows):
            self._review_rebase(ch)

    def _review_rebase(self, ch: TrackedChange) -> None:
        if ch.current_revision is None:
            self.status_msg = f"[red]cannot rebase change {ch.number} - no current revision known[/red]"
            return

        instance = self.config.get_instance_by_name(ch.instance)
        if instance is None:
            self.status_msg = f"[red]cannot find instance '{ch.instance}' for change {ch.number}[/red]"
            return

        result = gerrit.query_review_rebase(ch.current_revision, instance.host, instance.port)

        if "error" in result:
            self.status_msg = f"[red]Rebase failed for change {ch.number}: {result['error']}[/red]"
            _log.warning("rebase failed change=%s instance=%s error=%s", ch.number, ch.instance, result["error"])
        else:
            self.status_msg = f"[green]Rebase triggered for change {ch.number}[/green]"
            _log.info("rebase triggered change=%s instance=%s", ch.number, ch.instance)
            self._start_refresh()

    # --- Open WebUI ---

    def open_change_webui(self, rows: Index) -> None:
        for ch in self._resolve_index(rows):
            self._open_change_webui(ch)

    def _open_change_webui(self, ch: TrackedChange) -> None:
        if ch.url:
            webbrowser.open(ch.url)
        else:
            self.status_msg = f"[red]URL not found for change {ch.number}[/red]"

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
            self.config,
            self.status_msg,
            gerrit.ssh_request_count,
            self.input.hints(),
        )
        return build_layout(header, table, prompt=prompt_msg)

    def visual_update_if_needed(self, live: Live, force: bool = False) -> None:
        if self.needs_visual_update:
            live.update(self.build(self.input.prompt()))
            self.needs_visual_update = False

    # --- AppContext interface (called by InputHandler) ---

    def toggle_waiting(self, rows: Index) -> None:
        if rows.wildcard:
            self.toggle_all_waiting()

        for ch in rows.resolve(self.changes):
            ch.waiting = not ch.waiting

    def toggle_all_waiting(self) -> None:
        if not (candidates := self.changes.get_active()):
            self.status_msg = "[dim]No active changes to toggle[/dim]"
            return

        target = not all(ch.waiting for ch in candidates)
        for ch in candidates:
            ch.waiting = target

    def toggle_deleted(self, rows: Index) -> None:
        if rows.wildcard:
            self.toggle_all_deleted()

        for ch in rows.resolve(self.changes):
            ch.deleted = not ch.deleted

    def toggle_all_deleted(self) -> None:
        if not (candidates := self.changes.get_all()):
            self.status_msg = "[dim]No active changes to toggle[/dim]"
            return

        target = not all(ch.deleted for ch in candidates)
        for ch in candidates:
            ch.deleted = target

    def toggle_disabled(self, rows: Index) -> None:
        if rows.wildcard:
            self.toggle_all_disabled()

        for ch in rows.resolve(self.changes):
            ch.disabled = not ch.disabled

    def toggle_all_disabled(self) -> None:
        candidates = self.changes.get_active()
        if not candidates:
            self.status_msg = "[dim]No active changes to toggle[/dim]"
            return

        target = not all(ch.disabled for ch in candidates)
        for ch in candidates:
            ch.disabled = target

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
        _log.info("change added number=%d instance=%s", number, instance)

    def delete_all_submitted(self) -> None:
        count = 0
        for ch in self.changes.get_submitted():
            if not ch.deleted:
                count += 1
                ch.deleted = True

        if count > 0:
            self.status_msg = f"[red]{count} submitted change(s) marked for deletion[/red]"
        else:
            self.status_msg = "[dim]No submitted changes to delete[/dim]"

    def purge_deleted(self) -> None:
        count_before = self.changes.count()
        self.changes.remove_all_deleted()
        deleted_hashes = count_before - self.changes.count()

        if deleted_hashes > 0:
            self.status_msg = f"[red]{deleted_hashes} change(s) permanently removed[/red]"
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
            self._start_refresh()
        else:
            self.status_msg = f"[dim] No new changes on {len(self.config.instances)} instances[/dim]"

    def quit(self) -> None:
        self.changes.remove_all_deleted()
        _log.info("app quit")
        self.running = False

    # --- Comments ---

    def add_comment(self, rows: Index, text: str) -> None:
        for ch in self._resolve_index_for_all(rows):
            self._add_comment(ch, text)

    def _add_comment(self, ch: TrackedChange, text: str) -> None:
        ch.comments = [*ch.comments, text]

    def replace_all_comments(self, rows: Index, text: str) -> None:
        for ch in self._resolve_index_for_all(rows):
            self._replace_all_comments(ch, text)

    def _replace_all_comments(self, ch: TrackedChange, text: str) -> None:
        ch.comments = [text]

    def edit_last_comment(self, rows: Index, text: str) -> None:
        for ch in self._resolve_index_for_all(rows):
            self._edit_last_comment(ch, text)

    def _edit_last_comment(self, ch: TrackedChange, text: str) -> None:
        if ch.comments:
            new = list(ch.comments)
            new[-1] = text
            ch.comments = new

    def delete_comment(self, rows: Index, comment_idx: Index) -> None:
        for ch in self._resolve_index_for_all(rows):
            self._delete_comment(ch, comment_idx)

    def _delete_comment(self, ch: TrackedChange, comment_idx: Index) -> None:
        if comment_idx.wildcard:
            ch.comments = []
            return

        new = list(ch.comments)
        for idx in sorted([i - 1 for i in comment_idx.values], reverse=True):
            if 0 <= idx < len(new):
                new.pop(idx)
        ch.comments = new

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

    # --- Config methods ---

    def reload_config(self, force: bool = False) -> bool:
        """Check both files for changes and reload if needed. Returns True if either was reloaded."""
        self.cache.save_file()
        self.changes.save_changes()

        if not force and not self.config.is_file_changed() and not self.changes.is_file_changed():
            return False
        try:
            self.config.load_config()
            self.changes.load_changes()
            self._sync_cache_with_changes()

            self.status_msg = "[green]Config reloaded[/green]"
            _log.info("config reloaded instances=%d tracked=%d", len(self.config.instances), self.changes.count())
            return True
        except Exception as exc:
            self.status_msg = f"[red]Config error: {exc}[/red]"
            _log.error("config reload failed: %s", exc)
            return False

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
                refresh_per_second=self.config.ui_refresh_rate,
                screen=True,
            ) as live:
                while self.running:
                    time.sleep(self.config.ui_refresh_interval_sec)
                    self.seconds_since_refresh += self.config.ui_refresh_interval_sec

                    # Check if background refresh just completed
                    if self.refresh_pending and self.refresh_done.is_set():
                        self.refresh_pending = False
                        self.needs_visual_update = True

                    self._check_pending_input()

                    if not self.running:
                        return

                    self._check_pending_editor(live)

                    if self.reload_config():
                        self._start_refresh()
                        self.needs_visual_update = True
                    elif self.seconds_since_refresh >= self.config.interval:
                        self.status_msg = ""
                        self._start_refresh()
                        self.needs_visual_update = True

                    self.visual_update_if_needed(live)

        except KeyboardInterrupt:
            pass
        finally:
            self.changes.save_changes()
            _console.print(f"\n[dim]Stopped. {self.exit_msg} {self.changes.count()} change(s) saved. Bye![/dim]")

    def _check_pending_input(self) -> None:
        while True:
            try:
                key = self.key_queue.get_nowait()
            except Empty:
                break
            self.input.handle_key(key)
            self.needs_visual_update = True
            if not self.running:
                break

    def _check_pending_editor(self, live: Live) -> None:
        if self.pending_editor:
            target = self.pending_editor
            self.pending_editor = None

            live.stop()
            try:
                self._run_editor(target)
                self.reload_config(force=True)
            finally:
                live.start()
            self.needs_visual_update = True
