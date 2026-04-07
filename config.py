import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from models import TrackedChange

DEFAULT_INTERVAL = 30


def resolve_email(config_email: str | None) -> str | None:
    """Resolve user email: config value takes priority, then git config fallback.

    Returns None if no email can be determined.
    """
    if config_email is not None:
        return config_email
    try:
        result = subprocess.run(
            ["git", "config", "user.email"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        email = result.stdout.strip()
        return email if email else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def load_config(path: Path) -> tuple[list[TrackedChange], int, str | None, int | None, str | None]:
    data = json.loads(path.read_text())
    interval = int(data.get("interval", DEFAULT_INTERVAL))
    if interval < 1:
        raise ValueError(f"interval must be >= 1, got {interval}")
    default_host = data.get("default_host", None)
    default_port = data.get("default_port", None)
    if default_port is not None:
        default_port = int(default_port)
    changes = []
    for entry in data.get("changes", []):
        host = entry.get("host", default_host)
        commit_hash = entry["hash"]
        if not host:
            raise ValueError(f"Change '{commit_hash}' has no host and no default_host is set")
        port = entry.get("port", default_port)
        if port is not None:
            port = int(port)
        changes.append(
            TrackedChange(
                host=host,
                hash=commit_hash,
                waiting=bool(entry.get("waiting", False)),
                disabled=bool(entry.get("disabled", False)),
                port=port,
            )
        )
    return changes, interval, default_host, default_port, data.get("email")


def config_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def generate_example_config(path: Path) -> None:
    example = {
        "$schema": "./approvals.schema.json",
        "interval": 30,
        "changes": [
            {"host": "gerrit.example.com", "hash": "REPLACE_WITH_COMMIT_HASH"},
            {"host": "gerrit.example.com", "hash": "ANOTHER_HASH", "waiting": True},
        ],
    }
    path.write_text(json.dumps(example, indent=2) + "\n")


def update_config_field(path: Path, commit_hash: str, field: Literal["waiting", "disabled"], value: bool) -> float:
    """Set field=value for the entry matching commit_hash. Returns new mtime.

    Only 'waiting' and 'disabled' are persisted. 'deleted' is in-memory only.
    """
    data = json.loads(path.read_text())
    for entry in data.get("changes", []):
        if entry.get("hash") == commit_hash:
            entry[field] = value
    path.write_text(json.dumps(data, indent=2) + "\n")
    return config_mtime(path)


def bulk_update_config_field(path: Path, updates: Mapping[str, tuple[Literal["waiting", "disabled"], bool]]) -> float:
    """Apply multiple field updates in a single read/write. Returns new mtime.

    :param updates: mapping of commit_hash -> (field, value)
    """
    data = json.loads(path.read_text())
    for entry in data.get("changes", []):
        h = entry.get("hash")
        if h in updates:
            field, value = updates[h]
            entry[field] = value
    path.write_text(json.dumps(data, indent=2) + "\n")
    return config_mtime(path)


def add_change_to_config(path: Path, commit_hash: str, host: str) -> float:
    """Append a new change entry to the config file. Returns new mtime."""
    data = json.loads(path.read_text())
    data.setdefault("changes", []).append({"hash": commit_hash, "host": host})
    path.write_text(json.dumps(data, indent=2) + "\n")
    return config_mtime(path)


def remove_changes_from_config(path: Path, hashes: set[str]) -> float:
    """Remove entries matching hashes from config file. Returns new mtime."""
    data = json.loads(path.read_text())
    data["changes"] = [e for e in data.get("changes", []) if e.get("hash") not in hashes]
    path.write_text(json.dumps(data, indent=2) + "\n")
    return config_mtime(path)
