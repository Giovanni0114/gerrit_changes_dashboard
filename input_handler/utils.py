from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from models import AppContext, Index

if TYPE_CHECKING:
    from .input_engine import LeafAction

Context = dict[str, str]


@dataclass(frozen=True)
class InputField:
    name: str
    special_chars: frozenset[str] = field(default_factory=frozenset)
    digits_only: bool = False
    extra_chars: frozenset[str] = field(default_factory=frozenset)
    special_hint_func: Callable[[AppContext], str] | None = None


def parse_idx_notation(raw: str) -> Index | None:
    """Parse advanced index notation into a Index object.

    Supported formats:
    - Single index: ``"3"``
    - Comma-separated: ``"3,2,4"``
    - Range: ``"3-8"`` (inclusive on both ends)
    - Combined: ``"1-2, 3-5, 11, 23"``

    Whitespace is ignored. Returns ``None`` when the expression is invalid
    """
    if not raw or not raw.strip():
        return None

    stripped = raw.replace(" ", "")
    if not stripped:
        return None

    if stripped == "a":
        return Index(frozenset(), wildcard=True)

    result: set[int] = set()
    for part in stripped.split(","):
        if not part:
            return None
        if "-" in part:
            pieces = part.split("-")
            if len(pieces) != 2 or not pieces[0].isnumeric() or not pieces[1].isnumeric():
                return None
            lo, hi = int(pieces[0]), int(pieces[1])
            if lo > hi:
                return None
            result.update(range(lo, hi + 1))
        elif part.isnumeric():
            result.add(int(part))
        else:
            return None

    return Index(frozenset(result)) if result else None


def instances_hint(app_ctx: AppContext) -> str:
    if not app_ctx.config.instances:
        return "No instances configured"
    return "Instances: " + ", ".join(f"{idx + 1}={inst.name}" for idx, inst in enumerate(app_ctx.config.instances))


def code_review_hint(app_ctx: AppContext) -> str:
    return "-2=Do not submit, -1=I prefer not, 0=No score, +1=Looks good, +2=Approved"


_special_hint_keys = {" ": "<Space>"}


def _get_special_hint_keys(key: str) -> str:
    return _special_hint_keys.get(key, key)


def generate_hints(menu_map: dict[str, LeafAction]) -> str:
    return "  ".join(f"[bold]{_get_special_hint_keys(key)}[/] {item.label}" for key, item in menu_map.items())
