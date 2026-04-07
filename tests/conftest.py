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

    def quit(self) -> None:
        self.quit_called = True


@pytest.fixture
def app() -> FakeApp:
    return FakeApp()
