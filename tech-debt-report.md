# Tech-debt report

## 1. Massive duplication in SSH wrappers

`gerrit.py` has 7 near-identical `query_review_*` / `query_set_automerge` /
`query_review_code_review` functions — each ~40 lines of the same scaffolding
(counter/lock → build cmd → `subprocess.run(timeout=30)` → three-way branch on
returncode / timeout → structured log + return dict). Every new Gerrit action
copy-pastes this. Collapse into one helper like
`_run_gerrit_review(action, revision, host, port, extra_args)` — shrinks ~350
lines to ~80.

## 2. Same duplication in `App.review_*` methods

`app.py:135-227` — `set_automerge`, `review_abandon`, `review_rebase`,
`review_restore`, `review_submit`, `review_code_review` all follow the exact
same pattern: `at(row-1)` → check `current_revision` → resolve instance → call
gerrit → branch on `"error"` → log + `_start_refresh()`. Six methods × ~20
lines = 120 lines that could be a single
`_run_review(row, op_name, gerrit_fn, *args)` helper. `set_automerge`
additionally has the duplicate-label guard, which breaks the symmetry.

## 3. `InputHandler` state machine is over-implicit

`input_engine.py:171-344` — 8 mutable fields (`sequence`, `input`,
`current_field`, `context`, `pending_sub_actions`, `pending_menu`,
`current_action`, `active_sub_action`) track states that aren't named
anywhere. `reset()` has to remember all of them (and has silently broken once
already — `active_sub_action` had to be added to it). Valid configurations
aren't enforced by types. A discriminated-union state (`@dataclass Idle`,
`AwaitingField`, `AwaitingSubaction`, ...) would surface invalid transitions at
the type level.

## 4. Hard-coded special case for comment-edit

`input_engine.py:253-262` — `if key == "e":` does a comment-specific pre-fill
inside the generic sub-action dispatcher. It:

- reads `self.app_context.changes[idx - 1].comments`
- silently swallows an invalid-index case (`idx - 1` could be out of range)
- couples the engine to one submenu's semantics

Belongs on the `SubAction` itself (e.g. an optional
`prefill_from: Callable[[AppContext, Context], str | None]`).

## 5. Split-brain sequence matching

`input_engine.py:129-168` — `key_allowed_in_sequence` and `match_action`
duplicate sequence logic with separate `match` statements. `"r"` is both a
top-level refresh (handled by `match_action`'s default branch) *and* a leader
key (`LEADER_ACTIONS["r"]`). `"e": None` in `LEADER_ACTIONS` is a placeholder
whose real resolution lives in a separate `EDITOR_ACTIONS` dict. Readers have
to mentally merge three dicts and two match statements. A single transition
table would be clearer.

## 6. Race-condition workaround in editor launch

`app.py:281-286` — pauses key reader by setting an event, then
`time.sleep(0.15)` in the hope the in-flight `read_key()` finishes. Classic
"hope it's enough" pattern. The reader thread should acknowledge the pause (a
second Event) rather than sleeping.

## 7. Global `NoEcho.instance` singleton with None-checks

`utils.py:50` + `app.py:286-298` — `NoEcho.instance` is a class-level attribute
that gets set in `enable()` and cleared in `disable()`. Callers
`if no_echo is not None` everywhere. A regular instance passed via constructor
(or a module-level getter that raises) would remove the conditional noise.

## 8. `ssh_request_count` as a module global

`gerrit.py:8-10` — `ssh_request_count` + `_ssh_lock` at module scope means
every caller is touching shared state through `global`. Awful for tests, makes
a Gerrit-client class the obvious refactor. Also: the `ssh_requests` parameter
on `build_table` (`display.py:56`) is ignored (the function reads
`gerrit.ssh_request_count` indirectly via the header, not the parameter).

## 9. Manual `mtime` bookkeeping scattered across App

`app.py` — `self.changes_mtime = self.changes.save_changes()` appears 10+
times. Every mutation path has to remember. `FEATURES.md:155-166` (feature
018) already captures this; it's an acknowledged debt.

## 10. `Changes.edit_change` always saves even when nothing changed

`changes.py:49-56` — context manager unconditionally calls `save_changes()` on
exit. No dirty tracking. Combined with #9, every toggle writes the full JSON.

## 11. `AppContext` Protocol is a god-interface

`models.py:61-90` — 20+ methods in one Protocol. Every new feature requires
editing it, creating merge conflicts and long unrelated diffs. Split into
sub-protocols (`SupportsReview`, `SupportsComments`, `SupportsEditor`) and
compose.

## 12. Cache layer reaches into a private field

`cache.py:120` — `ch._snapshot = frozenset(...)`. Same snapshot construction
is duplicated in `app.py:56` (`_store_result`). Private attribute, two
writers, no single source of truth. Move snapshot computation onto
`TrackedChange` itself.

## 13. `TrackedChange` has two overlapping data lanes

`models.py:39-46` has a self-flagged TODO:
`# TODO: DELETE THIS, should not have duplicated data` next to
`subject/project/url/current_revision`. These overlap with cache entries — two
places store the same data, both get written out to JSON.

## 14. `config.py` instance resolution is convoluted

`config.py:96-118` — "if `default_host` set, synthesize a `default` instance;
then walk `[instance.*]`, each inheriting default_host/port/email fallback;
reject empty; reject dup names." The logic spreads across 20 lines of mixed
parsing and validation. Uniqueness check via `len(set(...))` after building —
hard to give a good error message for which name collides.

## 15. `display.build_table` mixes state with styling

`display.py:83-163` — an 80-line flat function that branches on `ch.error`,
`ch.deleted`, `ch.disabled`, `ch.waiting`, per-approval label/value, then
styles hex colors inline. Hard to change the theme; impossible to unit-test a
single rule. Break into `row_style_for(ch)` + `build_cells(ch)`.

## 16. Magic numbers

- `app.py:410` — `manual_refresh_counter.value() >= 5` (no comment on why 5).
- `gerrit.py` — `timeout=30` repeated 7 times across SSH wrappers (no
  constant).
- `logs.py:8-9` — `_MAX_BYTES = 5 * 1024 * 1024` / `_BACKUPS = 5` not
  configurable.

## 17. Arrow handling is stubbed

`input_engine.py:236-239` — `# TODO: create an handling for arrow navigation`
and the key is dropped. Feature 015 in FEATURES.md depends on this.

## 18. `fetch_open_changes` reuses `status_msg` as a control channel

`app.py:479-505` — if email resolution fails for one instance, sets
`self.status_msg` and returns `0`, but the outer loop keeps iterating over
other instances and overwriting the message. User only sees whichever instance
failed last.

## 19. Multi-idx vs single-idx inconsistency

`toggle_waiting/disable/delete/open/automerge-top-level` accept `1-3,5`
notation. `review_*` only accepts a single digit. Spec acknowledges but punts.
Easy for users to hit the mismatch.

## 20. `_fetch_open_changes_from_instance` short-circuits on error but caller doesn't know

Returns `0` both for "no new changes" and "misconfigured email" — caller can't
distinguish.

## Smaller nits

- `input_engine.py:43-44` double blank line (cosmetic).
- `app.py:15` `CacheEntry` imported but unused.
- `context_actions.py` several handlers take `ctx` unused (Pyright warnings);
  signature conformance — could be documented rather than silenced.
- `changes.py:50-56` `edit_change` yields `None` when idx invalid but callers
  don't uniformly handle it (some do `if ch is None: return`, but the save
  still runs at exit).
- `input_handler/input_engine.py:316-334` `_start_field_collection` is dead
  (never called after `_try_execute` fallthrough — worth verifying).

## Top 3 to tackle first

1. **Factor the SSH wrappers + App review methods** (#1, #2) — the most code,
   the most benefit, zero risk, purely mechanical.
2. **Model `InputHandler` state as a union** (#3) — prevents the next "forgot
   to reset X" bug as the state grows.
3. **Extract snapshot + remove duplicate data on `TrackedChange`** (#12, #13)
   — removes the two-writers-one-private-field smell and the self-flagged
   TODO.
