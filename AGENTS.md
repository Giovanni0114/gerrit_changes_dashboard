# AGENTS.md - Development Guidelines

This document provides guidelines for agentic coding agents operating in this repository.

> [!IMPORTANT]
> Don't be afraid to make changes in both this AGENTS.md file and in architecture of the program.
> Challenge existing solutions if these feel heavy, overcomplicated or outdated.

> [!TIP]
> The `spec/` directory is listed in `.gitignore` and is a good scratch space for specs, plans,
> and design documents. Use it freely — nothing there will be committed.

## Project Overview

Gerrit Approvals Dashboard is a terminal-based monitoring tool built with
Python 3.12+ and Rich. It displays real-time approval status for Gerrit code
reviews via SSH queries.

Configuration is split into two files:
- **TOML config** (`config.toml`) — app settings: interval, default host/port, email, editor,
  and path to the changes file. Managed by `config.py` (`AppConfig` class).
- **JSON changes file** (`changes.json`) — tracked Gerrit changes. Managed by `changes.py`
  (`Changes` class). **Not intended for manual editing** — all mutations happen through the
  TUI (add, delete, toggle flags, comments, fetch) and are persisted automatically via
  `Changes.save_changes()`. Manual editing is still possible but is a fallback, not the
  primary workflow.

The TUI provides keybind-driven change management (`<Space>` leader key), including
adding changes, auto-fetching open changes from Gerrit, toggling waiting/disabled/deleted
states, managing comments, and purging submitted changes.


## Build & Development Commands

### Setup
```bash
uv sync              # Install dependencies (uses uv package manager)
```

### Linting & Formatting
```bash
uv run ruff check .                           # Check code style violations
uv run ruff check . --fix                     # Auto-fix style violations
uv run ruff format .                          # Format code
```

### Running the Application
```bash
python3 gerrit_changes_dashboard.py                  # Run with default config.toml
python3 gerrit_changes_dashboard.py <config_file>    # Run with custom TOML config
python3 gerrit_changes_dashboard.py --init           # Generate example config.toml
```

### Testing
```bash
uv sync --dev        # Install dev dependencies (pytest)
uv run pytest        # Run all tests
uv run pytest -v     # Verbose output
```

> [!IMPORTANT]
> ITS TOO EARLY TO CREATE TESTS
> This app have such rapid development that creating tests that really catches
> important stuff is generally impossible.
> After creating version that will not be completly changed every week we will
> create tests. You can create temporary tests for the sake of control
> development, but don't commit anything for now

## Code Style Guidelines

### Imports
- Use absolute imports only (no relative imports)
- Group imports: standard library → third-party → local modules
- One blank line between groups
- Use `from X import Y` for specific items
- Example:
  ```python
  import json
  import sys
  from pathlib import Path
  
  from rich.console import Console
  
  from models import TrackedChange
  from utils import log
  ```

### Formatting & Line Length
- Line length: 120 characters (configured in ruff)
- Use double quotes for strings (`"string"`)
- 4-space indentation (Python default)
- One blank line between top-level functions/classes
- Two blank lines between top-level definitions

### Type Annotations
- Always use type hints for function parameters and return types
- Use `|` syntax for unions (Python 3.10+ style): `str | None`, not `Optional[str]`
- Use `from typing import` for advanced types (Protocol, Iterable, etc.)
- Annotate class attributes in `__init__`
- Example:
  ```python
  def load_changes(self, default_host: str | None, default_port: int | None) -> None:
      """Load tracked changes from JSON file, applying defaults."""
      data = json.loads(self.path.read_text(encoding="utf-8"))
      self.changes = [TrackedChange(**entry) for entry in data]
  ```

### Naming Conventions
- **Functions/variables**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE` (used rarely)
- **Private methods/attributes**: Prefix with `_` (e.g., `_internal_method`)
- **Protocols**: `PascalCase` suffix with `Protocol` (e.g., `AppContext`)

### Error Handling
- Catch specific exceptions, not bare `except:`
- Provide context in error messages: `f"Change '{commit_hash}' has no host"`
- Validate input early with clear error messages:
  ```python
  if interval < 1:
      raise ValueError(f"interval must be >= 1, got {interval}")
  ```
- Use OSError for file/system operations
- Log errors with context via `log(category, message, level="ERROR")`

### Docstrings
- Use docstrings for public functions and classes
- Format: One-line summary, then blank line, then details (if needed)
- Use reStructuredText-style for parameters in longer docstrings
- Example:
  ```python
  def update_config_field(path: Path, commit_hash: str, field: str, value: object) -> float:
      """Set field=value for the entry matching commit_hash. Returns new mtime.
      
      Only used for 'waiting' and 'disabled' fields (NOT 'deleted' which is in-memory only).
      """
  ```

### Concurrency & Threading
- Use `threading.Lock()` for shared state protection
- Always use locks when accessing/modifying shared data
- Use `queue.Queue` for thread-safe message passing
- Document thread-safety assumptions in docstrings
- Example: `_log_lock` protects concurrent log writes

### Dataclasses & Type Safety
- Prefer `@dataclass` for simple data structures (see `TrackedChange` model)
- Use `Protocol` for structural typing (e.g., `AppContext`)
- Always provide default values with type hints

### JSON & File I/O
- Always use `encoding="utf-8"` for file operations
- Pretty-print JSON with `indent=2` for readability:
  ```python
  path.write_text(json.dumps(data, indent=2) + "\n")
  ```
- Use `Path` from `pathlib` (not `os.path`)

### Rich Library (UI)
- Use `Console()` for output: `self.console.print(msg)`
- Use `Table` for structured data
- Use `Live` for real-time updates
- Document Rich objects and state management clearly

### Logging
- Use the custom `log(category, message, level="INFO")` function
- Categories: "GERRIT", "CONFIG", "APP", "INPUT", etc.
- Levels: "INFO", "WARNING", "ERROR"
- Logs stored in `logs/{YYYYMMDD}-{HHMMSS}.log`

## Key Patterns

### Config Management
- Configuration is split into two files:
  - **TOML config** (`config.toml`) — app settings, read-only at runtime. Managed by `config.py` (`AppConfig`).
  - **JSON changes file** (`changes.json`) — tracked changes. Managed by `changes.py` (`Changes`).
- The JSON changes file is **not intended for manual editing**. All mutations happen through
  the TUI and are persisted automatically via `Changes.save_changes()`.
- Use `Changes.edit_change()` / `edit_changes()` context managers for safe single/batch
  mutations — they auto-save on exit.
- Watch both files via `mtime` polling; external edits trigger auto-reload.

### Thread-Safe State
- Use `AtomicCounter` for simple numeric state
- Use `Lock` for complex state modifications
- Document synchronized access patterns

### SSH Queries
- All Gerrit queries use SSH: `ssh <host> gerrit query --format=json <hash>`
- Parse JSON output from SSH stdout
- Handle connection failures gracefully

## Ruff Configuration

Active linting rules (from pyproject.toml):
- `E`: pycodestyle errors (PEP 8 compliance)
- `F`: Pyflakes (undefined names, unused imports)
- `I`: isort (import sorting)
- `B`: flake8-bugbear (common bugs)
- `RUF`: Ruff-specific rules (modernizations)

Run `uv run ruff check . --fix` to auto-correct most issues.

## Python Version
- Minimum: Python 3.12
- Use modern syntax: walrus operator `:=`, match statements, etc.
- Type hints use PEP 604 (`X | Y` not `Union[X, Y]`)

## Dependencies
- **rich**: Terminal rendering and UI
- **fastmcp** (optional): Model Context Protocol support

## Working with Features

New features are tracked in `FEATURES.md` with brief PM-style descriptions.

### ID scheme

- Standalone feature: `001`, `002`, … — folder `spec/features/001-name/`
- EPIC: `EPIC001`, `EPIC002`, … — folder `spec/features/EPIC001-name/`
- Feature inside an EPIC: `EPIC001-001`, `EPIC001-002`, … — subfolder
  `spec/features/EPIC001-name/EPIC001-001-feature-name/`

### Folder contents

Each standalone feature folder and each EPIC sub-feature folder contains:
- `spec.md` — requirements, acceptance criteria, open questions
- `test-cases.md` — concrete test scenarios to implement and verify

Each EPIC folder contains:
- `spec.md` — EPIC overview, motivation, and how the sub-features fit together
- One subfolder per sub-feature (each with its own `spec.md` and `test-cases.md`)

### Before implementing a feature

1. Read the feature's `spec.md` in full. For EPIC features also read the parent
   EPIC `spec.md` for context.
2. Check `test-cases.md` — these drive the test suite for the feature.
3. Note any open questions in `spec.md`; resolve them with the user before
   writing code if they affect core design decisions.
4. Update `spec.md` if the implementation reveals that requirements need
   adjusting (note what changed and why).

### Adding a new feature or EPIC

1. Add a concise entry to `FEATURES.md` (PM-style notes, no heavy structure).
2. For a standalone feature: create `spec/features/<id>-<name>/spec.md` and
   `test-cases.md`.
3. For an EPIC: create `spec/features/EPIC<id>-<name>/spec.md` (overview), then
   add a subfolder per sub-feature with its own `spec.md` and `test-cases.md`.
4. Keep spec files focused on *what* and *why*; leave *how* to the implementation.

## Common Tasks

### Adding a New Module
1. Follow import grouping rules
2. Add type hints to all functions
3. Use docstrings for public APIs
4. Use snake_case for module names
5. Ensure ruff compliance: `uv run ruff check <file> --fix`

### Modifying Config Loading
1. For TOML settings: update `AppConfig.load_config()` in `config.py`
2. For changes file structure: update `Changes.load_changes()` / `save_changes()` in `changes.py`
   and the `TrackedChange` dataclass in `models.py`
3. Test with invalid configs to verify error messages
4. Document new fields in README.md

### Thread-Safe Changes
1. Identify all shared state (e.g., `self.results`, `self.submitted_keys`)
2. Protect with locks or atomic operations
3. Document lock usage in comments
4. Test concurrent modifications to verify correctness
