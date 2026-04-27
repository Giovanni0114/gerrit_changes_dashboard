import json
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from models import TrackedChange


@dataclass
class Changes:
    path: Path
    _changes: list[TrackedChange]

    _file_mtime: float
    _list_dirty: bool

    def __init__(self, path: Path) -> None:
        self.path = path
        self._changes = []
        self._list_dirty = False

        if not self.path.exists() or self.path.stat().st_size == 0:
            self.path.write_text(json.dumps([], indent=2) + "\n")

        self.load_changes()

    def _mtime(self) -> float:
        try:
            return self.path.stat().st_mtime
        except OSError:
            return 0.0

    def is_file_changed(self) -> bool:
        return self._mtime() != self._file_mtime

    def has_any_modified_changes(self) -> bool:
        return self._list_dirty or any(ch.modified for ch in self._changes)

    # --- utils ---

    def count(self) -> int:
        return len(self._changes)

    def append(self, ch: TrackedChange) -> None:
        self._changes.append(ch)
        self._list_dirty = True

    def at(self, idx: int) -> TrackedChange | None:
        if idx < 0 or idx >= len(self._changes):
            return None

        return self._changes[idx]

    # --- contextmanagers ---

    @contextmanager
    def edit_change(self, idx: int):
        if idx < 0 or idx >= len(self._changes):
            yield None
            return

        yield self._changes[idx]
        self.save_changes()

    @contextmanager
    def edit_changes(self, indexes: list[int]):
        valid = [self._changes[i] for i in indexes if 0 <= i < len(self._changes)]
        yield valid
        self.save_changes()

    # --- getters ---

    def get_all(self) -> list[TrackedChange]:
        return self._changes

    def get_running(self):
        """non-submitted && non-deleted && non-disabled"""
        return [ch for ch in self._changes if ch.is_running()]

    def get_active(self):
        """non-submitted && non-deleted"""
        return [ch for ch in self._changes if ch.is_active()]

    def get_disabled(self):
        return [ch for ch in self._changes if ch.disabled]

    def get_submitted(self):
        return [ch for ch in self._changes if ch.submitted]

    def get_deleted(self):
        return [ch for ch in self._changes if ch.deleted]

    # --- operations ---

    def remove_all_deleted(self):
        self._changes = [ch for ch in self._changes if not ch.deleted]
        self._list_dirty = True

    # --- changes file rw ---

    def load_changes(self):
        new_changes = []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(f"Changes json file {self.path} is not a list")

        for entry in data:
            try:
                number = int(entry.get("number"))
            except (ValueError, TypeError) as ex:
                raise ValueError(f"Invalid number for change entry: {entry}") from ex

            instance = entry.get("instance", "default")

            new_changes.append(
                TrackedChange(
                    number=number,
                    instance=instance,
                    waiting=bool(entry.get("waiting", False)),
                    disabled=bool(entry.get("disabled", False)),
                    deleted=bool(entry.get("deleted", False)),
                    comments=entry.get("comments", []),
                )
            )

        self._changes = new_changes
        self._list_dirty = False
        self._file_mtime = self._mtime()

    def save_changes(self) -> bool:
        if self.has_any_modified_changes():
            if self.is_file_changed():
                # TODO handle this better, maybe  try to merge changes instead of just throwing an error
                raise RuntimeError("Conflict detected: changes file has been modified by another process")

            data = []

            for ch in self._changes:
                change = {
                    "number": ch.number,
                    "instance": ch.instance,
                }

                if ch.waiting:
                    change["waiting"] = ch.waiting

                if ch.disabled:
                    change["disabled"] = ch.disabled

                if ch.deleted:
                    change["deleted"] = ch.deleted

                if ch.comments:
                    change["comments"] = ch.comments

                data.append(change)
                ch.modified = False

            self.path.write_text(json.dumps(data, indent=2) + "\n")
            self._file_mtime = self._mtime()
            self._list_dirty = False
            return True

        return False
