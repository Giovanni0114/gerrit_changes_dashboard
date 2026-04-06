# Features

Here I will add ideas for new features.

Standalone features use numeric ids like `001`, `002` and have a spec under
`spec/features/001-name/`.

EPICs group related features under a shared goal. An EPIC gets an id like
`EPIC001` and its spec folder is `spec/features/EPIC001-name/`. Features inside
the EPIC are numbered `EPIC001-001`, `EPIC001-002`, etc. and live as subfolders
inside the EPIC folder.

---

## 001 | Split config and changes storage

The single `approvals.json` mixes app configuration with the tracked changes list.
I want a separate config file (TOML format) for settings like interval, hosts, and
default options, and a separate JSON file just for the changes.

## 002 | Automatically pull all unmerged changes owned by the user

If we have an owner email we can query Gerrit for all open changes and add them
automatically instead of adding hashes one by one.

```bash
ssh -p 29418 giovanni@localhost gerrit query --format json owner:$EMAIL is:open
```

The email should default to `git config user.email` but also be configurable in
the config file.

## 003 | Gerrit server instances in config

Right now host, port and email are either global or set per change. I want a named
instances section in the config where each instance defines a Gerrit server:
- host (required)
- port
- email

The first defined instance is the default. When adding a change interactively, a
numbered list of instances is shown and the user picks one.

## 004 | Move input field above the table

The input field used for operations is currently rendered inside the table.
It should move above the table but below the header.

## 005 | Add `comments` field for change

Users should be able to attach short notes to individual changes. Comments are
persisted in the changes file and displayed in the table.

Keybindings:
- `<Space>` + c + `<idx>` + a — add comment
- `<Space>` + c + `<idx>` + A — remove all and add one
- `<Space>` + c + `<idx>` + e — edit last comment (pre-filled in input)
- `<Space>` + c + `<idx>` + d + `<idx>` — delete comment by index
- `<Space>` + c + `<idx>` + d + a — delete all comments

For now cursor movement inside the input is not required — only appending and
backspace deletion.

## 006 | Track latest patchset hash per change

Changes are added by commit hash, but when a new patchset is uploaded the hash
changes. This causes a mismatch warning and means operations like `gerrit review`
run against a stale hash.

Currently the app prints:
```
Warning: latest patchset mismatch for ...
```

Instead of showing this warning, the app should silently store the latest patchset
hash in memory and use it for all SSH operations. The original hash in the config
file stays unchanged — it is the user's reference point, not the live hash.

This also raises a deeper question: maybe the change number (not the commit hash)
should be the primary identifier, with the commit hash used only for the actual
review operations. That would make the tracking more resilient to patchset
updates. This is a prerequisite for EPIC001, since all review operations need to
target the correct patchset.

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

## EPIC002 | Expose MCP interface to all major operations

The MCP server currently has limited coverage. This EPIC extends it to cover
comments (feature 005) and all review operations (EPIC001) so AI assistants can
perform the same actions available in the TUI.

More sub-features will be defined once EPIC001 and feature 005 are complete.
No point speccing this in detail before those land.

### EPIC002-001 | Expose comment operations over MCP
### EPIC002-002 | Expose review operations over MCP
