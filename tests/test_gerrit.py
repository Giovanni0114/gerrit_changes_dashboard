import os
import shlex
import subprocess
from unittest.mock import MagicMock

import pytest

from gcd.core.gerrit import GerritCommunication
from gcd.core.models import GerritInstance
from gcd.core.ssh import SshResult


def test_review_message_preserves_complete_message_as_one_ssh_argument():
    comm = GerritCommunication()
    comm.ssh_communication.execute_ssh_request = MagicMock(return_value=SshResult(True, duration=0.1, data=""))
    instance = GerritInstance("prod", "gerrit.example.com", 29418, "tester@example.com")
    message = 'Ready to merge; don\'t expand $HOME or "quotes" \\ paths --submit'

    result = comm.review_message(instance, "deadbeef", message)

    assert result == {"success": True}
    command = comm.ssh_communication.execute_ssh_request.call_args.args[0]
    assert command == [
        "ssh",
        "-x",
        "-p",
        "29418",
        "gerrit.example.com",
        "gerrit",
        "review",
        "deadbeef",
        "--message",
        shlex.quote(message),
    ]
    remote_command = " ".join(command[5:])
    result = subprocess.run(
        [
            "sh",
            "-c",
            'gerrit() { for argument do printf "<%s>" "$argument"; done; }; eval "$1"',
            "sh",
            remote_command,
        ],
        check=True,
        capture_output=True,
        env={**os.environ, "HOME": "/must-not-expand"},
        text=True,
    )

    assert result.stdout == f"<review><deadbeef><--message><{message}>"


@pytest.mark.parametrize(
    ("ssh_message", "expected"),
    [
        ("error: permission denied", {"error": "permission denied"}),
        ("connection closed", {"error": "Fatal: error occurred but no error message was collected"}),
    ],
)
def test_review_message_uses_review_error_contract(ssh_message, expected):
    comm = GerritCommunication()
    comm.ssh_communication.execute_ssh_request = MagicMock(return_value=SshResult(False, duration=0.1, msg=ssh_message))
    instance = GerritInstance("prod", "gerrit.example.com", 29418, "tester@example.com")

    assert comm.review_message(instance, "deadbeef", "Needs work") == expected
