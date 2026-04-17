# Features 

Here I will add ideas for new features.

Standalone features use numeric ids like `001`, `002` and have a spec under
`spec/features/001-name/`.

EPICs group related features under a shared goal. An EPIC gets an id like
`EPIC001` and its spec folder is `spec/features/EPIC001-name/`. Features inside
the EPIC are numbered `EPIC001-001`, `EPIC001-002`, etc. and live as subfolders
inside the EPIC folder.

---

## EPIC001 | Review operations on a change

The `gerrit review` command supports a wide range of operations beyond setting
labels: abandon, rebase, restore, submit, code-review score, custom messages, etc.

Right now only `set automerge` is exposed. This EPIC adds a dedicated `Review`
submenu (`<Space>` + `r`) covering the most useful operations. Feature 006 is a
prerequisite — review commands must target the latest patchset, not the hash
stored in config.

Note: `<Space>` + `r` is currently unbound (bare `r` without Space does refresh),
so there is no keybind conflict.

### EPIC001-001 | Add `Review` submenu to keybinds

Add `<Space>` + `r` as the entry point for a new Review submenu, following the
same input-handler pattern as the existing leader actions.

### EPIC001-002 | Abandon a change

Add `<Space>` + `r` + `<idx>` + `abandon` to run `gerrit review --abandon`.
Should ask for confirmation before executing.

### EPIC001-003 | Rebase a change

Add `<Space>` + `r` + `<idx>` + `rebase` to run `gerrit review --rebase`.

### EPIC001-004 | Restore an abandoned change

Add `<Space>` + `r` + `<idx>` + `restore` to run `gerrit review --restore`.

### EPIC001-005 | Set Code-Review score

Add `<Space>` + `r` + `<idx>` + `cr` to run `gerrit review --code-review N`.
Prompts for a value from -2 to +2. Should display the meaning of each value
during the prompt.

### EPIC001-006 | Submit a change

Add `<Space>` + `r` + `<idx>` + `submit` to run `gerrit review --submit`.
Must ask for confirmation before executing since this is irreversible.

### EPIC001-007 | Move `set automerge` into the Review submenu

The current `<Space>` + `s` binding for automerge is a one-off. It should become
part of the Review submenu for consistency. The old binding can be kept as an
alias during a transition period or removed immediately — TBD.

---

## EPIC003 | Verification failure comments & analyzer system

When a change has Verified -1/-2 (typically set by Jenkins/CI), the dashboard
shows a red row but provides no clue about *why* it failed. The user must open
the Gerrit web UI to read through reviewer comments. This EPIC fetches those
comments via SSH (`--comments` flag) and runs a configurable analyzer to extract
actionable failure information for display directly on the dashboard.

Comment format varies across Gerrit organisations, instances and projects. The
analyzer uses a `Protocol` interface so different strategies can be plugged in.
This EPIC ships a built-in `PatternAnalyzer` (regex-based). An LLM-based
analyzer is explicitly deferred to a future EPIC — the Protocol is designed with
that use case in mind but not implemented here.

### Sub-features

| ID           | Name                                    | Deps            |
|--------------|-----------------------------------------|-----------------|
| EPIC003-001  | Fetch Gerrit comments via SSH           | —               |
| EPIC003-002  | Analyzer Protocol & PatternAnalyzer     | —               |
| EPIC003-003  | Analyzer configuration in TOML          | —               |
| EPIC003-004  | Integrate analyzer into refresh cycle   | 001, 002, 003   |
| EPIC003-005  | Display analyzer report in dashboard    | 004, feature 005|
| EPIC003-006  | Expose analyzer report over CLI          | 004             |

001, 002, 003 are independent and can be implemented in parallel. 004 is the
integration point. 005 depends on feature 005 (user comments) being merged
first. 006 is a leaf task.

Full specs are in `spec/features/EPIC003-verification-comments/` but only on
`origin/epic/003-verification-comments` branch

---

## 010 | Add spinner and countdown to header

Currently header shows just time of refreshed, and this is often misleading. I
want to add some sort of rich.Spinner to indicate when operations are running
in the background. Also, current time should be replaced with countdown to next
planned refresh.

---

## 011 | Make a SPIKE for the possibility of layering interface

I would like to be able to create some sort of overlay screen, floating window,
or some similar effect to show additional information on tab click

---

## 014 | SPIKE: Move from MCP to CLI

Key findings:
- 90% of operations work standalone against `config.toml` + `changes.json`
  (the TUI auto-reloads on file changes via mtime polling)
- Existing modules (`gerrit.py`, `config.py`, `changes.py`) are already
  decoupled from the TUI and can be wired into argparse directly
- Only `quit` truly needs IPC to the running TUI (and `kill` works for that)
- A CLI with `--json` output serves both humans and AI assistants better
  than MCP (composable, debuggable, zero dependencies)
- Completing EPIC002 (14+ tools, auth, envelope) is far more work for
  less payoff
- If live in-process state is ever needed, a Unix socket extension (Option D)
  can be added later

This SPIKE supersedes EPIC002 — if CLI is built, EPIC002 becomes unnecessary.

---

## 015 | Navigation and selecting using arrows

If the arrow is used when index is expected:
  - symbol `*` appears next to the first index in list of changes
  - arrows `up` and `down` navigates this symbol on the list of chanegs, symbol
  `*` should move.
  - it should rotate, meaning when it's on the first change (on top of a list)
  and arrow `up` is pressed, it should move to the last one. (ofc also in other way)
  - when `<space>` is pressed, the change should be marked as **selected**.
  - selecting a already selected change unselects it
  - selected change should be makred with bolding the index number
  - when pressing `<enter>` all selected changes should be passed for
  operatons, as it would if selected with notation
  - pressing `<esc>` unselects all changes and abort the operaton, as normally would
  - changes should never be selected outside of chosing index input

---

## 016 | Design CLI tool

---

## 018 | Changes auto-save and internal mtime tracking

`Changes` should own its own persistence. Today `app.py` calls `save_changes()`
in 14 places and tracks `changes_mtime` externally. This feature adds:

- Internal `_mtime` tracking (remove `self.changes_mtime` from `App`)
- Dirty flag (`_dirty`) — skip writes when nothing changed
- `flush()` — replaces `save_changes()`, no-op when clean
- `has_external_changes()` — replaces mtime comparison in `reload_config()`
- `mark_dirty()` — for mutations outside context managers

Depends on 017 (cache). Full spec in `spec/features/018-changes-auto-save/spec.md`.

---

