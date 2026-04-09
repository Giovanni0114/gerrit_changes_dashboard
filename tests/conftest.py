from dataclasses import dataclass, field
from typing import Iterable

import pytest

from models import TrackedChange


@dataclass
class FakeApp:
    """Explicit stub that satisfies the AppContext Protocol for testing."""

    changes: list[TrackedChange] = field(default_factory=list)
    status_msg: str = ""
    default_host: str | None = None

    # Call trackers
    quit_called: bool = False
    refresh_called: bool = False
    toggled_waiting: list[int] = field(default_factory=list)
    toggled_deleted: list[int] = field(default_factory=list)
    toggled_disabled: list[int] = field(default_factory=list)
    all_waiting_toggled: int = 0
    all_disabled_toggled: int = 0
    delete_all_submitted_called: bool = False
    purge_deleted_called: bool = False
    restore_all_called: bool = False
    opened_webui: list[int] = field(default_factory=list)
    automerge_set: list[int] = field(default_factory=list)
    added_changes: list[tuple[str, str]] = field(default_factory=list)
    fetch_open_changes_called: bool = False
    open_config_in_editor_called: bool = False
    open_approvals_in_editor_called: bool = False
    added_comments: list[tuple[int, str]] = field(default_factory=list)
    replaced_comments: list[tuple[int, str]] = field(default_factory=list)
    edited_comments: list[tuple[int, str]] = field(default_factory=list)
    deleted_comments: list[tuple[int, int]] = field(default_factory=list)
    deleted_all_comments: list[int] = field(default_factory=list)

    def get_changes(self) -> Iterable[TrackedChange]:
        return iter(self.changes)

    def toggle_waiting(self, row: int) -> None:
        self.toggled_waiting.append(row)

    def toggle_deleted(self, row: int) -> None:
        self.toggled_deleted.append(row)

    def toggle_disabled(self, row: int) -> None:
        self.toggled_disabled.append(row)

    def toggle_all_waiting(self) -> None:
        self.all_waiting_toggled += 1

    def toggle_all_disabled(self) -> None:
        self.all_disabled_toggled += 1

    def refresh_all(self) -> None:
        self.refresh_called = True

    def open_change_webui(self, row: int) -> None:
        self.opened_webui.append(row)

    def set_automerge(self, row: int) -> None:
        self.automerge_set.append(row)

    def add_change(self, commit_hash: str, host: str) -> None:
        self.added_changes.append((commit_hash, host))

    def delete_all_submitted(self) -> None:
        self.delete_all_submitted_called = True

    def purge_deleted(self) -> None:
        self.purge_deleted_called = True

    def restore_all(self) -> None:
        self.restore_all_called = True

    def fetch_open_changes(self) -> None:
        self.fetch_open_changes_called = True

    def open_config_in_editor(self) -> None:
        self.open_config_in_editor_called = True

    def open_approvals_in_editor(self) -> None:
        self.open_approvals_in_editor_called = True

    def quit(self) -> None:
        self.quit_called = True

    def add_comment(self, row: int, text: str) -> None:
        self.added_comments.append((row, text))

    def replace_all_comments(self, row: int, text: str) -> None:
        self.replaced_comments.append((row, text))

    def edit_last_comment(self, row: int, text: str) -> None:
        self.edited_comments.append((row, text))

    def delete_comment(self, row: int, comment_idx: int) -> None:
        if row < 1 or row > len(self.changes):
            self.status_msg = f"[red]No change at index {row}[/red]"
            return

        ch = self.changes[row - 1]
        # Convert 1-based comment index to 0-based array index
        array_idx = comment_idx - 1
        if 0 <= array_idx < len(ch.comments):
            self.deleted_comments.append((row, comment_idx))
            ch.comments.pop(array_idx)
        else:
            self.status_msg = f"[red]No comment at index {comment_idx}[/red]"

    def delete_all_comments(self, row: int) -> None:
        self.deleted_all_comments.append(row)


@pytest.fixture
def app() -> FakeApp:
    return FakeApp()
