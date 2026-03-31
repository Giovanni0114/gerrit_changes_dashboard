# Gerrit Approvals MCP Tools

## API Version

This MCP metadata and the server are versioned. Current API version: "v1".
All RPC routes and responses include the API version. Example route prefix:

> `/mcp/v1/rpc/<tool_name>`

## Overview

This directory contains metadata and a description for the MCP (Model Control Plane)
tools exposed by the Gerrit Approvals Dashboard application. The background MCP server
is started by the application and exposes a small set of tools (RPCs) that let an
authorized client (for example an LLM acting through the MCP) inspect and manage the
set of tracked Gerrit changes.

## Authentication

All MCP tool calls are protected by a Bearer token. The server expects an HTTP
Authorization header with a value of the form:

  `Authorization: Bearer <token>`

Valid tokens come from the application's runtime configuration (see utils.authorized_tokens()).

## Identification rules

- Identification for single-change operations: host and hash MUST be provided.
  The API does not support row/index-based identification. Using host+hash is
  unambiguous and stable across concurrent modifications.
- If a call omits host or hash, the server returns a BadRequest-style error.

## Response envelope and API version

Tool responses follow a consistent envelope. Example successful response:

```json
  {
    "ok": true,
    "api_version": "v1",
    "result": { "..." }
  }
```

Errors follow the same envelope with an error object:

```json
  {
    "ok": false,
    "api_version": "v1",
    "error": { "code": "NotFound", "message": "..." }
  }
```

## Tools / Discovery

The MCP exposes a discovery tool `mcp_info` which enumerates available tools,
their short descriptions and output schemas. Clients SHOULD use `mcp_info` to
discover tools and validate schemas prior to making automated calls. The project
may also support OpenAPI/Swagger export in future versions; the discovery endpoint
is the canonical machine-readable source today.

## Default tool

`get_changes` is the default function and intentionally returns only active changes
(not deleted and not disabled). Use `get_all_changes` to obtain everything,
including disabled/deleted entries.

## Naming conventions

All tool names use lower_snake_case (e.g. `get_changes`, `set_waiting`). Keep names
short and verb-first when appropriate.

## Fields and predictability

Change objects always include the same set of fields for predictability. If a
field has no value it will be present with an explicit `null` value (for example
`url: null`). This simplifies client parsing and schema validation.

## Tools (short summary)

Below is a short summary of the supported tools. For exact JSON output schemas
see `mcp/tools.json`.

- get_changes (default)
  - Return active tracked changes (filters out deleted and disabled entries).
  - Output: `{ api_version: string, changes: list[MCPChange], count: number }`

- get_all_changes
  - Return all tracked changes, including disabled and deleted.
  - Output: `{ api_version: string, changes: list[MCPChange] }`

- get_change
  - Return a single change identified by host+hash (both required).
  - Output: `{ api_version: string, change: MCPChange }`

- add_change
  - Add a change to the tracked list and persist to the config file.
  - Output: `{ api_version: string, added: MCPChange, mtime: number }`

- set_waiting
  - Set or clear the `waiting` flag for a change. Supply an explicit boolean to
    set state; omitting the value may be treated as a toggle by the implementation.
  - Output: `{ api_version: string, change: MCPChange, previous: boolean, current: boolean }`

- set_disabled
  - Enable/disable a change (persisted to config). Same semantics as set_waiting.
  - Output: `{ api_version: string, change: MCPChange, previous: boolean, current: boolean }`

- soft_delete_change
  - Mark a change as deleted in-memory. A subsequent `purge_deleted` is required
    to permanently remove the entry from the config file.
  - Output: `{ api_version: string, change: MCPChange }`

- purge_deleted
  - Permanently remove all changes marked deleted from the config file.
  - Output: `{ api_version: string, removed_count: number }`

- delete_change
  - Permanently remove a single change (requires host+hash). Implementations may
    internally mark+purge to reuse existing code paths.
  - Output: `{ api_version: string, removed: true, hash: string }`

- restore_change / restore_all
  - Undo the deleted flag for a single change or for all changes.
  - Output: `{ api_version: string, restored: boolean }` or `{ api_version: string, restored_count: number }`

- refresh_all
  - Trigger a manual refresh of SSH queries (subject to the app's manual refresh limits).
  - Output: `{ api_version: string, queued: boolean, message?: string }`

- set_automerge
  - Request Gerrit to set automerge (+1) for a change (host+hash required).
  - Output: `{ api_version: string, message: string }`

- open_change_webui
  - Ask the application to open the change URL in its environment (used by the TUI).
  - Output: `{ api_version: string, opened: boolean, url?: string }`

- quit
  - Ask the running application to quit (it will persist pending config removals).
  - Output: `{ api_version: string, message: string }`

MCPChange object
-------------

All tool outputs that include Change objects use this shape and always include all
fields (nullable fields will be present with explicit null values):

- host: `string`
- hash: `string`
- waiting: `boolean`
- disabled: `boolean`
- deleted: `boolean`
- submitted: `boolean`
- subject: `string | null`
- number: `integer | null`
- project: `string | null`
- url: `string | null`
- approvals: `list[tuple[string, integer]]`

How to use
----------

Examples below are conceptual. FastMCP exposes RPC endpoints at a versioned path.
Always include a valid Authorization Bearer token.

### Example: get_changes

```
  POST /mcp/v1/rpc/get_changes
  Authorization: Bearer <token>

  Body: {}

  Response envelope:

  {
    "ok": true,
    "api_version": "v1",
    "result": { "changes": [...], "count": 3 }
  }
```

### Example: add_change

```
  POST /mcp/v1/rpc/add_change Authorization: Bearer <token>

  Body: { "hash": "abcdef123", "host": "gerrit.example.com" }

  Response envelope:

  {
    "ok": true,
    "api_version": "v1",
    "result": { "added": { ... }, "mtime": 1610000000.0 }
  }
```

Rate limiting & safety
----------------------

The MCP server may enforce rate limits and other operational safeguards. Clients
should expect the server to return standard limit headers (for example
`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`) and honor them.
Destructive operations (purge, delete, set_automerge) require appropriate authorization
and should be used with care.

See `mcp/tools.json` for exact, machine-readable tool definitions and output schemas.
