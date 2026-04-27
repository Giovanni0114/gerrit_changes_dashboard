import json
from dataclasses import dataclass, field
from pathlib import Path

from logs import app_logger
from models import ApprovalEntry, TrackedChange

_log = app_logger()


@dataclass
class CacheEntry:
    subject: str | None = None
    project: str | None = None
    url: str | None = None
    current_revision: str | None = None
    submitted: bool = False
    approvals: list[ApprovalEntry] = field(default_factory=list)

    @classmethod
    def from_change(cls, ch: TrackedChange) -> "CacheEntry":
        return cls(
            subject=ch.subject,
            project=ch.project,
            url=ch.url,
            current_revision=ch.current_revision,
            submitted=ch.submitted,
            approvals=list(ch.approvals),
        )

    def to_json(self) -> dict:
        return {
            "subject": self.subject,
            "project": self.project,
            "url": self.url,
            "current_revision": self.current_revision,
            "submitted": self.submitted,
            "approvals": [{"label": a.label, "value": a.value, "by": a.by} for a in self.approvals],
        }

    @classmethod
    def from_json(cls, data: dict) -> "CacheEntry":
        approvals = [
            ApprovalEntry(label=a.get("label", "?"), value=a.get("value", ""), by=a.get("by", ""))
            for a in data.get("approvals", [])
            if isinstance(a, dict)
        ]
        return cls(
            subject=data.get("subject"),
            project=data.get("project"),
            url=data.get("url"),
            current_revision=data.get("current_revision"),
            submitted=bool(data.get("submitted", False)),
            approvals=approvals,
        )


def _key(number: int, instance: str) -> str:
    return f"{number}:{instance}"


class SshCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._entries: dict[str, CacheEntry] = {}
        self.load_file()
        self._file_mtime: float = self._mtime()

    def _mtime(self) -> float:
        try:
            return self.path.stat().st_mtime
        except OSError:
            return 0.0

    def is_file_changed(self) -> bool:
        return self._mtime() != self._file_mtime

    def load_file(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _log.warning("cache load failed, starting empty: %s", exc)
            return

        if not isinstance(data, dict):
            _log.warning("cache file %s is not an object, starting empty", self.path)
            return

        loaded: dict[str, CacheEntry] = {}
        for key, value in data.items():
            if not isinstance(value, dict):
                continue
            try:
                loaded[key] = CacheEntry.from_json(value)
            except (TypeError, ValueError) as exc:
                _log.warning("skipping malformed cache entry %s: %s", key, exc)
        self._entries = loaded

    def save_file(self) -> None:
        data = {key: entry.to_json() for key, entry in self._entries.items()}
        self.path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        self._file_mtime = self._mtime()

    def get(self, change: TrackedChange) -> CacheEntry | None:
        return self._entries.get(_key(change.number, change.instance))

    def has(self, change: TrackedChange) -> bool:
        return _key(change.number, change.instance) in self._entries

    def cache(self, change: TrackedChange) -> None:
        self._entries[_key(change.number, change.instance)] = CacheEntry.from_change(change)

    def evict(self, keep: set[tuple[int, str]]) -> int:
        keep_keys = {_key(n, i) for n, i in keep}
        before = len(self._entries)
        self._entries = {k: v for k, v in self._entries.items() if k in keep_keys}
        return before - len(self._entries)

    def hydrate(self, ch: TrackedChange) -> None:
        if (entry := self.get(ch)) is None:
            return

        ch.subject = entry.subject
        ch.project = entry.project
        ch.url = entry.url
        ch.current_revision = entry.current_revision
        ch.submitted = entry.submitted
        ch.approvals = list(entry.approvals)
        ch._snapshot = frozenset((a.label, a.value, a.by) for a in entry.approvals)
