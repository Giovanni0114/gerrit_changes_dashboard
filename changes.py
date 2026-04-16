import json
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from models import TrackedChange


@dataclass
class Changes:
    path: Path
    changes: list[TrackedChange]

    def __init__(self, path: Path) -> None:
        self.path = path
        self.changes = []

        if not self.path.exists() or self.path.stat().st_size == 0:
            self.path.write_text(json.dumps([], indent=2) + "\n")

    def mtime(self):
        try:
            return self.path.stat().st_mtime
        except OSError:
            return 0.0

    def __len__(self) -> int:
        return len(self.changes)

    def __getitem__(self, idx: int) -> TrackedChange:
        return self.changes[idx]

    def count(self) -> int:
        return len(self.changes)

    def append(self, ch: TrackedChange):
        self.changes.append(ch)

    def at(self, idx: int) -> TrackedChange | None:
        if idx < 0 or idx >= len(self.changes):
            return None

        return self.changes[idx]

    # --- contextmanagers ---

    @contextmanager
    def edit_change(self, idx: int):
        if idx < 0 or idx >= len(self.changes):
            yield None
            return

        yield self.changes[idx]
        self.save_changes()

    @contextmanager
    def edit_changes(self, indexes: list[int]):
        valid = [self.changes[i] for i in indexes if 0 <= i < len(self.changes)]
        yield valid
        self.save_changes()

    # --- getters ---

    def get_all(self) -> list[TrackedChange]:
        return self.changes

    def get_running(self):
        """non-submitted && non-deleted && non-disabled"""
        return [ch for ch in self.changes if ch.is_running()]

    def get_active(self):
        """non-submitted && non-deleted"""
        return [ch for ch in self.changes if ch.is_active()]

    def get_disabled(self):
        return [ch for ch in self.changes if ch.disabled]

    def get_submitted(self):
        return [ch for ch in self.changes if ch.submitted]

    def get_deleted(self):
        return [ch for ch in self.changes if ch.deleted]

    # --- operations ---

    def remove_all_deleted(self):
        self.changes = [ch for ch in self.changes if not ch.deleted]

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

            commit_hash = entry.get("hash")

            instance = entry.get("instance", "default")

            new_changes.append(
                TrackedChange(
                    number=number,
                    instance=instance,
                    waiting=bool(entry.get("waiting", False)),
                    disabled=bool(entry.get("disabled", False)),
                    deleted=bool(entry.get("deleted", False)),
                    submitted=bool(entry.get("submitted", False)),
                    comments=entry.get("comments", []),
                    # TODO: remove this, shoud not be here
                    current_revision=commit_hash,
                )
            )

        self.changes = new_changes

    def save_changes(self) -> float:
        data = []

        for ch in self.changes:
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

            if ch.submitted:
                change["submitted"] = ch.submitted

            if ch.current_revision:
                change["hash"] = ch.current_revision

            if ch.comments:
                change["comments"] = ch.comments

            data.append(change)

        self.path.write_text(json.dumps(data, indent=2) + "\n")
        return self.mtime()
