import json
from unittest.mock import MagicMock, patch

import pytest

from gcd.core.gerrit import GerritCommunication
from gcd.core.models import GerritInstance
from gcd.core.ssh import SshResult


def _instance() -> GerritInstance:
    return GerritInstance("prod", "gerrit.example.com", 22, "user@example.com")


@patch("gcd.core.gerrit.SSHCommunication")
def test_query_change_comments_returns_comment_records(ssh_communication: MagicMock) -> None:
    ssh_communication.return_value.execute_ssh_request.return_value = SshResult(
        True,
        duration=0.1,
        data='{"comments": [{"message": "looks good"}]}\n{"type": "stats"}',
    )

    result = GerritCommunication().query_change_comments(_instance(), "123")

    assert result == [{"message": "looks good"}]
    command = ssh_communication.return_value.execute_ssh_request.call_args.args[0]
    assert "123" in command
    assert "--comments" in command


@patch("gcd.core.gerrit.SSHCommunication")
def test_query_change_comments_returns_not_found_for_empty_query(ssh_communication: MagicMock) -> None:
    ssh_communication.return_value.execute_ssh_request.return_value = SshResult(True, duration=0.1, data="")

    result = GerritCommunication().query_change_comments(_instance(), "123")

    assert result == {"error": "Change not found"}


@patch("gcd.core.gerrit.SSHCommunication")
@pytest.mark.parametrize(
    "comments",
    [
        {"message": "not a list"},
        ["not a record"],
    ],
)
def test_query_change_comments_returns_error_for_malformed_comments(
    ssh_communication: MagicMock, comments: object
) -> None:
    ssh_communication.return_value.execute_ssh_request.return_value = SshResult(
        True,
        duration=0.1,
        data=json.dumps({"comments": comments}),
    )

    result = GerritCommunication().query_change_comments(_instance(), "123")

    assert result == {"error": "Could not get comments"}


@patch("gcd.core.gerrit.SSHCommunication")
@pytest.mark.parametrize(
    "data",
    [
        "not json",
        '"a scalar value"',
    ],
)
def test_query_change_comments_returns_error_for_invalid_query_record(ssh_communication: MagicMock, data: str) -> None:
    ssh_communication.return_value.execute_ssh_request.return_value = SshResult(True, duration=0.1, data=data)

    result = GerritCommunication().query_change_comments(_instance(), "123")

    assert result == {"error": "Could not get comments"}


@patch("gcd.core.gerrit.SSHCommunication")
def test_query_change_comments_returns_error_for_ssh_failure(ssh_communication: MagicMock) -> None:
    ssh_communication.return_value.execute_ssh_request.return_value = SshResult(
        False,
        duration=0.1,
        msg="connection failed",
    )

    result = GerritCommunication().query_change_comments(_instance(), "123")

    assert result == {"error": "Could not get comments"}
