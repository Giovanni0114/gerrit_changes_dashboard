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
python3 gerrit_changes_dashboard.py /path/to/custom/config.toml
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

## MCP server (in development)

The dashboard can optionally expose a [Model Context
Protocol](https://modelcontextprotocol.io/) HTTP server, allowing AI assistants
to query change status and perform actions remotely:

```bash
python3 gerrit_changes_dashboard.py --mcp
```

> [!WARNING]
> Only 2 tools are implemented (`get_changes` and `quit`).
> The full planned API surface includes 16+ tools for reading, adding, editing,
> and deleting changes. See `mcp/README.md` and `mcp/tools.json` for details.
>
> I'm considering dropping MCP development for CLI tool that AIs could use.

Authentication uses Bearer tokens from `.authorized_tokens` (one token per
line, currently not wired). This feature is under active development and the
API may change significantly.

## Terminal notes

Clickable links use OSC 8 hyperlink sequences. If running inside **tmux**, add
this to your `~/.tmux.conf`:

```
set -ga terminal-features ",*:hyperlinks"
```
