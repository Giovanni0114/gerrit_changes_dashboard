# Gerrit Approvals Dashboard

Are you tired with checking over several gerrit changes waiting for CI or
coworkers to approve your changes?

Terminal dashboard for monitoring Gerrit code review approvals, built with
[Rich](https://github.com/Textualize/rich).

## Features

- Live-updating table with configurable refresh interval
- Color-coded approval values (+2 green, +1 light green, 0 dim, -1 yellow, -2 red)
- Clickable Gerrit change numbers (OSC 8 terminal hyperlinks)
- Config-file driven

## Requirements

```
pip install rich
```

## Usage

Reads changes from a JSON file and auto-reloads when the file is modified:

```bash
python gerrit_approvals.py <config file default: approvals.json>
```

Generate an example config:

```bash
python gerrit_approvals.py --init
```

Default config path is `approvals.json`.


## Config file format

```json
{
  "$schema": "./approvals.schema.json",
  "default_host": "gerrit.example.com",
  "default_port": 29418,
  "interval": 30,
  "changes": [
    {
      "hash": "abc123def456"
    },
    {
      "host": "other-gerrit.example.com",
      "hash": "789abc012def",
      "port": 22
    }
  ]
}
```

| Field | Required | Description | Default |
|-------|----------|-------------|---------|
| `interval` | No | Refresh interval in seconds | `30` |
| `default_host` | No | Fallback SSH host for changes that don't specify one | -- |
| `default_port` | No | Fallback SSH port for changes that don't specify one | -- |
| `changes` | Yes | Array of changes to track | -- |
| `changes[].hash` | Yes | Git commit hash or change-id | -- |
| `changes[].host` | No* | Gerrit SSH host (*required if `default_host` is not set) | `default_host` |
| `changes[].port` | No | SSH port, overrides `default_port` | `default_port` |
| `changes[].waiting` | No | Dim the row until approvals change, then auto-clear | `false` |
| `changes[].disabled` | No | Skip SSH queries for this change (still shown) | `false` |

A JSON schema is provided in `approvals.schema.json`.

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `r` | Force refresh |
| `q` | Quit |
| `Space` | Open change menu |
| `Space` + `a` | Add a change (prompts for hash and host) |
| `Space` + `w` + `<n>` | Toggle waiting for change #n (`a` = all) |
| `Space` + `d` + `<n>` | Toggle disabled for change #n (`a` = all) |
| `Space` + `x` + `<n>` | Toggle deletion for change #n (`a` = delete all submitted, `x` = purge, `r` = restore all) |
| `Space` + `o` + `<n>` | Open change #n in browser |
| `Space` + `s` + `<n>` | Set Automerge +1 on change #n |

## How it works

The dashboard queries Gerrit via SSH:

```bash
ssh [-p <port>] <host> gerrit query --format=json --all-approvals <hash>
```
## MCP server (under development)

The dashboard can optionally expose a [Model Context Protocol](https://modelcontextprotocol.io/) HTTP server, allowing AI assistants to query change status and perform actions remotely:

```bash
python gerrit_approvals.py --mcp
```

Authentication uses Bearer tokens stored in `.authorized_tokens` (one token per line). This feature is still under active development and the API may change.

## Terminal notes

Clickable links use OSC 8 hyperlink sequences. If running inside **tmux**, add
this to your `~/.tmux.conf`:

```
set -ga terminal-features ",*:hyperlinks"
```
