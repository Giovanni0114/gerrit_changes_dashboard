from collections.abc import Callable
from enum import Enum
from pathlib import Path

Parser = Callable[[str, object, Path], object]

_TRUTHY = {"y", "yes", "1", "true"}


def _int_parser(default: int, *, minimum: int | None = None) -> Parser:
    def parse(name: str, raw: object, base_dir: Path) -> int:
        if raw is None:
            return default
        try:
            value = int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError) as ex:
            raise ValueError(f"Invalid value for '{name}': expected an integer, got {raw!r}") from ex
        if minimum is not None and value < minimum:
            raise ValueError(f"'{name}' must be >= {minimum}, got {value}")
        return value

    return parse


def _float_parser(default: float, *, minimum: float | None = None) -> Parser:
    def parse(name: str, raw: object, base_dir: Path) -> float:
        if raw is None:
            return default
        try:
            value = float(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError) as ex:
            raise ValueError(f"Invalid value for '{name}': expected a number, got {raw!r}") from ex
        if minimum is not None and value < minimum:
            raise ValueError(f"'{name}' must be >= {minimum}, got {value}")
        return value

    return parse


def _bool_parser(default: bool) -> Parser:
    def parse(name: str, raw: object, base_dir: Path) -> bool:
        if raw is None:
            return default
        return str(raw).strip().lower() in _TRUTHY

    return parse


def _enum_parser(enum_cls: type[Enum], default: Enum) -> Parser:
    def parse(name: str, raw: object, base_dir: Path) -> Enum:
        if raw is None:
            return default
        try:
            return enum_cls(raw)
        except ValueError as ex:
            valid = ", ".join(member.value for member in enum_cls)
            raise ValueError(f"Invalid value for '{name}': {raw!r}. Expected one of: {valid}") from ex

    return parse


def _str_parser(default: str | None = None) -> Parser:
    def parse(name: str, raw: object, base_dir: Path) -> str | None:
        return raw if raw is not None else default  # type: ignore[return-value]

    return parse


def _file_path_parser(default: str) -> Parser:
    """Resolve a file path relative to the config dir; its parent must be a dir."""

    def parse(name: str, raw: object, base_dir: Path) -> Path:
        path = (base_dir / (raw or default)).resolve()  # type: ignore[arg-type]
        parent = path.parent
        if not parent.exists():
            raise ValueError(f"Directory for '{name}' does not exist: {parent}")
        if not parent.is_dir():
            raise ValueError(f"Directory for '{name}' is not a directory: {parent}")
        return path

    return parse


def _dir_path_parser(default: str) -> Parser:
    """Resolve a directory path relative to the config dir; must be a dir if it exists."""

    def parse(name: str, raw: object, base_dir: Path) -> Path:
        path = (base_dir / (raw or default)).resolve()  # type: ignore[arg-type]
        if path.exists() and not path.is_dir():
            raise ValueError(f"'{name}' exists but is not a directory: {path}")
        return path

    return parse
