# Feature 023 — Gerrit Action Layer: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract review action logic from `app.py` into `gcd/core/actions.py` so
`app.py` becomes a thin TUI adapter and the actions are reusable by a future CLI.

**Architecture:** A new `actions.py` module contains six pure action functions plus
a shared `ActionResult` datatype. `app.py` gains two small helpers
(`_get_instance_for`, `_apply_result`) that translate `ActionResult` into TUI
side-effects. No changes to `gerrit.py` or `ssh.py`.

**Tech Stack:** Python 3.12, stdlib `dataclasses`, `typing.Literal`, existing
`gcd.core.logs`, `gcd.core.models`, `gcd.core.gerrit`.

> **Note on tests:** Per `AGENTS.md`, tests are not committed at this stage.
> Use temporary scripts or manual smoke-testing for verification.

---

## Task 1: Create `gcd/core/actions.py`

**Files:**
- Create: `gcd/core/actions.py`

- [ ] **Step 1: Write `gcd/core/actions.py`**

  ```python
  from dataclasses import dataclass
  from typing import Literal

  from gcd.core.gerrit import GerritCommunication
  from gcd.core.logs import app_logger
  from gcd.core.models import GerritInstance, TrackedChange

  _log = app_logger()

  ActionStatus = Literal["success", "warning", "failure"]


  @dataclass(frozen=True)
  class ActionResult:
      status: ActionStatus
      message: str  # plain text, no Rich markup


  def _gerrit_result(raw: dict, success_msg: str, failure_prefix: str) -> ActionResult:
      if raw.get("success"):
          return ActionResult("success", success_msg)
      msg = raw.get("failure", "unknown error")
      return ActionResult("failure", f"{failure_prefix}: {msg}")


  def set_automerge(ch: TrackedChange, instance: GerritInstance, comm: GerritCommunication) -> ActionResult:
      if ch.current_revision is None:
          return ActionResult("failure", f"cannot set automerge for change {ch.number} — no current revision known")
      if ch.submitted:
          return ActionResult("warning", f"cannot set automerge for change {ch.number} — change is already submitted")
      if any(a.label == "Automerge" for a in ch.approvals):
          return ActionResult("warning", f"Label Automerge already exists for change {ch.number}")
      raw = comm.review_set_automerge(instance, ch.current_revision)
      result = _gerrit_result(raw, f"Automerge +1 set for change #{ch.number}", f"Automerge failed for change #{ch.number}")
      _log.info("set_automerge change=%s instance=%s status=%s", ch.number, ch.instance, result.status)
      return result


  def code_review(ch: TrackedChange, instance: GerritInstance, comm: GerritCommunication, score: int) -> ActionResult:
      if score < -2 or score > 2:
          return ActionResult("failure", f"Score out of range: {score}")
      if ch.current_revision is None:
          return ActionResult("failure", f"cannot set code-review for change {ch.number} — no current revision known")
      raw = comm.review_code_review(instance, ch.current_revision, score)
      sign = "+" if score > 0 else ""
      result = _gerrit_result(
          raw,
          f"Code-Review {sign}{score} set for change #{ch.number}",
          f"Code-Review failed for change #{ch.number}",
      )
      _log.info("code_review change=%s instance=%s score=%d status=%s", ch.number, ch.instance, score, result.status)
      return result


  def abandon(ch: TrackedChange, instance: GerritInstance, comm: GerritCommunication) -> ActionResult:
      if ch.current_revision is None:
          return ActionResult("failure", f"cannot abandon change {ch.number} — no current revision known")
      raw = comm.review_abandon(instance, ch.current_revision)
      result = _gerrit_result(raw, f"Change {ch.number} abandoned", f"Abandon failed for change {ch.number}")
      _log.info("abandon change=%s instance=%s status=%s", ch.number, ch.instance, result.status)
      return result


  def restore(ch: TrackedChange, instance: GerritInstance, comm: GerritCommunication) -> ActionResult:
      if ch.current_revision is None:
          return ActionResult("failure", f"cannot restore change {ch.number} — no current revision known")
      raw = comm.review_restore(instance, ch.current_revision)
      result = _gerrit_result(raw, f"Change {ch.number} restored", f"Restore failed for change {ch.number}")
      _log.info("restore change=%s instance=%s status=%s", ch.number, ch.instance, result.status)
      return result


  def submit(ch: TrackedChange, instance: GerritInstance, comm: GerritCommunication) -> ActionResult:
      if ch.current_revision is None:
          return ActionResult("failure", f"cannot submit change {ch.number} — no current revision known")
      raw = comm.review_submit(instance, ch.current_revision)
      result = _gerrit_result(raw, f"Change {ch.number} submitted", f"Submit failed for change {ch.number}")
      _log.info("submit change=%s instance=%s status=%s", ch.number, ch.instance, result.status)
      return result


  def rebase(ch: TrackedChange, instance: GerritInstance, comm: GerritCommunication) -> ActionResult:
      if ch.current_revision is None:
          return ActionResult("failure", f"cannot rebase change {ch.number} — no current revision known")
      raw = comm.review_rebase(instance, ch.current_revision)
      result = _gerrit_result(raw, f"Rebase triggered for change {ch.number}", f"Rebase failed for change {ch.number}")
      _log.info("rebase change=%s instance=%s status=%s", ch.number, ch.instance, result.status)
      return result
  ```

- [ ] **Step 2: Run ruff to check the new file**

  ```bash
  uv run ruff check gcd/core/actions.py --fix && uv run ruff format gcd/core/actions.py
  ```

  Expected: no errors, file reformatted in place.

---

## Task 2: Update `gcd/tui/app.py`

**Files:**
- Modify: `gcd/tui/app.py`

Two bugs introduced by the SSH refactor are fixed here as part of the rewrite:
- `query_review_restore` → `review_restore` (wrong method name)
- `if "error" in result:` → now handled correctly by `_gerrit_result` in actions.py

- [ ] **Step 1: Add import for `actions` and `ActionResult` after the existing `gcd.core` imports**

  Find the existing imports block (around line 17–21):
  ```python
  from gcd.core.gerrit import GerritCommunication
  from gcd.core.logs import app_logger
  from gcd.core.models import ApprovalEntry, GerritInstance, Index, TrackedChange
  ```

  Add after the `gcd.core.models` import:
  ```python
  from gcd.core import actions
  from gcd.core.actions import ActionResult
  ```

- [ ] **Step 2: Add `_get_instance_for` and `_apply_result` helpers to `App`**

  Add these two methods to `App` just before the `# --- Review methods ---` comment
  (currently around line 142):

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

- [ ] **Step 3: Replace `_review_set_automerge`**

  Old body (~lines 148–176):
  ```python
  def _review_set_automerge(self, ch: TrackedChange) -> None:
      if ch.current_revision is None:
          self.status_msg = f"[red]cannot set automerge for change {ch.number} - no current revision known[/red]"
          return

      if ch.submitted:
          self.status_msg = (
              f"[yellow]cannot set automerge for change {ch.number} - change is already submitted[/yellow]"
          )
          return

      if any(approval.label == "Automerge" for approval in ch.approvals):
          self.status_msg = f"[yellow]Label Automerge already exists for change {ch.number}[/yellow]"
          return

      instance = self.config.get_instance_by_name(ch.instance)
      if instance is None:
          self.status_msg = f"[red]cannot find instance '{ch.instance}' for change #{ch.number}[/red]"
          return

      result = self.gerrit_comm.review_set_automerge(instance, ch.current_revision)

      if "error" in result:
          self.status_msg = f"[red]Automerge failed for change #{ch.number}: {result['error']}[/red]"
          _log.warning("automerge failed change=%s instance=%s error=%s", ch.number, ch.instance, result["error"])
      else:
          self.status_msg = f"[green]Automerge +1 set for change #{ch.number}[/green]"
          _log.info("automerge set change=%s instance=%s", ch.number, ch.instance)
          self._start_refresh()
  ```

  New body:
  ```python
  def _review_set_automerge(self, ch: TrackedChange) -> None:
      if (instance := self._get_instance_for(ch)) is None:
          return
      self._apply_result(actions.set_automerge(ch, instance, self.gerrit_comm))
  ```

- [ ] **Step 4: Replace `_review_code_review`**

  Old body (~lines 182–211):
  ```python
  def _review_code_review(self, ch: TrackedChange, score: int) -> None:
      if score < -2 or score > 2:
          self.status_msg = f"[red]Score out of range: {score}[/red]"
          return

      if ch.current_revision is None:
          self.status_msg = f"[red]cannot set code-review for change {ch.number} - no current revision known[/red]"
          return

      instance = self.config.get_instance_by_name(ch.instance)
      if instance is None:
          self.status_msg = f"[red]cannot find instance '{ch.instance}' for change {ch.number}[/red]"
          return

      result = self.gerrit_comm.review_code_review(instance, ch.current_revision, score)

      if "error" in result:
          self.status_msg = f"[red]Code-Review failed for change #{ch.number}: {result['error']}[/red]"
          _log.warning(
              "code-review failed change=%s instance=%s score=%d error=%s",
              ch.number,
              ch.instance,
              score,
              result["error"],
          )
      else:
          sign = "+" if score > 0 else ""
          self.status_msg = f"[green]Code-Review {sign}{score} set for change #{ch.number}[/green]"
          _log.info("code-review set change=%s instance=%s score=%d", ch.number, ch.instance, score)
          self._start_refresh()
  ```

  New body:
  ```python
  def _review_code_review(self, ch: TrackedChange, score: int) -> None:
      if (instance := self._get_instance_for(ch)) is None:
          return
      self._apply_result(actions.code_review(ch, instance, self.gerrit_comm, score))
  ```

- [ ] **Step 5: Replace `_review_abandon`**

  Old body (~lines 217–235):
  ```python
  def _review_abandon(self, ch: TrackedChange) -> None:
      if ch.current_revision is None:
          self.status_msg = f"[red]cannot abandon change {ch.number} - no current revision known[/red]"
          return

      instance = self.config.get_instance_by_name(ch.instance)
      if instance is None:
          self.status_msg = f"[red]cannot find instance '{ch.instance}' for change {ch.number}[/red]"
          return

      result = self.gerrit_comm.review_abandon(instance, ch.current_revision)

      if "error" in result:
          self.status_msg = f"[red]Abandon failed for change {ch.number}: {result['error']}[/red]"
          _log.warning("abandon failed change=%s instance=%s error=%s", ch.number, ch.instance, result["error"])
      else:
          self.status_msg = f"[green]Change {ch.number} abandoned[/green]"
          _log.info("change abandoned change=%s instance=%s", ch.number, ch.instance)
          self._start_refresh()
  ```

  New body:
  ```python
  def _review_abandon(self, ch: TrackedChange) -> None:
      if (instance := self._get_instance_for(ch)) is None:
          return
      self._apply_result(actions.abandon(ch, instance, self.gerrit_comm))
  ```

- [ ] **Step 6: Replace `_review_restore`** (also fixes the `query_review_restore` bug)

  Old body (~lines 241–259):
  ```python
  def _review_restore(self, ch: TrackedChange) -> None:
      if ch.current_revision is None:
          self.status_msg = f"[red]cannot restore change {ch.number} - no current revision known[/red]"
          return

      instance = self.config.get_instance_by_name(ch.instance)
      if instance is None:
          self.status_msg = f"[red]cannot find instance '{ch.instance}' for change {ch.number}[/red]"
          return

      result = self.gerrit_comm.query_review_restore(instance, ch.current_revision)

      if "error" in result:
          self.status_msg = f"[red]Restore failed for change {ch.number}: {result['error']}[/red]"
          _log.warning("restore failed change=%s instance=%s error=%s", ch.number, ch.instance, result["error"])
      else:
          self.status_msg = f"[green]Change {ch.number} restored[/green]"
          _log.info("change restored change=%s instance=%s", ch.number, ch.instance)
          self._start_refresh()
  ```

  New body:
  ```python
  def _review_restore(self, ch: TrackedChange) -> None:
      if (instance := self._get_instance_for(ch)) is None:
          return
      self._apply_result(actions.restore(ch, instance, self.gerrit_comm))
  ```

- [ ] **Step 7: Replace `_review_submit`**

  Old body (~lines 265–283):
  ```python
  def _review_submit(self, ch: TrackedChange) -> None:
      if ch.current_revision is None:
          self.status_msg = f"[red]cannot submit change {ch.number} - no current revision known[/red]"
          return

      instance = self.config.get_instance_by_name(ch.instance)
      if instance is None:
          self.status_msg = f"[red]cannot find instance '{ch.instance}' for change {ch.number}[/red]"
          return

      result = self.gerrit_comm.review_submit(instance, ch.current_revision)

      if "error" in result:
          self.status_msg = f"[red]Submit failed for change {ch.number}: {result['error']}[/red]"
          _log.warning("submit failed change=%s instance=%s error=%s", ch.number, ch.instance, result["error"])
      else:
          self.status_msg = f"[green]Change {ch.number} submitted[/green]"
          _log.info("change submitted change=%s instance=%s", ch.number, ch.instance)
          self._start_refresh()
  ```

  New body:
  ```python
  def _review_submit(self, ch: TrackedChange) -> None:
      if (instance := self._get_instance_for(ch)) is None:
          return
      self._apply_result(actions.submit(ch, instance, self.gerrit_comm))
  ```

- [ ] **Step 8: Replace `_review_rebase`**

  Old body (~lines 289–307):
  ```python
  def _review_rebase(self, ch: TrackedChange) -> None:
      if ch.current_revision is None:
          self.status_msg = f"[red]cannot rebase change {ch.number} - no current revision known[/red]"
          return

      instance = self.config.get_instance_by_name(ch.instance)
      if instance is None:
          self.status_msg = f"[red]cannot find instance '{ch.instance}' for change {ch.number}[/red]"
          return

      result = self.gerrit_comm.review_rebase(instance, ch.current_revision)

      if "error" in result:
          self.status_msg = f"[red]Rebase failed for change {ch.number}: {result['error']}[/red]"
          _log.warning("rebase failed change=%s instance=%s error=%s", ch.number, ch.instance, result["error"])
      else:
          self.status_msg = f"[green]Rebase triggered for change {ch.number}[/green]"
          _log.info("rebase triggered change=%s instance=%s", ch.number, ch.instance)
          self._start_refresh()
  ```

  New body:
  ```python
  def _review_rebase(self, ch: TrackedChange) -> None:
      if (instance := self._get_instance_for(ch)) is None:
          return
      self._apply_result(actions.rebase(ch, instance, self.gerrit_comm))
  ```

- [ ] **Step 9: Run ruff on both changed files**

  ```bash
  uv run ruff check gcd/core/actions.py gcd/tui/app.py --fix && uv run ruff format gcd/core/actions.py gcd/tui/app.py
  ```

  Expected: no errors. If ruff removes the `ActionResult` import from
  `app.py` as unused (it is only used in the type annotation of `_apply_result`),
  keep it — it documents the interface. Alternatively type the param as
  `result: "ActionResult"` or keep the import and mark with `# noqa` if ruff
  complains.

- [ ] **Step 10: Smoke-test startup**

  ```bash
  uv run gcd --init /tmp/test_config.toml && uv run gcd /tmp/test_config.toml
  ```

  Expected: app launches without `ImportError` or `AttributeError`. Exit with
  `q`. No functional testing of actual Gerrit calls is needed here — the logic
  is covered by the deterministic guard paths in `actions.py`.

---

## Task 3: Commit

- [ ] **Step 1: Stage both files**

  ```bash
  git add gcd/core/actions.py gcd/tui/app.py
  ```

- [ ] **Step 2: Commit**

  ```bash
  git commit -m "extract review action logic into gcd/core/actions.py

  Introduces ActionResult (success/warning/failure) and six action
  functions. app.py becomes a thin TUI adapter via two new helpers
  (_get_instance_for, _apply_result). Also fixes two bugs from the
  SSH refactor: wrong method name query_review_restore and silent
  swallowing of review failures due to wrong dict key check."
  ```

- [ ] **Step 3: Verify**

  ```bash
  git show --stat HEAD
  ```

  Expected output shows exactly two files:
  ```
  gcd/core/actions.py  | ~95 lines (+)
  gcd/tui/app.py       | ~100 lines (-)
  ```
