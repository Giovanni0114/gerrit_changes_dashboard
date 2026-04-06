from dataclasses import dataclass, field
from typing import Iterable, Protocol, runtime_checkable


@dataclass
class ApprovalEntry:
    label: str
    value: str
    by: str


@dataclass
class TrackedChange:
    # --- Persisted to config file ---
    host: str
    hash: str
    waiting: bool = False
    disabled: bool = False
    port: int | None = None

    # --- In-memory only (not saved to config) ---
    deleted: bool = False

    # --- Remote data from Gerrit SSH (None = not yet fetched) ---
    number: int | None = None
    subject: str | None = None
    project: str | None = None
    url: str | None = None
    submitted: bool = False
    approvals: list[ApprovalEntry] = field(default_factory=list)
    error: str | None = None

    # --- Internal: approval snapshot for change-detection ---
    _snapshot: frozenset[tuple[str, str, str]] = field(default_factory=frozenset, repr=False, compare=False)


@runtime_checkable
class AppContext(Protocol):
    changes: list[TrackedChange]
    status_msg: str
    default_host: str | None

    def get_changes(self) -> Iterable[TrackedChange]: ...
    def toggle_waiting(self, row: int) -> None: ...
    def toggle_deleted(self, row: int) -> None: ...
    def toggle_disabled(self, row: int) -> None: ...
    def toggle_all_waiting(self) -> None: ...
    def toggle_all_disabled(self) -> None: ...
    def refresh_all(self) -> None: ...
    def open_change_webui(self, row: int) -> None: ...
    def set_automerge(self, row: int) -> None: ...
    def add_change(self, commit_hash: str, host: str) -> None: ...
    def delete_all_submitted(self) -> None: ...
    def purge_deleted(self) -> None: ...
    def restore_all(self) -> None: ...
    def quit(self) -> None: ...
