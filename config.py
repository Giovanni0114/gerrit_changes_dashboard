import json
import os
import subprocess
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from models import TrackedChange

DEFAULT_INTERVAL = 30
DEFAULT_CHANGES_FILENAME = "approvals.json"
DEFAULT_DEFAULT_PORT = 22


@dataclass
class AppConfig:
    interval: int
    default_host: str | None
    default_port: int | None
    email: str | None
    changes_file: Path
    editor: str | None = None


def load_toml_config(path: Path) -> AppConfig:
    with path.open("rb") as fh:
        data = tomllib.load(fh)

    if "config" not in data:
        raise ValueError(f"Missing [config] section in {path}")

    config_data = data["config"]

    try:
        interval = int(config_data.get("interval", DEFAULT_INTERVAL))
    except Exception as ex:
        raise ValueError(f"Invalid interval value: {config_data.get('interval')}") from ex

    if interval < 1:
        raise ValueError(f"interval must be >= 1, got {interval}")

    try:
        default_port = int(config_data.get("default_port", DEFAULT_DEFAULT_PORT))
    except Exception as ex:
        raise ValueError(f"Invalid default_port: {config_data.get('interval')}") from ex

    changes_file_str = config_data.get("changes_file", DEFAULT_CHANGES_FILENAME)
    changes_file = (path.parent / changes_file_str).resolve()

    return AppConfig(
        interval=interval,
        default_host=config_data.get("default_host"),
        default_port=default_port,
        email=config_data.get("default_email"),
        changes_file=changes_file,
        editor=config_data.get("editor"),
    )


def load_changes(path: Path, default_host: str | None, default_port: int | None) -> list[TrackedChange]:
    """Load the tracked changes list from a JSON file.

    The file must contain a top-level `changes` array. Settings keys are ignored.

    :param path: Path to the changes JSON file.
    :param default_host: Host applied to entries that omit ``host``.
    :param default_port: Port applied to entries that omit ``port``.
    :raises json.JSONDecodeError: On invalid JSON.
    :raises ValueError: If a change has no host and no default_host.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    changes = []
    for entry in data.get("changes", []):
        commit_hash = entry.get("hash")
        if not commit_hash:
            raise ValueError(f"Change entry missing required 'hash' field: {entry}")

        host = entry.get("host", default_host)
        if not host:
            raise ValueError(f"Change '{commit_hash}' has no host and no default_host is set")

        try:
            port = int(entry.get("port", default_port))
        except (ValueError, TypeError) as ex:
            raise ValueError(f"Invalid port for change '{commit_hash}': {entry.get('port')}") from ex

        changes.append(
            TrackedChange(
                hash=commit_hash,
                host=host,
                port=port,
                waiting=bool(entry.get("waiting", False)),
                disabled=bool(entry.get("disabled", False)),
            )
        )
    return changes


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
        return email
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def resolve_editor(config_editor: str | None) -> str | None:
    """Resolve editor command: config value takes priority, then EDITOR env var.

    Returns None if no editor can be determined.
    """
    if config_editor is not None:
        return config_editor
    return os.environ.get("EDITOR") or None


def config_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def generate_example_toml(path: Path) -> None:
    """Write an example approvals.toml. No-op if the file already exists."""
    if path.exists():
        return
    content = (
        "# Gerrit Approvals Dashboard — settings\n"
        "[config]"
        "# interval = 30\n"
        '# default_host = "gerrit.example.com"\n'
        "# default_port = 22\n"
        '# default_email = "you@example.com"  # falls back to git config user.email\n'
        '# changes_file = "approvals.json"  # path relative to this file\n'
    )
    path.write_text(content, encoding="utf-8")


def generate_example_changes(path: Path) -> None:
    """Write an example changes JSON file. No-op if the file already exists."""
    if path.exists():
        return

    example = {
        "$schema": "./approvals.schema.json",
        "changes": [
            {"host": "gerrit.example.com", "hash": "REPLACE_WITH_COMMIT_HASH"},
            {"host": "gerrit.example.com", "hash": "ANOTHER_HASH", "waiting": True},
        ],
    }

    path.write_text(json.dumps(example, indent=2) + "\n", encoding="utf-8")


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
