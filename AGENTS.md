# AGENTS.md

> [!IMPORTANT]
> Don't be afraid to change this file or the program's architecture.
> Challenge solutions that feel heavy, overcomplicated, or outdated.

> [!IMPORTANT]
> NEVER PUSH. Prefer amending a few commits over creating many with similar names.
> In terms of amend, prefer --no-edit.

## Project Overview

Terminal-based Gerrit review dashboard. Python 3.12+, Rich for the TUI, SSH for
Gerrit queries (`ssh <host> gerrit query --format=json <hash>`).

Two config files:
- `config.toml` — app settings (read-only at runtime, managed by `config.py::AppConfig`)
- `changes.json` — tracked changes (managed by `changes.py::Changes`, mutated
through the TUI. Manual editing works as a fallback.

Both files are watched via mtime polling; external edits auto-reload.

## Project Management (`pm/` worktree)

`pm/` is a git worktree on the orphan `pm` branch, gitignored in `main`. Specs and
notes live there and are version-controlled on `pm`, not `main`.

- Specs go in `pm/spec/features/` (see `pm/spec/README.md` for the ID scheme and
  folder layout).
- Notes and scratch thinking go in `pm/notes/`.
- Commit spec changes on the `pm` branch (from inside `pm/`), not on feature branches.
- Never `git add -f` anything under `pm/`. Never `rm -rf pm/`.

Before implementing a feature: read its `spec.md` (and the parent EPIC's `spec.md`
if applicable) and `test-cases.md`. Resolve open questions with the user before
coding if they affect core design. Update `spec.md` if implementation reveals
requirements need adjusting.

New feature or EPIC: add an entry to `pm/FEATURES.md` and create the spec folder
per the scheme in `pm/spec/README.md`.

## Commands

```bash
uv sync
uv sync --dev
uv run ruff check . --fix && uv run ruff format .
uv run pytest
python3 gerrit_changes_dashboard.py              # legacy shim
python3 gerrit_changes_dashboard.py --init       # generate example config
uv run gcd                                 # via entry point
uv run gcd --init                          # generate example config
```

> [!IMPORTANT]
> Too early for committed tests — the app changes too rapidly for them to catch
> anything meaningful yet. Temporary tests for development control are fine,
> but don't commit them.

## Code Conventions

Ruff enforces formatting and most style rules — run it and trust it. Beyond that:

- Absolute imports only, grouped stdlib → third-party → local.
- Type hints on all function signatures; PEP 604 unions (`str | None`).
- `@dataclass` for data structures, `Protocol` for structural typing.
- Catch specific exceptions with contextful messages
  (`f"Change '{commit_hash}' has no host"`). Validate early.
- Threading: `threading.Lock` for shared state, `queue.Queue` for message passing,
  `AtomicCounter` for counters.
- Logging via `logs.py` (`app_logger()`, `ssh_logger()`), levels INFO/WARNING/ERROR,
  files under configured `log_dir`.

Match existing patterns in the codebase for UI (Rich), file I/O, and naming.
