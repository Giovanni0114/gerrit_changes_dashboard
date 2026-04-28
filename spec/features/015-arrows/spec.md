# 015 — Arrow Navigation and Multi-Selection

## Problem

Today, every action that targets a change (`<Space>w`, `<Space>x`, `<Space>r…`,
`<Space>c…`, `<Space>o`, …) requires the user to type an index notation
(`3`, `1-2,5`, `a`) in response to the prompt for the `idx` field
(`input_handler/input_engine.py::input_idx_factory`). Two friction points:

1. **No visual cursor.** The user has to read the index column and mentally
   map it back to the row they want, even though the dashboard is a list.
2. **Selecting a non-contiguous set is awkward.** `1,3,5,7` is fine but slow,
   and there is no way to "build up" a selection visually before committing.

`Arrow` keys are already detected by the key reader (`utils.py::Arrow`,
returned via `NoEcho.read_key`) and dispatched to `InputHandler.handle_key`
where they currently hit a `# TODO: arrow navigation` no-op
(`input_engine.py:202`).

## Solution

Add a **cursor mode** that is entered transparently whenever an arrow key is
pressed at the `idx` input prompt. In cursor mode:

- A symbol `*` is rendered next to one row's index (the "cursor row").
- `<up>` / `<down>` move the cursor, wrapping at top/bottom.
- `<space>` toggles the cursor row's selection. Selected rows render their
  index in **bold**.
- `<enter>` commits the current selection as the `idx` field value (the same
  way typing `1,3,5<enter>` would) and the action proceeds normally.
- `<esc>` clears selection AND aborts the action (current `<esc>` semantics).
- The cursor and selection live ONLY for the duration of an `idx` prompt —
  there is no "global" selection mode outside of that.

This is purely an alternative input method for the `idx` field. It does not
touch the action layer (`app.py`), the change model (`models.py::Index`), or
any sub-action.

## Behaviour

### Entering cursor mode

The user types e.g. `<Space>` then `w` (toggle waiting). The handler is now
in input mode collecting `idx`. State:

```
sequence = [" ", "w"]
current_field = IDX_FIELD
input = ""        # empty digit buffer
cursor_row = None
selection = frozenset()
```

The first `<up>` or `<down>` press flips into cursor mode:

- `cursor_row` is initialised to `1` on `<down>` (top of list) and to the
  last row on `<up>`.
- `input` becomes `None` (we're no longer collecting digits).

Display effect:
- The dim `idx` cell of the cursor row gets a `*` prefix.
- Hint line below the table shows the new keys (`↑↓ move  <space> select
  <enter> confirm  <esc> cancel`).

### Moving and selecting

- `<up>` / `<down>` advance `cursor_row` with wrap-around. `cursor_row`
  is 1-based to match the existing index column.
- `<space>` toggles `cursor_row` in `selection`. Selected rows show their
  index number in **bold** (today the `idx` column is `dim` — bold
  cancels dim).
- A `*` symbol always marks the cursor row, even if it is not selected.
  When the cursor sits on a selected row, both effects compose
  (`* ` prefix and bold index).

### Confirming

- `<enter>` builds an `Index`:
  - If `selection` is non-empty: `Index(values=frozenset(selection))`.
  - Else (cursor used purely to navigate without `<space>`):
    `Index(values=frozenset({cursor_row}))` — single-row commit, mirrors
    the natural expectation that hovering a row and pressing `<enter>`
    selects it.
- The handler stuffs the resulting `Index` into `self.context["idx"]`
  (encoded as a notation string for compatibility with
  `parse_idx_notation`, see "Bridging" below) and proceeds with
  `_try_execute()` exactly as if the user had typed it.

### Cancelling

- `<esc>` calls the existing `self.reset()` — selection and cursor go away
  with the rest of the input state.

### Switching back to digit input

If the user types a digit while in cursor mode, that's treated as a
"start over with typed notation" intent:
- Clear `cursor_row` and `selection`.
- Set `input = key` (the digit) — re-enter digit-collection mode.

This avoids dead-end states where the user can't recover without `<esc>`.

### Constraints

- Cursor mode is **only** active while the `idx` field is being collected
  AND the change list is non-empty. Pressing arrows at any other time is a
  no-op (matches current behaviour).
- For sub-actions whose `idx` is single-only (e.g. `comment_edit_last` —
  see `_prefill_for_field` in `input_engine.py:256`), confirming with a
  multi-row selection should fail the existing single-only validation
  cleanly. No new validation needed: `Index.single()` already exists and is
  checked in the action handler.

## Code changes

### `input_handler/input_engine.py::InputHandler`

Add three fields to `__init__`:

```python
self.cursor_row: int | None = None
self.selection: frozenset[int] = frozenset()
```

Replace the `# TODO: arrow navigation` block in `handle_key`:

```python
if isinstance(key, Arrow):
    self._handle_arrow(key)
    return
```

Add `_handle_arrow`:

```python
def _handle_arrow(self, arrow: Arrow) -> None:
    if self.current_field is None or self.current_field.name != "idx":
        return
    n = self.app_context.changes.count()
    if n == 0:
        return

    if arrow is Arrow.DOWN:
        self.cursor_row = 1 if self.cursor_row is None else (self.cursor_row % n) + 1
    elif arrow is Arrow.UP:
        self.cursor_row = n if self.cursor_row is None else ((self.cursor_row - 2) % n) + 1
    else:
        return  # left/right reserved

    # Drop digit buffer once we enter cursor mode.
    self.input = None
    # Reflect cursor as the "current" provisional index for highlight purposes.
    self.current_index = Index(frozenset({self.cursor_row}) | self.selection)
```

Extend `_handle_input` to handle `<space>` and `<enter>` while in cursor
mode (i.e. when `self.cursor_row is not None`):

```python
if self.cursor_row is not None:
    if key == " ":
        if self.cursor_row in self.selection:
            self.selection -= {self.cursor_row}
        else:
            self.selection |= {self.cursor_row}
        self.current_index = Index(self.selection | {self.cursor_row})
        return False

    if key == "<enter>":
        committed = self.selection or frozenset({self.cursor_row})
        self.context[self.current_field.name] = ",".join(str(i) for i in sorted(committed))
        self._reset_cursor_state()
        self.input = None
        self.current_field = None
        return True

    if key.isdigit():
        # Switch back to digit notation — drop cursor state, fall through to digit handling.
        self._reset_cursor_state()
        # let normal digit handling pick this up below
```

Add `_reset_cursor_state`:

```python
def _reset_cursor_state(self) -> None:
    self.cursor_row = None
    self.selection = frozenset()
```

Hook `reset()` to call it. Hook `selected_rows()` so that in cursor mode it
returns `self.selection | ({self.cursor_row} if self.cursor_row else frozenset())` —
this is what the table uses to render highlights.

### Bridging cursor selection to `Index`

The action layer expects `ctx["idx"]` to be a notation string parsable by
`parse_idx_notation`. We encode the selection as a comma-separated list of
sorted integers (`"1,3,5"`) — `parse_idx_notation` already handles that
verbatim. No changes to action handlers, no changes to `models.Index`, no
changes to `app.py`.

### `display.py::build_table`

Two new visual hooks. `build_table` already accepts `selected_rows`
(`display.py:64`); extend with a `cursor_row` parameter:

```python
def build_table(
    changes, config, status_msg="", ssh_requests=0, hints="",
    selected_rows: frozenset[int] | None = None,
    cursor_row: int | None = None,
) -> Table:
    ...
```

In the row loop:

- If `idx == cursor_row`: prefix the rendered index cell with `"* "`
  (otherwise `"  "` to keep column width stable). Width budget: bump the
  `idx` column from `width=2` to `width=4` to fit `"* NN"`.
- If `idx in selected_rows`: render the index cell with `style="bold"`
  (overriding the default `"dim"`). Today only `subject` and `project`
  pick up an `underline` style for selected rows (`display.py:150-152`) —
  keep that, and additionally bold the index.

### `app.py::App.build`

Pass the cursor through:

```python
table = build_table(
    self.changes, self.config, self.status_msg, gerrit.ssh_request_count,
    self.input.hints(),
    self.input.selected_rows(),
    self.input.cursor_row,
)
```

Expose `cursor_row` as a property or plain attribute on `InputHandler`
(it already is, after the changes above).

### Hints

`InputHandler.hints()` already returns context-sensitive hints. Extend it so
that when `current_field.name == "idx"` and `cursor_row is not None`, the
hint line is:

```
↑↓ move  <space> select  <enter> confirm  <esc> cancel
```

Otherwise the existing hint line for the current sequence is shown.

When `current_field.name == "idx"` and `cursor_row is None` (i.e. we're
collecting digits), append a small affordance hint:

```
…  ↑↓ to navigate
```

so the user discovers cursor mode.

## Edge cases

### Empty list

`changes.count() == 0`. Arrow keys are ignored, hint affordance is
suppressed. Existing behaviour around `idx` collection on an empty list
already produces a "no changes" status downstream — unchanged.

### List shrinks while cursor mode is active

The list is mutated only by user actions, all of which require `<enter>` to
fire. Once `<enter>` is pressed cursor mode ends, so by the time `_changes`
shrinks, `cursor_row` is already cleared. No clamping needed inside cursor
mode itself. (The background SSH refresh modifies fields on existing
`TrackedChange` entries but does not add/remove items.)

External `changes.json` edit triggers `reload_config`, which is gated by
the main loop tick. We can defensively call `_reset_cursor_state()` at the
top of `reload_config` to avoid an out-of-range `cursor_row` after an
external edit shrinks the list.

### Wildcard sub-actions (`x` and `xa`)

`handle_deletion` accepts wildcard via `input_idx_factory({"x", "a"})`.
The `a` special-char path bypasses notation parsing entirely — cursor mode
does not interfere because `a` is consumed at the special-char check
*before* the cursor-mode branch is reached. Pressing `a` as a single-key
shortcut still works.

### Selection includes cursor at confirm

`committed = self.selection or frozenset({self.cursor_row})`. If the user
toggled the cursor row on with `<space>`, the cursor row is already in
`selection` and the `or` keeps the same set. If the user moved without
toggling, the cursor row alone is committed. No double-add risk.

### Single-only sub-actions (e.g. `comment edit last`)

`_prefill_for_field` checks `idx.single()` and bails with a red status if
not. Selecting multiple rows + confirming + a single-only sub-action will
print the existing "Invalid idx" message — same as today's behaviour for
`1,3<enter>`.

### Refresh tick during cursor mode

The background refresh runs concurrently. The cursor and selection are
attributes on `InputHandler`, never touched by SSH/refresh code paths.
Visual updates redraw the table with the latest cursor/selection — no
flicker, since cursor state is stable across redraws.

## Files changed

| File                              | Change                                              |
|-----------------------------------|-----------------------------------------------------|
| `input_handler/input_engine.py`   | Replace TODO with arrow handling; add cursor/selection state; bridge to notation on `<enter>`; extend hints. |
| `display.py`                      | Add `cursor_row` param to `build_table`; render `*` prefix and bold-on-selected for the `idx` cell. |
| `app.py`                          | Pass `cursor_row` from `InputHandler` to `build_table` in `App.build`; reset cursor state on reload. |
| `models.py`                       | No change — `Index` already supports arbitrary `frozenset[int]`. |

## Acceptance Criteria

- At any `idx` prompt, pressing `<down>` shows `*` on row 1; `<up>` from
  fresh state shows `*` on the last row.
- `<up>` from row 1 wraps to the last row; `<down>` from the last row
  wraps to row 1.
- `<space>` on the cursor row marks it selected (bold index). Pressing
  `<space>` again unselects it.
- `<enter>` with one or more selected rows commits as if the user had
  typed the equivalent comma notation, and the active action proceeds
  (status messages, refresh trigger, etc., unchanged).
- `<enter>` with no selection but a moved cursor commits the cursor row
  alone.
- `<esc>` at any point cancels the action and clears cursor/selection.
- Typing a digit in cursor mode discards cursor state and starts a fresh
  digit-notation buffer with that digit.
- Cursor mode does not appear outside an `idx` prompt — arrows pressed at
  the bare top-level keymap are a no-op.
- Existing notation typing (`1-3,5`) keeps working unchanged.
- A single-row commit through cursor mode satisfies single-only
  sub-actions (`comment edit last`); a multi-row commit cleanly fails them
  with the existing red status message.

## Out of Scope

- Persistent selection across multiple actions (a "build a working set,
  apply many ops" mode). FEATURES.md explicitly says *"changes should
  never be selected outside of choosing index input"* — this spec honours
  that.
- Mouse support.
- `<left>` / `<right>` arrows. Reserved for future feature (e.g. paging,
  comment column scrolling) — currently no-op.
- Vim-style `j` / `k` aliases. Could be added later if requested.
- Visual scroll: assumes the entire list fits on screen, same assumption
  as the current dashboard.

## Open Questions

1. **Bold vs underline for selected.** Today selected rows get
   `underline` on `subject` / `project` (`display.py:150-152`). FEATURES.md
   says "**bolding the index number**". Plan: add bold on the index cell,
   keep the existing underline on subject/project so the row visibly
   "lights up" rather than only the index changing.
2. **Discoverability of cursor mode.** Should the hint line always show
   `↑↓ to navigate` when collecting `idx`, or only after first arrow
   press? Initial take: always — cheap to render, helps first-time users.
3. **`Page Up` / `Page Down` / `Home` / `End`.** Not in the FEATURES.md
   ask. Defer.
