from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable, Protocol, runtime_checkable

if TYPE_CHECKING:
    import changes
    import config


@dataclass
class ApprovalEntry:
    label: str
    value: str
    by: str


@dataclass(frozen=True)
class GerritInstance:
    name: str
    host: str
    port: int
    email: str | None


@dataclass
class TrackedChange:
    number: int
    instance: str = "default"
    comments: list[str] = field(default_factory=list)

    # --- state ---
    deleted: bool = False
    submitted: bool = False
    disabled: bool = False
    waiting: bool = False

    # --- data from gerrit ---
    subject: str | None = None
    project: str | None = None
    url: str | None = None
    current_revision: str | None = None

    approvals: list[ApprovalEntry] = field(default_factory=list)
    error: str | None = None

    # --- Internal: approval snapshot for change-detection ---
    _snapshot: frozenset[tuple[str, str, str]] = field(default_factory=frozenset, repr=False, compare=False)

    def is_running(self) -> bool:
        """non-submitted && non-deleted && non-disabled"""
        return not self.submitted and not self.deleted and not self.disabled

    def is_active(self) -> bool:
        """non-submitted && non-deleted"""
        return not self.submitted and not self.deleted


@runtime_checkable
class AppContext(Protocol):
    changes: changes.Changes
    config: config.AppConfig
    status_msg: str

    def get_changes(self) -> Iterable[TrackedChange]: ...
    def toggle_waiting(self, row: int) -> None: ...
    def toggle_deleted(self, row: int) -> None: ...
    def toggle_disabled(self, row: int) -> None: ...
    def toggle_all_waiting(self) -> None: ...
    def toggle_all_disabled(self) -> None: ...
    def refresh_all(self) -> None: ...
    def open_change_webui(self, row: int) -> None: ...
    def set_automerge(self, row: int) -> None: ...
    def add_change(self, number: int, instance: str) -> None: ...
    def delete_all_submitted(self) -> None: ...
    def purge_deleted(self) -> None: ...
    def restore_all(self) -> None: ...
    def fetch_open_changes(self) -> None: ...
    def open_config_in_editor(self) -> None: ...
    def open_changes_in_editor(self) -> None: ...
    def quit(self) -> None: ...

    # --- Comments ---
    def add_comment(self, row: int, text: str) -> None: ...
    def replace_all_comments(self, row: int, text: str) -> None: ...
    def edit_last_comment(self, row: int, text: str) -> None: ...
    def delete_comment(self, row: int, comment_idx: int) -> None: ...
    def delete_all_comments(self, row: int) -> None: ...
