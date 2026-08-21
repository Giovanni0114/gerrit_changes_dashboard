"""Cache persistence — save_file only writes when the in-memory cache changed.

Idle CPU regression guard: reload_config() calls SshCache.save_file() on a timer,
so it must be a cheap no-op when nothing in the cache actually changed.
"""

from __future__ import annotations

import json

from gcd.core.cache import SshCache
from gcd.core.models import TrackedChange


def test_save_is_noop_right_after_load(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text(json.dumps({}) + "\n")
    cache = SshCache(path)

    assert cache.save_file() is False


def test_save_persists_after_caching_a_change(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text(json.dumps({}) + "\n")
    cache = SshCache(path)

    cache.cache(TrackedChange(number=1, instance="prod", subject="hi"))

    assert cache.save_file() is True
    assert "1:prod" in json.loads(path.read_text())


def test_save_is_noop_on_second_call(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text(json.dumps({}) + "\n")
    cache = SshCache(path)
    cache.cache(TrackedChange(number=1, instance="prod"))

    assert cache.save_file() is True
    assert cache.save_file() is False  # nothing changed since the last write


def test_evict_removing_entries_marks_dirty(tmp_path):
    path = tmp_path / "cache.json"
    cache = SshCache(path)
    cache.cache(TrackedChange(number=1, instance="prod"))
    cache.save_file()

    removed = cache.evict(set())  # keep nothing
    assert removed == 1
    assert cache.save_file() is True


def test_evict_removing_nothing_stays_clean(tmp_path):
    path = tmp_path / "cache.json"
    cache = SshCache(path)
    cache.cache(TrackedChange(number=1, instance="prod"))
    cache.save_file()

    cache.evict({(1, "prod")})  # keep everything
    assert cache.save_file() is False


def test_owner_and_patchset_round_trip_through_cache(tmp_path):
    path = tmp_path / "cache.json"
    cache = SshCache(path)
    source = TrackedChange(
        number=1,
        instance="prod",
        owner={"name": "Jane Doe", "email": "jane@example.com"},
        current_patchset_number=4,
    )

    cache.cache(source)
    assert cache.save_file() is True

    target = TrackedChange(number=1, instance="prod")
    SshCache(path).hydrate(target)

    assert target.owner == {"name": "Jane Doe", "email": "jane@example.com"}
    assert target.current_patchset_number == 4


def test_cache_without_owner_remains_readable(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text(
        json.dumps(
            {
                "1:prod": {
                    "subject": "cached subject",
                    "project": "team/project",
                    "url": None,
                    "current_revision": None,
                    "current_patchset_number": "4",
                    "submitted": False,
                    "abandoned": False,
                    "is_wip": False,
                    "approvals": [],
                }
            }
        )
        + "\n"
    )
    target = TrackedChange(number=1, instance="prod")

    SshCache(path).hydrate(target)

    assert target.subject == "cached subject"
    assert target.owner is None
    assert target.current_patchset_number == 4
