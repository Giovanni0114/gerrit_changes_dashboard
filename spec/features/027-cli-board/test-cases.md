# 027 - Test Cases

All tests use temporary files. Default-mode tests use a communication fake that
raises if called; reload tests use controlled Gerrit responses. No terminal TUI
or real SSH connection is used.

## CLI Dispatch

### TC-001: `board` dispatches without starting the TUI

Parse `gcd board`, verify the board runner is called, and verify `App.run` is not
called.

### TC-002: `board --json` selects JSON output

Parse `gcd board --json` and verify the board runner receives `args.json=True`.

### TC-003: `board --reload` selects Gerrit refresh

Parse `gcd board --reload` and verify the board runner receives
`args.reload=True`.

### TC-004: Existing no-subcommand and query paths are unchanged

Verify no subcommand still follows the TUI path and `query` still dispatches to
the query runner.

## Default Cache-Only Mode

### TC-101: Empty tracked set succeeds silently

Given an empty `changes.json`, `run` constructs no Gerrit communication, emits no table, and
returns `0`.

### TC-102: Plain board never queries Gerrit

Given cached tracked entries and a communication fake that raises on any call,
verify `board` renders successfully without reaching the fake.

### TC-103: Every tracked state is included

Given normal, waiting, disabled, and deleted entries, verify all four are
hydrated and represented. Local flags do not filter the board.

### TC-104: Cached owner is rendered

Given a cache entry containing owner name, verify the Owner column uses it.

### TC-105: Old cache entries without owner remain readable

Load a pre-feature cache entry with no `owner` key and verify it renders `?`
without an exception or cache rewrite.

### TC-106: Missing cache remains visible and fails

Given a tracked entry with no cache entry, verify its number is shown with an
error instructing the user to run `board --reload`, no query occurs, and the
status is `1`.

### TC-107: Plain board does not modify cache

Record cache contents and mtime, run plain board, and verify neither changes.

## Reload Mode

### TC-201: Reload entries use their configured Gerrit instances

Given changes from two configured instances, verify each `query_change` call
receives the matching `GerritInstance` and tracked number.

### TC-202: Reload includes every tracked state

Given normal, waiting, disabled, and deleted entries, verify all four are
queried. Local flags do not filter reload.

### TC-203: Unknown instance skips SSH

Given an entry whose instance is absent from config, verify no Gerrit call is
made for it, an error record is produced, and the final status is `1`.

### TC-204: Queries may complete out of order without reordering results

Make fake queries complete in a different order and verify collected results
still match `changes.json` order.

### TC-205: Successful reload updates and saves cache

Given a successful Gerrit response, verify subject, project, URL, owner, and
other supported fields are persisted and available to a subsequent plain board
run. Verify cache saving occurs once after collection.

### TC-206: Failed reload retains stale cache

Given existing cached fields and a Gerrit error, verify stale fields remain in
the result and cache file, the error is reported, and status is `1`.

### TC-207: Partial reload failure does not prevent later queries

Make an early query fail and verify later tracked entries are still attempted;
successful entries are cached while the failed entry remains unchanged.

## Human Output

### TC-301: Default output uses query-style columns

Given successful Gerrit responses, verify the rendered table contains Number,
Project, Subject, and Owner and does not contain TUI-only Comments or Approvals
columns.

### TC-302: Tables group by instance in first-appearance order

Given interleaved tracked instances, verify one table is rendered for each
instance, tables follow first appearance, and rows preserve relative file order.

### TC-303: Number remains clickable

Given a response with a URL, verify the Number cell carries the Rich hyperlink.

### TC-304: Reload failure remains visible with stale fields

Given cached fields followed by a `{"error": "connection failed"}` reload,
verify the tracked number and stale details have a row, the error is printed to
stderr with instance context, and `run` returns `1`.

## JSON Output

### TC-401: JSON is a flat ordered array

Run with `--json` for interleaved instances and verify the decoded array exactly
follows `changes.json` order.

### TC-402: Cached JSON adds instance

Verify a plain JSON run contains cached fields and the source instance without a
Gerrit call.

### TC-403: Reload JSON uses the same normalized schema

Compare plain cached JSON with JSON after a successful reload and verify both use
the same field set. An arbitrary raw Gerrit-only field must not leak into board
JSON.

### TC-404: Reload failure emits stale fields and an error

Verify a Gerrit failure emits `number`, `instance`, stale cached fields, and
`error`, returns `1`, and does not add Rich or per-change error text to stdout.

### TC-405: Missing cache emits an identity-bearing error record

Without reload, verify the JSON array includes number, instance, and a message
instructing the user to use `--reload`.

### TC-406: Unknown instance emits an identity-bearing error record on reload

Verify the JSON array includes the unknown instance name, tracked number, and a
clear error while other records still succeed.

### TC-407: Complete JSON success returns zero

Given all successful queries, verify valid JSON output and exit status `0`.
