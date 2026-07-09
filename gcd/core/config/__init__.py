import os
import tomllib
from enum import Enum
from pathlib import Path

from gcd.core.logs import app_logger
from gcd.core.models import GerritInstance

from .field import Field
from .parsers import (
    _bool_parser,
    _dir_path_parser,
    _enum_parser,
    _file_path_parser,
    _float_parser,
    _int_parser,
    _list_parser,
    _str_parser,
)

DEFAULT_INTERVAL = 30
DEFAULT_REFRESH_RATE = 20
DEFAULT_CHANGES_FILENAME = "changes.json"
DEFAULT_CACHE_FILENAME = "cache.json"
DEFAULT_LOG_DIRNAME = "log"


class Layout(Enum):
    DEFAULT = "default"
    INSTANCES = "per_instance"
    TAGS = "per_tags"
    PROJECTS = "per_projects"


_FIELDS: list[Field] = [
    Field("interval", "interval", _int_parser(DEFAULT_INTERVAL, minimum=1), example="30"),
    Field("ui_refresh_rate", "ui_refresh_rate", _float_parser(DEFAULT_REFRESH_RATE, minimum=1), example="20"),
    Field(
        "layout",
        "default_layout",
        _enum_parser(Layout, Layout.DEFAULT),
        example=f'"{Layout.DEFAULT.value}"',
        comment=f"one of: {', '.join(layout.value for layout in Layout)}",
    ),
    Field("changes_path", "changes_file", _file_path_parser(DEFAULT_CHANGES_FILENAME), example='"./changes.json"'),
    Field("cache_path", "cache_file", _file_path_parser(DEFAULT_CACHE_FILENAME), example='"./cache.json"'),
    Field("log_path", "log_dir", _dir_path_parser(DEFAULT_LOG_DIRNAME), example='"./log"'),
    Field("show_header", "show_header", _bool_parser(False)),
    Field("hide_tags", "hide_tags", _list_parser(), example='["#HIDE"]'),
    Field("_editor", "editor", _str_parser(None), example='"vim"'),
]

_logger = app_logger()


class AppConfig:
    path: Path
    _file_mtime: float

    interval: int
    ui_refresh_rate: float
    changes_path: Path
    cache_path: Path
    log_path: Path
    hide_tags: list[str]

    show_header: bool | None
    layout: Layout = Layout.DEFAULT
    instances: list[GerritInstance]
    _editor: str | None = None
    plugin_configs: dict[str, dict]
    plugin_configs_per_instance: dict[str, dict[str, dict]]

    def __init__(self, path: Path) -> None:
        self.path = path
        self.instances = []
        self.plugin_configs = {}
        self.plugin_configs_per_instance = {}
        self.load_config()

    def is_file_changed(self) -> bool:
        return self._mtime() != self._file_mtime

    def _mtime(self) -> float:
        try:
            return self.path.stat().st_mtime
        except OSError:
            return 0.0

    def load_config(self) -> None:
        with self.path.open("rb") as fh:
            data = tomllib.load(fh)

        config_data = data.get("config")
        if config_data is None:
            raise ValueError(f"Missing [config] section in {self.path}")

        base_dir = self.path.parent
        for field in _FIELDS:
            setattr(self, field.attr, field.read(config_data, base_dir))

        self.instances = []
        self.plugin_configs = {}
        self.plugin_configs_per_instance = {}

        self._parse_instances(data, config_data)
        self._parse_plugin_configs(data)
        self._file_mtime = self._mtime()

    def _parse_instances(self, data: dict, config_data: dict) -> None:
        default_port = config_data.get("default_port")
        default_email = config_data.get("default_email")
        default_plugins = config_data.get("default_plugins_enabled", [])

        for name, ins in data.get("instance", {}).items():
            host = ins.get("host")
            port = ins.get("port") or default_port

            if not (host and port):
                continue

            email = ins.get("email") or default_email
            enabled_plugins = frozenset(ins.get("plugins_enabled", []) + default_plugins)

            self.instances.append(GerritInstance(name, host, port, email, enabled_plugins))

        if not self.instances:
            raise ValueError("No Gerrit instances configured. Please specify at least one instance in the config file.")

        names = [ins.name for ins in self.instances]
        if len(set(names)) != len(names):
            raise ValueError("Instance names must be unique.")

    def _parse_plugin_configs(self, data: dict) -> None:
        for name, conf in data.get("plugin", {}).items():
            self.plugin_configs[name] = {}
            self.plugin_configs_per_instance[name] = {}

            for key, value in conf.items():
                if isinstance(value, dict):
                    self.plugin_configs_per_instance[name][key] = value
                else:
                    self.plugin_configs[name][key] = value

    def get_config_for_plugin(self, plugin_name: str, instance: str) -> dict:
        plugin_config = self.plugin_configs.get(plugin_name, {}).copy()
        instance_config = self.plugin_configs_per_instance.get(plugin_name, {}).get(instance, {})

        plugin_config.update(instance_config)

        return plugin_config

    @property
    def default_instance(self) -> GerritInstance:
        if len(self.instances) == 0:
            raise ValueError("No Gerrit instances configured")
        return self.instances[0]

    def get_instance_by_name(self, name: str) -> GerritInstance | None:
        for ins in self.instances:
            if ins.name == name:
                return ins
        return None

    @property
    def editor(self) -> str | None:
        return self._editor or os.environ.get("EDITOR") or None

    @property
    def ui_refresh_interval_sec(self) -> float:
        return 1 / self.ui_refresh_rate

    def next_layout(self) -> Layout:
        layouts = list(Layout)
        current_index = layouts.index(self.layout)
        self.layout = layouts[(current_index + 1) % len(layouts)]
        return self.layout

    def generate_rich_footnote(self) -> str:
        footnote = f"[dim]interval:[/dim] {self.interval}s"
        # footnote += f" | [dim]layout[/dim]: {self.layout.name}"
        return footnote

    def get_all_enabled_plugins(self) -> set[str]:
        enabled_plugins: set[str] = set()
        for ins in self.instances:
            enabled_plugins.update(ins.enabled_plugins)
        return enabled_plugins

    def get_enabled_plugins_per_instance(self) -> dict[str, frozenset[str]]:
        return {ins.name: ins.enabled_plugins for ins in self.instances}


def generate_example_config(path: Path) -> None:
    if path.exists():
        print(f"Config file already exists at {path}, not overwriting.")
        return

    lines = [
        "[config]",
        'default_host = "gerrit.example.com"',
        "default_port = 22",
        '# default_email = "you@example.com"',
        "# default_plugins_enabled = []",
        "",
    ]

    for field in _FIELDS:
        if field.example is None:
            continue
        line = f"# {field.key} = {field.example}"
        if field.comment:
            line += f"  # {field.comment}"
        lines.append(line)

    lines += [
        "",
        "# [instance.test]",
        '# host = "localhost"',
        "# port = 22",
        '# email = "you@example.com"',
        "# plugins_enabled = []",
    ]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
