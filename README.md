# Gerrit Changes Dashboard

Are you tired with checking over several gerrit changes waiting for CI or
coworkers to approve your changes?

Terminal dashboard for monitoring Gerrit code review approvals, built with
[Rich](https://github.com/Textualize/rich).

## Features

- Live-updating table with configurable refresh interval
- Color-coded approval values (+2 green, +1 light green, 0 dim, -1 yellow, -2 red)
- Clickable Gerrit change numbers (OSC 8 terminal hyperlinks)

## Requirements

Python 3.12+ with dependencies managed by `uv`:

```bash
uv sync
```

This installs:
- **rich** — Terminal rendering and UI
- **pytest** (dev) — Testing

## Usage

Generate an example config:

```bash
python3 gerrit_changes_dashboard.py --init
```

This creates `config.toml` with example settings. Edit it to configure your Gerrit instances, email, and other preferences.

Then run the dashboard:

```bash
python3 gerrit_changes_dashboard.py
```

Or specify a custom config file:

```bash
python3 gerrit_changes_dashboard.py --config /path/to/custom/config.toml
```

### CLI board

Print every change currently tracked by the TUI using only local `cache.json`
data:

```bash
uv run gcd board
```

The default command makes no Gerrit or SSH requests. Refresh tracked changes and
save successful results back to the cache explicitly:

```bash
uv run gcd board --reload
```

Use `--json` with either mode for normalized machine-readable output:

```bash
uv run gcd board --json
uv run gcd board --reload --json
```

## Keyboard shortcuts

### Main Screen

| Key | Action |
|-----|--------|
| `r` | Refresh all changes from Gerrit |
| `q` | Quit application |
| `f` | Fetch all open changes you own from Gerrit and add them to tracking |
| `Space` | Open change management menu |
| `e` | Open editor submenu |


### Space + [Key] - Change Management

| Keybind                 | Action                                    |
| ---------               | --------                                  |
| `Space` + `a`           | Add a new change by number + instance         |
| `Space` + `w` + `<idx>` | Toggle waiting status                     |
| `Space` + `d` + `<idx>` | Toggle disabled status                    |
| `Space` + `x` + `<idx>` | Toggle deletion or manage deleted changes |
| `Space` + `o` + `<idx>` | Open change in web browser                |
| `Space` + `s` + `<idx>` | Set Automerge +1 on change                |
| `Space` + `c` + `<idx>` | Manage comments on change                 |


### e + [Key] - Editor Submenu

| Keybind | Action |
|---------|--------|
| `e` + `c` | Open TOML config file in external editor |
| `e` + `a` | Open JSON changes file in external editor (auto-reloads on save) |

### Index Notation

Most change management commands accept flexible index notation:

- **Single**: `3` — change at index 3
- **Multiple**: `1,3,5` — changes at indices 1, 3, 5
- **Range**: `1-5` — changes 1 through 5 (inclusive)
- **Combined**: `1-2,5,7-9` — mix ranges and singles
- **All**: `a` — apply to all changes (valid for `w`, `d`, `x`, `c` commands)

Whitespace is ignored in index notation (e.g., `1-3, 5, 7-9` is valid).

### Navigation & Input

| Key | Action |
|-----|--------|
| `Enter` | Confirm input and proceed |
| `ESC` | Cancel current action and return to main screen |
| `Backspace` | Delete last character in input field |


## How it works

The dashboard manages tracked Gerrit changes via SSH queries and stores them persistently:

```bash
# For each tracked change:
ssh [-p <port>] <host> gerrit query --format=json --all-approvals <number>
```

## Terminal notes

Clickable links use OSC 8 hyperlink sequences. If running inside **tmux**, add
this to your `~/.tmux.conf`:

```
set -ga terminal-features ",*:hyperlinks"
```
