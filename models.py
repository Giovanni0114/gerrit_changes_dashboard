from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

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


_TRACKED = frozenset(
    {
        "deleted",
        "disabled",
        "waiting",
        "comments",
    }
)
_SENTINEL = object()


@dataclass
class TrackedChange:
    number: int
    instance: str = "default"

    comments: list[str] = field(default_factory=list)
    approvals: list[ApprovalEntry] = field(default_factory=list)

    deleted: bool = False
    submitted: bool = False
    disabled: bool = False
    waiting: bool = False

    # --- data from gerrit ---
    subject: str | None = None
    project: str | None = None
    url: str | None = None
    current_revision: str | None = None
    error: str | None = None
    _snapshot: frozenset[tuple[str, str, str]] = field(default_factory=frozenset, repr=False, compare=False)

    modified: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "modified", False)

    def __setattr__(self, name: str, value: object) -> None:
        if name in _TRACKED and getattr(self, name, _SENTINEL) != value:
            super().__setattr__("modified", True)
        super().__setattr__(name, value)

    def is_running(self) -> bool:
        """non-submitted && non-deleted && non-disabled"""
        return not self.submitted and not self.deleted and not self.disabled

    def is_active(self) -> bool:
        """non-submitted && non-deleted"""
        return not self.submitted and not self.deleted


@dataclass(frozen=True)
class Index:
    values: frozenset[int]
    wildcard: bool = False

    def empty(self) -> bool:
        return len(self.values) == 0

    def single(self) -> bool:
        return len(self.values) == 1

    def __contains__(self, item: int) -> bool:
        return item in self.values

    def __len__(self) -> int:
        return len(self.values)

    def __iter__(self) -> Iterator[int]:
        return iter(sorted(self.values))

    def __str__(self) -> str:
        return f"Index({sorted(self.values)})"

    def resolve(self, changes_store: changes.Changes) -> list[TrackedChange]:
        resolved = [changes_store.at(idx - 1) for idx in self.values]
        resolved = [ch for ch in resolved if ch is not None]
        return resolved


@runtime_checkable
class AppContext(Protocol):
    changes: changes.Changes
    config: config.AppConfig
    status_msg: str

    def toggle_waiting(self, row: Index) -> None: ...
    def toggle_deleted(self, row: Index) -> None: ...
    def toggle_disabled(self, row: Index) -> None: ...

    def open_change_webui(self, row: Index) -> None: ...
    def review_set_automerge(self, row: Index) -> None: ...
    def review_abandon(self, row: Index) -> None: ...
    def review_rebase(self, row: Index) -> None: ...
    def review_restore(self, row: Index) -> None: ...
    def review_code_review(self, row: Index, score: int) -> None: ...
    def review_submit(self, row: Index) -> None: ...

    def refresh_all(self) -> None: ...

    def add_change(self, number: int, instance: str) -> None: ...
    def delete_all_submitted(self) -> None: ...
    def purge_deleted(self) -> None: ...
    def restore_all(self) -> None: ...
    def fetch_open_changes(self) -> None: ...
    def open_config_in_editor(self) -> None: ...
    def open_changes_in_editor(self) -> None: ...
    def quit(self) -> None: ...

    # --- Comments ---
    def add_comment(self, row: Index, text: str) -> None: ...
    def replace_all_comments(self, row: Index, text: str) -> None: ...
    def edit_last_comment(self, row: Index, text: str) -> None: ...
    def delete_comment(self, row: Index, comment_idx: Index) -> None: ...
    def delete_all_comments(self, row: Index) -> None: ...
