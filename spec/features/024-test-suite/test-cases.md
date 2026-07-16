# 024 — Test Cases

Each case names the module it belongs to. All tests use `tmp_path`, the `app`
fixture, and `FakeGerrit`/`SpyAppContext` as described in the spec. No terminal,
threads, or network.

---

## tests/test_changes_persistence.py

### TC-001: Add + save round-trips to disk
Append a `TrackedChange(number=123, instance="default")`, call
`save_changes()`, construct a fresh `Changes(path)`, and verify the change is
present via `by_id` / `get_all`.

### TC-002: Save is a no-op when nothing modified
On a freshly loaded store with no mutations, `save_changes()` returns `False`
and does not alter the file mtime.

### TC-003: Save persists only when dirty
Mutate a tracked field that participates in dirty tracking (e.g. append a
comment or set `waiting`), then `save_changes()` returns `True` and a reload
reflects the change.

### TC-004: External edit is detected
After load, rewrite `changes.json` on disk (new mtime). `is_file_changed()`
returns `True`.

### TC-005: Conflicting external edit raises on save
Load, mutate an in-memory change (so it is dirty), then externally rewrite
`changes.json`. `save_changes()` raises `RuntimeError` (conflict detected)
rather than clobbering the external edit.

### TC-006: load_changes rejects a non-list root
A `changes.json` whose JSON root is an object (not a list) raises `ValueError`
on load.

---

## tests/test_app_behaviors.py

### TC-101: add_change appends to the store
`app.add_change(456, "default")` increases `changes.count()` by one, the new
change is retrievable, and `status_msg` is set.

### TC-102: toggle_waiting flips the flag
Given a tracked change at index 1, `toggle_waiting(Index.single(1))` sets
`waiting=True`; a second call clears it.

### TC-103: toggle_deleted / toggle_disabled flip their flags
Analogous to TC-102 for `deleted` and `disabled`.

### TC-104: add_comment appends to ch.comments
`add_comment(Index.single(1), "hello")` appends `"hello"` to the change's
`comments` list.

### TC-105: edit_last_comment replaces the last comment
With existing comments, `edit_last_comment(Index.single(1), "new")` replaces the
last entry, preserving earlier ones.

### TC-106: delete_comment removes the addressed comment
`delete_comment(rows, comment_idx)` removes the correct comment by index.

### TC-107: delete_all_submitted removes submitted changes
Given a mix of submitted and running changes, `delete_all_submitted()` marks the
submitted ones deleted (and leaves running ones untouched).

### TC-108: restore_all clears deleted flags
After some changes are deleted, `restore_all()` clears `deleted` on all.

### TC-109: review_set_automerge guard — no current revision
A change with `current_revision is None`: `review_set_automerge` sets a red/
warning `status_msg` and does **not** call `gerrit_comm.review_set_automerge`.

### TC-110: review_set_automerge guard — already submitted
A submitted change: no gerrit call; a warning `status_msg` is set.

### TC-111: review_set_automerge guard — label already present
A change already carrying an `Automerge` approval: no gerrit call; warning
status.

### TC-112: review_set_automerge success path calls gerrit
A valid change (has `current_revision`, not submitted, no Automerge label):
`review_set_automerge` calls `FakeGerrit.review_set_automerge` exactly once with
the change's `current_revision`.

### TC-113: review failure surfaces an error status
With `FakeGerrit` returning an error for the review, the success branch is not
taken (no refresh); `status_msg` reflects failure.

### TC-114: _store_result maps query dict onto the change
Feed a representative Gerrit query dict (subject, project, url, currentPatchSet
with approvals) through `_store_result`; assert `subject`, `project`, `url`,
`current_revision`, and the parsed `approvals` land on the `TrackedChange`.

### TC-115: _store_result derives status flags
A dict with `status="ABANDONED"` sets `abandoned=True`; a SUBM approval sets
`submitted=True`; `wip` sets `is_wip=True`.

### TC-116: _store_result records an error entry
A dict containing `{"error": ...}` sets `ch.error` and leaves other fields
untouched.

---

## tests/test_input_handler.py

### TC-201: add-change key sequence dispatches add_change
Drive the real key sequence for adding a change through
`InputHandler.handle_key()` against a `SpyAppContext`; assert `add_change` is
called with the expected arguments.

### TC-202: a toggle key sequence dispatches the toggle
A representative toggle sequence (e.g. waiting) dispatches the matching
`AppContext` toggle with the correct `Index`.

### TC-203: a comment key sequence dispatches add_comment
Driving the comment-add sequence dispatches `add_comment` with the parsed
`Index` and text.

### TC-204: wildcard index "a" resolves to a wildcard Index
A sequence using the `a` wildcard in the index field passes an `Index` with
`wildcard=True` to the dispatched action.

### TC-205: <esc> aborts the in-progress sequence
Pressing `<esc>` mid-sequence resets the handler (no action dispatched, handler
back to top level).

> Exact keys are taken from `TOP_LEVEL_ACTIONS` / `LEADER_ACTIONS` /
> `COMMENT_ACTIONS` / `REVIEW_ACTIONS` in `input_engine.py` when the tests are
> written; the cases above are representative flows, not an exhaustive binding
> map.

---

## tests/test_selection_and_config.py

### TC-301: parse_idx_notation — single index
`"3"` → `Index` containing `{3}`, `wildcard=False`.

### TC-302: parse_idx_notation — comma-separated
`"3,2,4"` → `{2, 3, 4}`.

### TC-303: parse_idx_notation — inclusive range
`"3-6"` → `{3, 4, 5, 6}`.

### TC-304: parse_idx_notation — combined + whitespace
`"1-2, 3, 11"` → `{1, 2, 3, 11}`.

### TC-305: parse_idx_notation — wildcard
`"a"` → `Index` with `wildcard=True` and empty value set.

### TC-306: parse_idx_notation — invalid inputs return None
Empty string, `"1-"`, `"x"`, `"3-1"` (reversed range) each return `None`.

### TC-307: AppConfig loads instances from TOML
A config with one `[instance.X]` table yields exactly one `GerritInstance` with
the expected `name`/`host`/`port`.

### TC-308: AppConfig applies defaults
Omitted `interval` / `ui_refresh_rate` fall back to their documented defaults.

### TC-309: AppConfig.next_layout cycles the Layout enum
Repeated `next_layout()` calls cycle through all `Layout` members and wrap back
to the start.
