from typing import Protocol, runtime_checkable

from models import Change


@runtime_checkable
class AppContext(Protocol):
    """Interface that InputHandler uses to call back into the app.

    Methods that persist to config (toggle_waiting, toggle_disabled, add_change,
    purge_deleted, quit) handle config file writes internally and update last_mtime.
    Methods that are in-memory only (toggle_deleted, delete_all_submitted, restore_all)
    do NOT write to config.
    """

    changes: list[Change]
    status_msg: str
    default_host: str | None
    submitted_keys: set[tuple[str, str]]

    def toggle_waiting(self, row: int) -> None: ...
    def toggle_deleted(self, row: int) -> None: ...
    def toggle_disabled(self, row: int) -> None: ...
    def refresh_all(self) -> None: ...
    def open_change_webui(self, row: int) -> None: ...
    def add_change(self, commit_hash: str, host: str) -> None: ...
    def delete_all_submitted(self) -> None: ...
    def purge_deleted(self) -> None: ...
    def restore_all(self) -> None: ...
    def quit(self) -> None: ...


class InputHandler:
    def __init__(self) -> None:
        self.active: bool = False
        self.buf: str = ""
        self.action: str = ""  # "a", "w", "d", "x", ""
        self.step: int = 0  # for multi-step actions like "a" (add)
        self.hash: str = ""  # stashed hash during add flow

    def prompt(self, num_changes: int) -> str:
        """Build prompt string for current input state."""
        if not self.active:
            return ""
        if self.action == "a":
            if self.step == 1:
                return f"Add change — paste commit hash: {self.buf}_  [ESC=cancel]"
            else:
                return f"Host (Enter=default, #=copy from row, or type): {self.buf}_  [ESC=cancel]"
        if self.action == "w":
            label = "Toggle waiting"
        elif self.action == "d":
            label = "Toggle disabled"
        else:
            label = "Toggle deleted"
        hint = f"{label} — enter row # (1-{num_changes}): {self.buf}_  [ESC=cancel]"
        if self.action == "x" and not self.buf:
            hint += "  [a=all submitted  x=purge deleted  r=restore all]"
        return hint

    def handle_key(self, key: str, ctx: AppContext) -> None:
        """Process a single keypress. Delegates to action-specific methods."""
        if not self.active:
            self._handle_inactive(key, ctx)
        elif key == "ESC":
            self._reset()
        elif self.action == "a":
            self._handle_add(key, ctx)
        elif self.action == "x" and not self.buf and key in ("a", "x", "r"):
            self._handle_delete_shortcut(key, ctx)
        else:
            self._handle_row_action(key, ctx)

    def _handle_inactive(self, key: str, ctx: AppContext) -> None:
        """Handle keypress when no action is active (top-level bindings)."""
        if key == "w":
            self.active = True
            self.buf = ""
            self.action = "w"
        elif key == "x":
            self.active = True
            self.buf = ""
            self.action = "x"
        elif key == "d":
            self.active = True
            self.buf = ""
            self.action = "d"
        elif key == "a":
            self.active = True
            self.buf = ""
            self.action = "a"
            self.step = 1
            self.hash = ""
        if key == "o":
            self.active = True
            self.buf = ""
            self.action = "o"
        elif key == "r":
            ctx.refresh_all()
        elif key == "q":
            ctx.quit()

    def _handle_add(self, key: str, ctx: AppContext) -> None:
        """Handle keypress during add-change flow."""
        if key in ("\r", "\n"):
            if self.step == 1:
                # Hash submitted — move to host step
                if not self.buf.strip():
                    ctx.status_msg = "[red]Hash cannot be empty[/red]"
                    self._reset()
                else:
                    self.hash = self.buf.strip()
                    self.buf = ""
                    self.step = 2
            else:
                # Host submitted — resolve and add
                commit_hash = self.hash
                if not self.buf.strip():
                    # Empty -> use default_host
                    if ctx.default_host:
                        host = ctx.default_host
                    else:
                        ctx.status_msg = "[red]No default_host set in config[/red]"
                        self._reset()
                        return
                elif self.buf.strip().isdigit():
                    # Number -> copy host from that row
                    row_num = int(self.buf.strip())
                    if 1 <= row_num <= len(ctx.changes):
                        host = ctx.changes[row_num - 1].host
                    else:
                        ctx.status_msg = f"[red]Invalid row: {self.buf.strip()}[/red]"
                        self._reset()
                        return
                else:
                    # Literal hostname
                    host = self.buf.strip()
                ctx.add_change(commit_hash, host)
                self._reset()
        elif key in ("\x7f", "\x08"):
            self.buf = self.buf[:-1]
        elif key.isprintable() and key not in ("", "ESC"):
            self.buf += key

    def _handle_row_action(self, key: str, ctx: AppContext) -> None:
        """Handle keypress during w/d/x row-number entry."""
        if key in ("\r", "\n"):
            if self.buf.isdigit():
                row_num = int(self.buf)
                if 1 <= row_num <= len(ctx.changes):
                    if self.action == "w":
                        ctx.toggle_waiting(row_num)
                    elif self.action == "x":
                        ctx.toggle_deleted(row_num)
                    elif self.action == "d":
                        ctx.toggle_disabled(row_num)
                    elif self.action == "o":
                        ctx.open_change_webui(row_num)
                else:
                    ctx.status_msg = f"[red]Invalid row: {self.buf}[/red]"
            else:
                ctx.status_msg = f"[red]Invalid input: {self.buf}[/red]"
            self._reset()
        elif key in ("\x7f", "\x08"):
            self.buf = self.buf[:-1]
        elif key.isdigit():
            self.buf += key

    def _handle_delete_shortcut(self, key: str, ctx: AppContext) -> None:
        """Handle x-mode shortcuts (a=all submitted, x=purge, r=restore)."""
        if key == "a":
            ctx.delete_all_submitted()
        elif key == "x":
            ctx.purge_deleted()
        elif key == "r":
            ctx.restore_all()
        self._reset()

    def _reset(self) -> None:
        """Clear input state back to inactive."""
        self.active = False
        self.buf = ""
        self.action = ""
        self.step = 0
        self.hash = ""
