from dataclasses import dataclass, field
from typing import Callable

from models import AppContext

Context = dict[str, str]


@dataclass(frozen=True)
class InputField:
    name: str
    special_chars: frozenset[str] = field(default_factory=frozenset)
    digits_only: bool = False
    extra_chars: frozenset[str] = field(default_factory=frozenset)
    special_hint_func: Callable[[AppContext], str] | None = None


def parse_idx_notation(raw: str, max_idx: int) -> list[int] | None:
    """Parse advanced index notation into a sorted list of unique 1-based indexes.

    Supported formats:
    - Single index: ``"3"``
    - Comma-separated: ``"3,2,4"``
    - Range: ``"3-8"`` (inclusive on both ends)
    - Combined: ``"1-2, 3-5, 11, 23"``

    Whitespace is ignored. Returns ``None`` when the expression is invalid or any
    index falls outside ``[1, max_idx]``.
    """
    if not raw or not raw.strip():
        return None

    stripped = raw.replace(" ", "")
    if not stripped:
        return None

    result: set[int] = set()
    for part in stripped.split(","):
        if not part:
            return None  # empty segment, e.g. "1,,3"
        if "-" in part:
            pieces = part.split("-")
            if len(pieces) != 2 or not pieces[0] or not pieces[1]:
                return None
            if not pieces[0].isnumeric() or not pieces[1].isnumeric():
                return None
            lo, hi = int(pieces[0]), int(pieces[1])
            if lo > hi:
                return None
            if lo < 1 or hi > max_idx:
                return None
            result.update(range(lo, hi + 1))
        else:
            if not part.isnumeric():
                return None
            val = int(part)
            if val < 1 or val > max_idx:
                return None
            result.add(val)

    return sorted(result) if result else None


def instances_hint(app_ctx: AppContext) -> str:
    if not app_ctx.config.instances:
        return "No instances configured"
    return "Instances: " + ", ".join(f"{idx + 1}={inst.name}" for idx, inst in enumerate(app_ctx.config.instances))
