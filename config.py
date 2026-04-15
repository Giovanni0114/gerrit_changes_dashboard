import os
import subprocess
import tomllib
from pathlib import Path

DEFAULT_INTERVAL = 30
DEFAULT_CHANGES_FILENAME = "changes.json"
DEFAULT_DEFAULT_PORT = 22


class AppConfig:
    path: Path

    # --- mandatory ---
    interval: int
    changes_path: Path

    # --- optional ---
    default_host: str | None
    default_port: int | None
    email: str | None
    editor: str | None = None

    def __init__(self, path: Path) -> None:
        self.path = path
        self.load_config()

    def mtime(self) -> float:
        try:
            return self.path.stat().st_mtime
        except OSError:
            return 0.0

    def load_config(self):
        with self.path.open("rb") as fh:
            data = tomllib.load(fh)

        if "config" not in data:
            raise ValueError(f"Missing [config] section in {self.path}")

        config_data = data["config"]

        try:
            self.interval = int(config_data.get("interval", DEFAULT_INTERVAL))
        except Exception as ex:
            raise ValueError(f"Invalid interval value: {config_data.get('interval')}") from ex

        if self.interval < 1:
            raise ValueError(f"interval must be >= 1, got {self.interval}")

        try:
            self.default_port = int(config_data.get("default_port", DEFAULT_DEFAULT_PORT))
        except Exception as ex:
            raise ValueError(f"Invalid default_port: {config_data.get('interval')}") from ex

        changes_file_filename = config_data.get("changes_file", DEFAULT_CHANGES_FILENAME)
        self.changes_path = (self.path.parent / changes_file_filename).resolve()

        self.default_host = config_data.get("default_host")
        self.email = config_data.get("email")
        self.editor = config_data.get("editor")

    def resolve_email(self) -> str | None:
        if self.email is not None:
            return self.email

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

    def resolve_editor(self) -> str | None:
        if self.editor is not None:
            return self.editor
        return os.environ.get("EDITOR") or None


def generate_example_config(path: Path) -> None:
    if path.exists():
        return
    content = (
        "# Gerrit Approvals Dashboard — settings\n"
        "[config]"
        "interval = 30\n"
        'changes_file = "./changes.json"  # path relative to this file\n'
        '# default_host = "gerrit.example.com"\n'
        "# default_port = 22\n"
        '# email = "you@example.com"  # falls back to git config user.email\n'
        '# editor = "vim"  # falls back to env EDITOR\n'
    )
    path.write_text(content, encoding="utf-8")
