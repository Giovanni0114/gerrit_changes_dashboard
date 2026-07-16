"""Small helpers shared across test modules.

Imported as a top-level module thanks to pytest's ``prepend`` import mode
(the tests directory is placed on ``sys.path``).
"""

from __future__ import annotations

from gcd.core.models import Index, TrackedChange


def idx(*positions: int, wildcard: bool = False) -> Index:
    """Build an ``Index`` from 1-based row positions."""
    return Index(frozenset(positions), wildcard=wildcard)


def sync_map(app) -> None:
    """Populate the changes index map to match the default (flat) layout.

    ``Index.resolve`` looks changes up via ``Changes.at`` which reads the index
    map normally built during rendering; tests must set it explicitly.
    """
    app.changes.set_map([ch.id for ch in app.changes.get_all()])


def add(app, number: int, instance: str = "prod", **kwargs) -> TrackedChange:
    """Append a tracked change to the app and refresh the index map."""
    ch = TrackedChange(number=number, instance=instance, **kwargs)
    app.changes.append(ch)
    sync_map(app)
    return ch
