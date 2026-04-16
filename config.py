import os
import subprocess
import tomllib
from functools import lru_cache
from pathlib import Path

from models import GerritInstance

DEFAULT_INTERVAL = 30
DEFAULT_CHANGES_FILENAME = "changes.json"


@lru_cache(maxsize=1)
def _get_email_from_git_config() -> str | None:
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


class AppConfig:
    path: Path

    interval: int
    changes_path: Path

    _instances: list[GerritInstance]
    _editor: str | None = None

    def __init__(self, path: Path) -> None:
        self.path = path
        self._instances = []
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
            self.interval = int((config_data.get("interval", DEFAULT_INTERVAL)))
        except Exception as ex:
            raise ValueError(f"Invalid interval value: {config_data.get('interval')}") from ex

        if self.interval < 1:
            raise ValueError(f"interval must be >= 1, got {self.interval}")

        changes_file_filename = config_data.get("changes_file", DEFAULT_CHANGES_FILENAME)
        self.changes_path = (self.path.parent / changes_file_filename).resolve()
        if not self.changes_path.parent.exists():
            raise ValueError(f"Directory for changes_file does not exist: {self.changes_path.parent}")

        if not self.changes_path.parent.is_dir():
            raise ValueError(f"Directory for changes_file is not a directory: {self.changes_path.parent}")

        self._editor = config_data.get("editor")

        self._instances = []

        default_host = config_data.get("default_host")
        default_port = config_data.get("default_port")
        default_email = config_data.get("default_email")

        if default_host and default_port:
            self._instances.append(
                GerritInstance(name="default", host=default_host, port=default_port, email=default_email)
            )

        for ins_name in data.get("instance", {}):
            ins = data["instance"][ins_name]
            host = ins.get("host") or default_host
            port = ins.get("port") or default_port
            email = ins.get("email") or default_email

            if host and port:
                self._instances.append(GerritInstance(name=ins_name, host=host, port=port, email=email))

        if len(self._instances) == 0:
            raise ValueError("No Gerrit instances configured. Please specify at least one instance in the config file.")

        if len(set((ins.name for ins in self._instances))) != len(self._instances):
            raise ValueError("Instance names must be unique.")

    @property
    def default_host(self) -> str:
        return self.default_instance.host

    @property
    def default_port(self) -> int:
        return self.default_instance.port

    @property
    def default_instance(self) -> GerritInstance:
        if len(self._instances) == 0:
            raise ValueError("No Gerrit instances configured")
        return self._instances[0]

    @property
    def instances(self) -> list[GerritInstance]:
        return self._instances

    def get_instance_by_name(self, name: str) -> GerritInstance | None:
        for ins in self._instances:
            if ins.name == name:
                return ins
        return None

    @property
    def editor(self) -> str | None:
        if self._editor is not None:
            return self._editor
        return os.environ.get("EDITOR") or None

    def resolve_email(self, instance: GerritInstance) -> str | None:
        if instance.email:
            return instance.email

        if self.default_instance.email:
            return self.default_instance.email

        return _get_email_from_git_config()


def generate_example_config(path: Path) -> None:
    if path.exists():
        return
    content = (
        "# Gerrit Changes Dashboard settings\n"
        "[config]\n"
        "interval = 30\n"
        'changes_file = "./changes.json"  # path relative to this file\n'
        'default_host = "gerrit.example.com"\n'
        "default_port = 22\n"
        '# default_email = "you@example.com"  # falls back to git config user.email\n'
        '# editor = "vim"  # falls back to env EDITOR\n'
        "\n"
        "# if you have multiple gerrit instances, you can specify them here.\n"
        "# If default_host/default_port are set, they will be used as instance named 'default'\n"
        "# Also, default_* values will be used as defaults for each instance.\n"
        "# Instances must have different names.\n"
        "\n"
        "# If default values are not specified, first instance is used as default.\n"
        "# [instance.default]\n"
        '# host = "localhost"\n'
        "# port = 29418\n"
        '# email = ""\n'
    )
    path.write_text(content, encoding="utf-8")
