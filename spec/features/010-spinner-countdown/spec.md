# 010 — Spinner & Refresh Countdown in Header

## Problem

The header today (`display.py::build_header`) shows only the wall-clock time of
the last refresh:

```
Gerrit Approvals  (refreshed 14:32:07)  ssh requests: 12
```

This has two practical issues:

1. **No live indicator that work is in flight.** When a manual refresh
   (`r` / `<Space>r…m` / etc.) or scheduled refresh runs, the user has no visual
   cue that SSH queries are pending. A change row may stay stale-looking for
   several seconds with no feedback that data is being fetched.
2. **"Refreshed at" is misleading as freshness signal.** What the user actually
   wants to know is *"how long until the next refresh?"*, not *"how long ago was
   the last one?"*. The latter requires mental arithmetic against
   `config.interval`.

## Solution

Replace the static header with a header that:

1. Shows a Rich spinner whenever a background refresh is running
   (`App.refresh_pending` is `True` / `App.refresh_done` is cleared).
2. Shows a countdown to the next scheduled refresh
   (`config.interval - seconds_since_refresh`, clamped to `>= 0`) instead of the
   "refreshed HH:MM:SS" timestamp. While a refresh is in flight, the countdown
   is replaced by `"refreshing…"`.

`ssh requests: N` keeps its place — it is a useful cumulative counter and
unrelated to this feature.

## Header layout (before → after)

### Before

```
              Gerrit Approvals  (refreshed 14:32:07)  ssh requests: 12
```

### After (idle, 8 s until next refresh)

```
              Gerrit Approvals  (next refresh in 8s)  ssh requests: 12
```

### After (refresh in flight)

```
              Gerrit Approvals  ⠋ refreshing…  ssh requests: 12
```

The spinner glyph cycles via Rich's built-in `Spinner` (default `"dots"` style)
on every UI tick (`config.ui_refresh_rate` Hz, already driving `Live`).

## Code changes

### `display.py::build_header`

Signature changes to receive the data it needs to render the new header:

```python
def build_header(
    ssh_requests: int,
    seconds_until_refresh: float,
    refresh_in_flight: bool,
) -> Panel:
    ...
```

- When `refresh_in_flight` is `True`, render `Spinner("dots", text="refreshing…")`
  next to the title using a `Group` or a single `Text` line — the spinner needs
  to be a `RenderableType`, not a string, so `Live`'s tick advances it.
- When `False`, render `f"next refresh in {int(max(0, seconds_until_refresh))}s"`.

The header stays a `Panel`. The centered text becomes a small renderable group
combining the title, the status fragment (spinner *or* countdown), and the
ssh-requests counter.

### `app.py::App.build`

Compute the two new arguments from existing state:

```python
seconds_until_refresh = max(0.0, self.config.interval - self.seconds_since_refresh)
refresh_in_flight = not self.refresh_done.is_set()
header = build_header(
    ssh_requests=gerrit.ssh_request_count,
    seconds_until_refresh=seconds_until_refresh,
    refresh_in_flight=refresh_in_flight,
)
```

No new state is introduced on `App` — `seconds_since_refresh` and
`refresh_done` already exist (`app.py:77-79`).

### `app.py::App.run` main loop

The countdown must update once per second visually even when nothing else
changes. Today `visual_update_if_needed()` only redraws when
`needs_visual_update` is `True`. Two options:

- **Option A (preferred):** Set `self.needs_visual_update = True` once per
  whole-second crossing in the main loop — i.e. when
  `int(prev_seconds_since_refresh) != int(self.seconds_since_refresh)`. Cheap,
  bounded to ≤ 1 redraw/second, and integrates with the existing
  `needs_visual_update` flag.
- **Option B:** Always rebuild on every tick. Wasteful at
  `ui_refresh_rate=20`.

Go with Option A. Add a small `_last_countdown_value: int` field, compare on
each tick, and flag `needs_visual_update` on transition.

The spinner does **not** require `needs_visual_update` to advance — Rich's
`Live` re-renders the same `Spinner` instance on every refresh tick by design.
The renderable just has to be present in the layout while a refresh is running.

### `models.py::AppContext`

No changes — `build_header` is called from `App.build` directly.

## Edge cases

### Refresh starts while countdown is at 0

`seconds_since_refresh >= config.interval` triggers `_start_refresh()`
(`app.py:693`). On the same tick, `seconds_since_refresh` is reset to `0.0` and
`refresh_done` is cleared. The header flips from `"next refresh in 0s"` to the
spinner without an intermediate frame showing a stale countdown.

### Manual refresh

`refresh_all()` → `_process_refresh_queue()` → `_start_refresh()` resets
`seconds_since_refresh` to `0.0`. Header switches to the spinner immediately.

### Refresh takes longer than `interval`

The spinner stays visible. `seconds_since_refresh` keeps growing past
`config.interval`, but the countdown isn't displayed (spinner replaces it).
When the refresh completes, the next-refresh countdown resumes from
whatever `seconds_since_refresh` is — it will likely be > `interval`, so the
next `interval` check fires immediately on the following tick and a fresh
refresh kicks off. This matches today's behaviour.

### `config.interval` reduced via config reload

The countdown derived value (`interval - seconds_since_refresh`) clamps at
`0`, so a shrunken interval shows `0s` until the next refresh fires.
No new behaviour needed.

### Disabled-changes one-time query at startup (`query_disabled_once`)

This runs synchronously in `run()` *before* the `Live` context is entered,
so the spinner is irrelevant for this initial query — there is no header to
update yet. No change needed.

## Visual / Rich notes

- Use Rich's `Spinner` from `rich.spinner`. Picking style: `"dots"` is the
  most terminal-portable and matches Rich examples; `"point"` and `"line"`
  are alternatives and fine — pick by taste during implementation.
- The header `Panel` keeps `expand=True` and the centered alignment used today
  (`display.py:170-172`).
- Spinner colour: leave default. Avoid `style="bold yellow"` etc. to stay
  consistent with the muted header style.

## Files changed

| File         | Change                                                      |
|--------------|-------------------------------------------------------------|
| `display.py` | Rework `build_header()` signature and body; add spinner.    |
| `app.py`     | Pass `seconds_until_refresh` / `refresh_in_flight` into `build_header`. Flag `needs_visual_update` on whole-second tick. |

## Acceptance Criteria

- Idle dashboard shows `next refresh in <N>s` in the header, decreasing once
  per second, clamped at `0s`.
- Triggering a refresh (any path: scheduled, `r`, review op, fetch) replaces
  the countdown with an animated spinner and the literal text `refreshing…`.
- The spinner glyph animates without user input — i.e. it ticks on Rich's
  refresh schedule, not only on key presses.
- When the refresh completes, the header reverts to a countdown derived from
  the (now-reset) `seconds_since_refresh`.
- `ssh requests: <N>` is still displayed in the same relative position.
- No regression in startup or the initial blocking
  `query_active_changes()` / `query_disabled_once()` calls.

## Out of Scope

- Per-change in-progress indicator (e.g. spinner inside a row while *that*
  change is being queried). The current code queries all running changes in
  one `ThreadPoolExecutor.map`, so per-change progress would require
  threading the executor state into rendering — bigger change, not worth it
  for alpha.
- Configurable spinner glyph / colour. Defaults are fine.
- Showing seconds to the next *manual* refresh allowance (the
  `manual_refresh_counter` rate-limit). Different concept, different UI.

## Open Questions

1. Should the countdown go negative (`-2s`) when a refresh overruns, or stay
   pinned at `0s`? Initial take: pinned at `0s`, since once
   `seconds_since_refresh > interval` the spinner is showing anyway.
2. Should the header also surface an error indicator (e.g. red spinner /
   icon) when the previous refresh produced widespread errors? Probably
   future work — errors are already shown in the rows themselves
   (`display.py:114-117`).
