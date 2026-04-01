# AGENTS.md - Development Guidelines

This document provides guidelines for agentic coding agents operating in this repository.

> [!IMPORTANT]
> Don't be afraid to make changes in both this AGENTS.md file and in architecture of the program.
> Challenge existing solutions if these feel heavy, overcomplicated or outdated.

## Project Overview

Gerrit Approvals Dashboard is a terminal-based monitoring tool built with
Python 3.12+ and Rich. It displays real-time approval status for Gerrit code
reviews via SSH queries.


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
python3 gerrit_approvals.py                  # Run dashboard with default config
python3 gerrit_approvals.py <config_file>    # Run with custom config
python3 gerrit_approvals.py --init           # Generate example config
```

### Testing
No automated test framework configured. Currently verify by:
- Running the application and checking terminal output
- Checking for SSH connectivity to Gerrit hosts
- Verifying JSON config parsing with valid/invalid configs

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
  
  from models import Change
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
  def load_config(path: Path) -> tuple[list[Change], int, str | None]:
      """Docstring describing function."""
      data = json.loads(path.read_text())
      return changes, interval, default_host
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
- Prefer `@dataclass` for simple data structures (see `Change` model)
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
- All config is JSON-based (`approvals.json`)
- Watch config file via `mtime` polling (see `config_mtime()`)
- Validate on load with clear error messages

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

## Common Tasks

### Adding a New Module
1. Follow import grouping rules
2. Add type hints to all functions
3. Use docstrings for public APIs
4. Use snake_case for module names
5. Ensure ruff compliance: `uv run ruff check <file> --fix`

### Modifying Config Loading
1. Update JSON schema in `approvals.schema.json` if structure changes
2. Update validation in `load_config()` in `config.py`
3. Test with invalid configs to verify error messages
4. Document new fields in README.md

### Thread-Safe Changes
1. Identify all shared state (e.g., `self.results`, `self.submitted_keys`)
2. Protect with locks or atomic operations
3. Document lock usage in comments
4. Test concurrent modifications to verify correctness
