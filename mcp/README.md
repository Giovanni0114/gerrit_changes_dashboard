# Gerrit Changes MCP Tools

## Implementation Status

> [!IMPORTANT]
> The MCP server is in early development. Only **2 tools** are currently implemented:
> `get_changes` and `quit`. The remaining tools below describe the **planned** API surface
> (tracked in EPIC002). Planned tools are marked with "(planned)" in the summary table.
>
> Additionally:
> - **Authentication middleware** (`AuthMiddleware`) is defined but not yet wired into the
>   FastMCP server.
> - **Response envelope** (`ok`, `api_version`, error objects) is not yet implemented —
>   tools return raw result dicts directly.
> - **API versioning** (v1 route prefix) is not yet enforced.

## API Version

This MCP metadata and the server are versioned. Target API version: "v1".
All RPC routes and responses will include the API version once implemented. Example route prefix:

> `/mcp/v1/rpc/<tool_name>`

## Overview

This directory contains metadata and a description for the MCP (Model Control Plane)
tools exposed by the Gerrit Changes Dashboard application. The background MCP server
is started by the application (with `--mcp` flag) and exposes a small set of tools (RPCs)
that let an authorized client (for example an LLM acting through the MCP) inspect and
manage the set of tracked Gerrit changes.

Changes are managed through the `Changes` class (`changes.py`) which persists to a JSON
changes file (`changes.json`). The JSON file is **not intended for manual editing** — all
mutations happen through the TUI or MCP tools and are persisted automatically via
`Changes.save_changes()`.

## Authentication (planned)

All MCP tool calls will be protected by a Bearer token. The server expects an HTTP
Authorization header with a value of the form:

  `Authorization: Bearer <token>`

Valid tokens come from the application's runtime configuration (see `utils.authorized_tokens()`).

> **Note:** The `AuthMiddleware` class exists in `mcp_background.py` but is not yet passed
> to the `FastMCP` constructor. Authentication is currently not enforced.

## Identification rules

- Changes are identified by `number` (Gerrit change number) + `instance`.
- In the MCP response payload, the field `hash` contains the current patchset revision
  (maps to `TrackedChange.current_revision`). This value may be `null` if the change
  has not been queried from Gerrit yet.
- For single-change operations (planned), both `number` and `instance` MUST be provided.

## Response envelope (planned)

Tool responses will follow a consistent envelope. Example successful response:

```json
  {
    "ok": true,
    "api_version": "v1",
    "result": { "..." }
  }
```

Errors will follow the same envelope with an error object:

```json
  {
    "ok": false,
    "api_version": "v1",
    "error": { "code": "NotFound", "message": "..." }
  }
```

> **Note:** Currently implemented tools return raw result dicts without the envelope.

## Tools / Discovery (planned)

The MCP will expose a discovery tool `mcp_info` which enumerates available tools,
their short descriptions and output schemas. Clients SHOULD use `mcp_info` to
discover tools and validate schemas prior to making automated calls.

## Default tool

`get_changes` is the default function and intentionally returns only active changes
(not deleted and not disabled). Use `get_all_changes` (planned) to obtain everything,
including disabled/deleted entries.

## Naming conventions

All tool names use lower_snake_case (e.g. `get_changes`, `set_waiting`). Keep names
short and verb-first when appropriate.

## Fields and predictability

Change objects always include the same set of fields for predictability. If a
field has no value it will be present with an explicit `null` value (for example
`url: null`). This simplifies client parsing and schema validation.

## Tools (summary)

Below is a summary of all tools (implemented and planned). For exact JSON output
schemas see `mcp/tools.json`.

### Implemented

- **get_changes**
  - Return active tracked changes (filters out deleted and disabled entries).
  - Output: `{ changes: list[MCPChange] }`

- **quit**
  - Ask the running application to quit (it will persist pending config removals).
  - Output: `{ message: string }`

### Planned (EPIC002)

- get_all_changes
  - Return all tracked changes, including disabled and deleted.
  - Output: `{ api_version: string, changes: list[MCPChange] }`

- get_change
  - Return a single change identified by number+instance (both required).
  - Output: `{ api_version: string, change: MCPChange }`

- add_change
  - Add a change to the tracked list and persist to the changes file.
  - Input: `{ number: integer, instance: string }`
  - Output: `{ api_version: string, added: MCPChange, mtime: number }`

- set_waiting
  - Set or clear the `waiting` flag for a change. Supply an explicit boolean to
    set state; omitting the value may be treated as a toggle by the implementation.
  - Output: `{ api_version: string, change: MCPChange, previous: boolean, current: boolean }`

- set_disabled
  - Enable/disable a change (persisted to changes file). Same semantics as set_waiting.
  - Output: `{ api_version: string, change: MCPChange, previous: boolean, current: boolean }`

- soft_delete_change
  - Mark a change as deleted in-memory. A subsequent `purge_deleted` is required
    to permanently remove the entry from the changes file.
  - Output: `{ api_version: string, change: MCPChange }`

- purge_deleted
  - Permanently remove all changes marked deleted from the changes file.
  - Output: `{ api_version: string, removed_count: number }`

- delete_change
  - Permanently remove a single change (requires number+instance). Implementations may
    internally mark+purge to reuse existing code paths.
  - Output: `{ api_version: string, removed: true, number: integer }`

- restore_change / restore_all
  - Undo the deleted flag for a single change or for all changes.
  - Output: `{ api_version: string, restored: boolean }` or `{ api_version: string, restored_count: number }`

- refresh_all
  - Trigger a manual refresh of SSH queries (subject to the app's manual refresh limits).
  - Output: `{ api_version: string, queued: boolean, message?: string }`

- set_automerge
  - Request Gerrit to set automerge (+1) for a change (number+instance required).
  - Output: `{ api_version: string, message: string }`

- open_change_webui
  - Ask the application to open the change URL in its environment (used by the TUI).
  - Output: `{ api_version: string, opened: boolean, url?: string }`

- add_comment / edit_comment / delete_comment (EPIC002-001)
  - Comment operations on tracked changes.
  - Not yet specified in detail.

## MCPChange object

All tool outputs that include Change objects use this shape and always include all
fields (nullable fields will be present with explicit null values):

- instance: `string`
- hash: `string | null` — current patchset revision (`TrackedChange.current_revision`)
- number: `integer`
- waiting: `boolean`
- disabled: `boolean`
- deleted: `boolean`
- submitted: `boolean`
- subject: `string | null`
- project: `string | null`
- url: `string | null`
- approvals: `list[object]` — each: `{ type: string, value: string, by: string }`

## How to use

Examples below are conceptual. FastMCP exposes RPC endpoints at a versioned path.

### Example: get_changes (implemented)

```
  POST /mcp/v1/rpc/get_changes

  Body: {}

  Current response (no envelope):

  {
    "changes": [
      {
        "instance": "default",
        "hash": "abc123...",
        "number": 12345,
        "waiting": false,
        "disabled": false,
        "deleted": false,
        "submitted": false,
        "subject": "Fix foobar",
        "project": "my-project",
        "url": "https://gerrit.example.com/c/12345",
        "approvals": [
          { "type": "Code-Review", "value": "+2", "by": "reviewer@example.com" }
        ]
      }
    ]
  }
```

### Example: add_change (planned)

```
  POST /mcp/v1/rpc/add_change
  Authorization: Bearer <token>

  Body: { "number": 12345, "instance": "default" }

  Response envelope (planned):

  {
    "ok": true,
    "api_version": "v1",
    "result": { "added": { ... }, "mtime": 1610000000.0 }
  }
```

## Rate limiting & safety

The MCP server may enforce rate limits and other operational safeguards. Clients
should expect the server to return standard limit headers (for example
`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`) and honor them.
Destructive operations (purge, delete, set_automerge) require appropriate authorization
and should be used with care.

See `mcp/tools.json` for exact, machine-readable tool definitions and output schemas.
