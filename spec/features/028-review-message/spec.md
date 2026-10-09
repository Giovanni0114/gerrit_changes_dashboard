# 028 - Publish Gerrit review messages

## Problem

The dashboard can perform Gerrit review operations, but publishing a plain
review message still requires leaving the TUI. Add an action that sends one
message to one or more tracked changes through Gerrit's SSH interface.

## Interaction

The review submenu gains the following flow:

```text
Space, r, p -> idx -> message -> Enter
```

- `p` means "publish message" and does not conflict with the existing `m`
  automerge action.
- `idx` uses the dashboard's existing single, list, range, and `a` notation.
- The message is one line because the current TUI input field completes on
  Enter.
- An empty or whitespace-only message is rejected without contacting Gerrit.
- Escape cancels the action through the existing input-handler behavior.

## Gerrit Command

For each resolved change, invoke the existing SSH execution boundary with an
argument vector equivalent to:

```text
ssh -x -p <port> <host> gerrit review <current-revision> --message <message>
```

OpenSSH joins remote command arguments into one command string before sending
it, and Gerrit parses that string again. The message is therefore wrapped in
double quotes for Gerrit's parser, with embedded double quotes and backslashes
escaped. This preserves spaces and option-looking text such as `--submit`
without allowing it to become another Gerrit argument. The command is still
executed without a local shell.

## Validation And Results

- A change with no current revision is not sent and contributes a failure.
- A change whose configured Gerrit instance cannot be resolved is not sent and
  contributes a failure.
- Every valid selected change is attempted even if another change fails.
- Complete success reports how many changes received the message.
- Mixed or complete failure reports the successful count and identifies each
  failed change with its error.
- Publishing does not start a refresh because the normal refresh query does not
  retrieve review messages.

## Code Changes

- Extend `GerritCommunication` with a message review operation.
- Extend `AppContext` and `App` with the publish-message action.
- Add a context action and `p` entry to the review input submenu.
- Use a dedicated `message` input field so local-comment tag completion does not
  alter Gerrit message input.
- Update test fakes and keyboard documentation.

## Testing

Tests cover the complete key sequence, empty-message rejection, one and many
changes, missing revisions, Gerrit failures, aggregate status, lack of refresh,
and reconstruction of the exact Gerrit argument from the SSH remote command.
SSH itself is replaced at the external execution boundary; no network
connection is made.

## Out Of Scope

- Multiline message editing.
- Draft comments or inline file comments.
- Combining a message with labels, submit, abandon, or other review options in
  one command.
- Fetching the newly published message back into the dashboard.
