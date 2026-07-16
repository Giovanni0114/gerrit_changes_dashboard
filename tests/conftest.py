"""Shared fixtures and spies for the behavioural test suite.

Everything here is deterministic: no terminal, no threads, no network. SSH is
replaced by ``FakeGerrit`` at the single ``App.gerrit_comm`` seam, and all files
live under ``tmp_path``.
"""

from __future__ import annotations

import inspect
import json
from unittest.mock import MagicMock

import pytest

from gcd.core.changes import Changes
from gcd.core.config import AppConfig
from gcd.core.models import AppContext
from gcd.tui.app import App
from gcd.tui.input_handler import InputHandler

CONFIG_TOML = """\
[config]
default_port = 22
default_email = "tester@example.com"
interval = 30
ui_refresh_rate = 20
changes_file = "./changes.json"
cache_file = "./cache.json"
log_dir = "./log"

[instance.prod]
host = "gerrit.example.com"

[instance.staging]
host = "gerrit-staging.example.com"
"""


class FakeGerrit:
    """Stand-in for ``GerritCommunication`` that records calls and returns canned dicts.

    Tests tweak ``query_response`` / ``review_response`` / ``open_changes`` to
    steer behaviour, and inspect ``calls`` (a list of ``(method, args)`` tuples)
    to assert what the app asked the SSH layer to do.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.query_response: dict = {}
        self.review_response: dict = {"success": True}
        self.open_changes: list[dict] = []

    @property
    def ssh_request_count(self) -> int:
        return len(self.calls)

    def _record(self, name: str, *args) -> None:
        self.calls.append((name, args))

    def called(self, name: str) -> bool:
        return any(call == name for call, _ in self.calls)

    # --- queries ---

    def query_change(self, instance, change_id):
        self._record("query_change", instance, change_id)
        return dict(self.query_response)

    def query_change_comments(self, instance, change_id):
        self._record("query_change_comments", instance, change_id)
        return []

    def query_open_changes(self, instance):
        self._record("query_open_changes", instance)
        return list(self.open_changes)

    # --- reviews ---

    def review_set_automerge(self, instance, revision):
        self._record("review_set_automerge", instance, revision)
        return dict(self.review_response)

    def review_code_review(self, instance, revision, score):
        self._record("review_code_review", instance, revision, score)
        return dict(self.review_response)

    def review_abandon(self, instance, revision):
        self._record("review_abandon", instance, revision)
        return dict(self.review_response)

    def review_restore(self, instance, revision):
        self._record("review_restore", instance, revision)
        return dict(self.review_response)

    def review_submit(self, instance, revision):
        self._record("review_submit", instance, revision)
        return dict(self.review_response)

    def review_rebase(self, instance, revision):
        self._record("review_rebase", instance, revision)
        return dict(self.review_response)


@pytest.fixture
def config_path(tmp_path):
    """Write a minimal valid config + empty state files under tmp_path."""
    cfg = tmp_path / "config.toml"
    cfg.write_text(CONFIG_TOML)
    (tmp_path / "changes.json").write_text(json.dumps([]) + "\n")
    (tmp_path / "cache.json").write_text(json.dumps({}) + "\n")
    return cfg


@pytest.fixture
def config(config_path):
    return AppConfig(config_path)


@pytest.fixture
def fake_gerrit():
    return FakeGerrit()


@pytest.fixture
def app(config, fake_gerrit):
    """A real ``App`` with SSH mocked. No ``run()``, no threads."""
    app = App(config)
    app.gerrit_comm = fake_gerrit
    return app


def _protocol_methods() -> list[str]:
    """Names of the callable members declared on the AppContext protocol."""
    return [
        name for name, member in vars(AppContext).items() if inspect.isfunction(member) and not name.startswith("_")
    ]


class SpyAppContext:
    """Records ``AppContext`` method calls while reusing a real config/changes.

    Every protocol method is a ``MagicMock``, generated from the protocol itself
    so there is no per-method boilerplate and the spy stays in sync as
    ``AppContext`` grows. A real ``AppConfig`` is reused so flows that resolve
    domain data (e.g. ``add_change`` picking the default instance) stay
    meaningful without stubbing.
    """

    def __init__(self, config: AppConfig, changes: Changes) -> None:
        self.config = config
        self.changes = changes
        self.status_msg = ""
        for name in _protocol_methods():
            setattr(self, name, MagicMock(name=name))


@pytest.fixture
def spy_ctx(config, tmp_path):
    changes = Changes(tmp_path / "spy_changes.json")
    return SpyAppContext(config, changes)


@pytest.fixture
def input_handler(spy_ctx):
    return InputHandler(spy_ctx)
