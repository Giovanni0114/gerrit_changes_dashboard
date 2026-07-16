# 024 — High-level behavioural test suite

## Problem

The codebase has **zero committed tests**. `pyproject.toml` already configures
pytest 8 (`pythonpath = ["."]`) and the `justfile` has a `test` recipe, but no
`test_*.py` exists. AGENTS.md historically flagged committed tests as premature
because the app changed too rapidly. The architecture has now stabilised enough
around clear seams that a small, high-value behavioural suite is worth locking
in.

This feature adds that suite. The guiding principles are **YAGNI** (only what is
functionally necessary — no exhaustive coverage) and testing **WHAT** the app
does, not **HOW** it renders.

## Scope & philosophy

- **Test WHAT, not HOW.** Assert on state changes, persisted data, dispatched
  actions, and parsed models — never on Rich markup, colours, column widths, or
  layout. `gcd/tui/display.py` is deliberately **not** tested.
- **High level.** Drive behaviour through the real public surface (`App` /
  `AppContext`, `Changes`, `InputHandler`, `AppConfig`) rather than probing
  private rendering internals.
- **Deterministic.** No terminal, no threads, no network. SSH is mocked at the
  single `App.gerrit_comm` seam. Files live under `tmp_path`.
- **Small.** ~30–35 focused tests across 5 files. The suite should catch
  regressions in core behaviour without becoming a maintenance burden.

## Testing seams (why this is feasible)

1. **`AppContext` protocol** (`gcd/core/models.py`) is the full command surface
   the input layer depends on. `App` implements it; a spy can impersonate it.
2. **`App.gerrit_comm`** is a plain attribute set in `App.__init__`
   (`gcd/tui/app.py:112`). Tests replace it with a `FakeGerrit` after
   construction — the only SSH seam.
3. **`Changes(path)` / `SshCache(path)` / `AppConfig(path)`** each take only a
   `Path`, own their own persistence, and expose plain getters — instantiable
   against temp files.
4. **`_store_result(ch, data, cache, plugin_manager)`** (`gcd/tui/app.py:58`) is
   a module-level pure function mapping a Gerrit query dict onto a
   `TrackedChange` — testable in isolation.

## Deliverables

A `tests/` package with a shared `conftest.py` and five test modules.

### `tests/conftest.py` — fixtures

- **`app_env` / temp files.** Writes a minimal valid `config.toml` (one Gerrit
  instance, `changes_path`/`cache_path`/`log_path` pointing inside `tmp_path`),
  plus empty `changes.json` (`[]`) and `cache.json` (`{}`).
- **`app` fixture.** Constructs a real `App(AppConfig(tmp_config_path))` and
  swaps in a `FakeGerrit` for `app.gerrit_comm`. Yields the app; no `run()`, no
  threads.
- **`FakeGerrit` spy.** Stand-in for `GerritCommunication`. Records every call
  and returns canned dicts. Methods used by `App`:
  `query_change`, `query_change_comments`, `query_open_changes`,
  `review_set_automerge`, `review_set_label`, `review_code_review`,
  `review_abandon`, `review_restore`, `review_submit`, `review_rebase`,
  `ssh_request_count`. Configurable per-test to return success or
  `{"error": ...}` / `{"failure": ...}`.
- **`SpyAppContext`.** A record-only object satisfying the `AppContext` protocol
  (via `unittest.mock.MagicMock(spec=AppContext)` or a hand-rolled class with a
  real `config`) for driving `InputHandler` without a full `App`.

> Note: `AppConfig`'s file-path parsers validate that the parent directory
> exists, and `GerritInstance.__post_init__` may call `git config user.email`
> when no email is set. The fixture sets an explicit `default_email` (or per
> instance email) to avoid depending on the host's git config.

### `tests/test_changes_persistence.py` — data integrity

The `Changes` store round-trips through `changes.json` and guards against
conflicting external edits. Covers load/save, dirty-only writes, external-edit
detection, and conflict detection.

### `tests/test_app_behaviors.py` — core WHAT (through `App`/`AppContext`)

Adding changes, toggles, comment operations, delete/restore lifecycle, review
guard logic, and the Gerrit-JSON→model mapping via `_store_result`. SSH is the
`FakeGerrit` spy; assertions are on `Changes`/`TrackedChange` state and on which
`gerrit_comm` methods were invoked.

### `tests/test_input_handler.py` — user-facing WHAT (keys → actions)

Drive `InputHandler.handle_key()` with a spy `AppContext` and assert that
representative real key sequences dispatch the correct `AppContext` method with
the correct `Index`. The exact key bindings are read from the action tables in
`gcd/tui/input_handler/input_engine.py`; a handful of representative flows only,
not exhaustive.

### `tests/test_selection_and_config.py` — selection + config startup

`parse_idx_notation` (underpins every selection) and `AppConfig` loading
(instances, defaults, layout cycling).

## Verification

- `uv run pytest` — all green.
- `uv run ruff check tests/` — clean.

## Out of scope

- Any assertion on Rich rendering (`display.py`): tables, colours, layout,
  panels, footnotes, spinners.
- The `App.run()` main loop, threading, `NoEcho`/termios terminal handling.
- Real SSH / subprocess execution and real network calls.
- Plugin implementations under `gcd/plugins/` (beyond the fact that
  `_store_result` emits events; event emission is verified via a spy where
  cheap, not by exercising concrete plugins).
- Exhaustive coverage or coverage-percentage targets. YAGNI.
- Adding new test dependencies (pytest-mock, pytest-cov, hypothesis). Stdlib
  `unittest.mock` only.

## Open decisions

- **Committing the suite.** AGENTS.md says "don't commit tests." This feature
  is added at explicit user request; whether the resulting `tests/` directory is
  committed to `main` is the user's call and left open here.
