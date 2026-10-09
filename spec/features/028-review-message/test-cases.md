# 028 - Test Cases

No test makes a real SSH connection.

## Input Flow

### TC-001: Publish key sequence dispatches message action

Enter `Space`, `r`, `p`, an index expression, and a message. Verify the parsed
indices and complete message reach the app context.

### TC-002: Escape cancels message entry

Cancel while entering the message and verify no publish action is dispatched.

### TC-003: Message input does not perform tag completion

Enter a message beginning with `#`, press Tab, and verify local comment tags do
not replace the review message.

## App Behavior

### TC-101: A message is published to one change

Given a tracked change with a current revision and known instance, verify the
message operation receives that instance, revision, and exact message. Verify no
refresh starts and success is reported.

### TC-102: A message is published to every selected change

Select changes from multiple configured instances and verify every change is
sent through its matching instance with the same message.

### TC-103: Empty messages are rejected

Use an empty and a whitespace-only message. Verify no Gerrit operation occurs
and clear failure feedback is shown.

### TC-104: Missing revision does not block valid changes

Select one change without a revision and one valid change. Verify only the valid
change is sent and the aggregate result reports the partial failure.

### TC-105: Gerrit failure does not block remaining changes

Make one Gerrit call fail and another succeed. Verify both are attempted and the
aggregate result contains the successful count and failed change information.

### TC-106: Unknown instance does not block valid changes

Select a change with an unconfigured instance and a valid change. Verify no call
is made for the unknown instance, the valid change is sent, and both outcomes
are represented in the aggregate status.

## SSH Boundary

### TC-201: Message is one exact SSH argument

Publish a message containing spaces, quotes, backslashes, shell-sensitive
characters, and option-looking text. Verify the SSH executor receives a safely
quoted remote argument and that Gerrit's command-line parsing reconstructs the
unchanged complete message as one argument.

### TC-202: SSH errors use the existing review result contract

Return an unsuccessful SSH result and verify the message operation exposes the
same error dictionary shape as the other review operations.
