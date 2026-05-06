# 023 — Gerrit Action Layer

## Problem

`app.py`'s `_review_*` methods mix two layers of concern:

1. **Portable action logic** — validate the `TrackedChange` (revision known?),
   call `gerrit_comm.review_*`, log the outcome.
2. **TUI side-effects** — set `self.status_msg` with Rich markup, call
   `_start_refresh()`.

Consequences:

- `app.py` grows with logic that has nothing to do with the TUI event loop,
  making it harder to scan (760+ lines).
- The action logic cannot be reused from a future CLI (see spike 014 / feature
  016).

### Latent bugs fixed along the way

Two bugs were introduced by the SSH-communication refactor on
`improve-ssh-communication` and should be fixed here:

1. **Wrong dict key for review errors.** Every `_review_*` method in `app.py`
   checks `if "error" in result:`, but `GerritCommunication._review()` returns
   `{"failure": "..."}` — not `{"error": "..."}`. Review failures are silently
   treated as success, so the green "success" status message appears even when
   Gerrit rejects the operation.

2. **Wrong method name for restore.** `app.py` calls
   `gerrit_comm.query_review_restore(...)`, but the method was renamed
   `review_restore(...)` in the refactor. This raises `AttributeError` at
   runtime.

## Solution

Introduce `gcd/core/actions.py` as a thin action layer between `app.py` and
`gerrit.py`.

Each action function:
- Accepts a resolved `TrackedChange`, `GerritInstance`, and
  `GerritCommunication`.
- Performs domain validation (revision exists, score range, etc.).
- Calls the appropriate `gerrit_comm.review_*` method.
- Logs the outcome.
- Returns a typed `ActionResult`.

`app.py` retains only TUI concerns: instance lookup from config, translating
`ActionResult` into `status_msg` markup, and triggering `_start_refresh()`.

## Data types

```python
ActionStatus = Literal["success", "warning", "failure"]

@dataclass(frozen=True)
class ActionResult:
    status: ActionStatus
    message: str  # plain text, no Rich markup
```

Three states:

| Status | Meaning | App response |
|--------|---------|--------------|
| `"success"` | Action completed | green status_msg + trigger refresh |
| `"warning"` | Not performed, non-fatal (e.g. already submitted) | yellow status_msg, no refresh |
| `"failure"` | Action failed with an error | red status_msg, no refresh |

## New module: `gcd/core/actions.py`

### Imports

```python
from typing import Literal
from dataclasses import dataclass
from gcd.core.gerrit import GerritCommunication
from gcd.core.logs import app_logger
from gcd.core.models import GerritInstance, TrackedChange
```

### Private helper

```python
def _gerrit_result(raw: dict, success_msg: str, failure_prefix: str) -> ActionResult:
    if raw.get("success"):
        return ActionResult("success", success_msg)
    msg = raw.get("failure", "unknown error")
    return ActionResult("failure", f"{failure_prefix}: {msg}")
```

### Functions

All take `(ch: TrackedChange, instance: GerritInstance, comm: GerritCommunication)`
plus any extra arguments. All log a single INFO line with `change=`, `instance=`,
`status=`.

#### `set_automerge`

Guards (checked in order):

1. `ch.current_revision is None` → failure
   `"cannot set automerge for change {ch.number} — no current revision known"`
2. `ch.submitted` → warning
   `"cannot set automerge for change {ch.number} — change is already submitted"`
3. `any(a.label == "Automerge" for a in ch.approvals)` → warning
   `"Label Automerge already exists for change {ch.number}"`

Success: `"Automerge +1 set for change #{ch.number}"`
Failure: `"Automerge failed for change #{ch.number}: {msg}"`

#### `code_review`

Extra param: `score: int`

Guards (checked in order):

1. `score < -2 or score > 2` → failure `"Score out of range: {score}"`
2. `ch.current_revision is None` → failure
   `"cannot set code-review for change {ch.number} — no current revision known"`

Success: `"Code-Review +{score} set for change #{ch.number}"` (sign prefix: `+`
for positive, empty string for zero, `-` already in the int for negative)
Failure: `"Code-Review failed for change #{ch.number}: {msg}"`

#### `abandon`

Guard: `ch.current_revision is None` → failure
`"cannot abandon change {ch.number} — no current revision known"`

Success: `"Change {ch.number} abandoned"`
Failure: `"Abandon failed for change {ch.number}: {msg}"`

#### `restore`

Guard: `ch.current_revision is None` → failure
`"cannot restore change {ch.number} — no current revision known"`

Success: `"Change {ch.number} restored"`
Failure: `"Restore failed for change {ch.number}: {msg}"`

#### `submit`

Guard: `ch.current_revision is None` → failure
`"cannot submit change {ch.number} — no current revision known"`

Success: `"Change {ch.number} submitted"`
Failure: `"Submit failed for change {ch.number}: {msg}"`

#### `rebase`

Guard: `ch.current_revision is None` → failure
`"cannot rebase change {ch.number} — no current revision known"`

Success: `"Rebase triggered for change {ch.number}"`
Failure: `"Rebase failed for change {ch.number}: {msg}"`

## Changes to `app.py`

### New helpers on `App`

```python
def _get_instance_for(self, ch: TrackedChange) -> GerritInstance | None:
    """Resolve instance from config; set red status_msg and return None if not found."""
    instance = self.config.get_instance_by_name(ch.instance)
    if instance is None:
        self.status_msg = f"[red]cannot find instance '{ch.instance}' for change #{ch.number}[/red]"
    return instance

def _apply_result(self, result: ActionResult) -> None:
    """Translate ActionResult into status_msg markup; trigger refresh on success."""
    color = {"success": "green", "warning": "yellow", "failure": "red"}[result.status]
    self.status_msg = f"[{color}]{result.message}[/{color}]"
    if result.status == "success":
        self._start_refresh()
```

### Slimmed `_review_*` methods

Each collapses to 3–4 lines:

```python
def _review_abandon(self, ch: TrackedChange) -> None:
    if (instance := self._get_instance_for(ch)) is None:
        return
    self._apply_result(actions.abandon(ch, instance, self.gerrit_comm))
```

All per-method logging moves to `actions.py`. The `_log.info` / `_log.warning`
calls inside each `_review_*` are removed from `app.py`.

## Responsibility split

| Concern | Location |
|---------|----------|
| Validate `current_revision` | `actions.py` |
| Domain guards (automerge already set, submitted) | `actions.py` |
| Score range validation | `actions.py` |
| Call `gerrit_comm.review_*` | `actions.py` |
| Log action outcome | `actions.py` |
| Resolve instance from config | `app.py` |
| Instance not found → status_msg | `app.py` |
| status_msg markup (green/yellow/red) | `app.py` |
| Trigger `_start_refresh()` | `app.py` |

## Files

| File | Change |
|------|--------|
| `gcd/core/actions.py` | **New.** `ActionStatus`, `ActionResult`, `_gerrit_result`, all six action functions. |
| `gcd/tui/app.py` | Add import, add `_get_instance_for` and `_apply_result` helpers, slim down all six `_review_*` methods, remove review logging. |

## Out of scope

- Future CLI implementation (feature 016).
- Query methods (`_query`, background refresh).
- Any changes to `GerritCommunication` or `ssh.py`.
