import json
from typing import Literal

from gcd.core.logs import ssh_logger
from gcd.core.models import GerritInstance

from .ssh import SSHCommunication

_log = ssh_logger()

GerritSubcommand = Literal["review", "query"]
GerritReviewSubcommand = Literal["abandon", "code-review", "label", "rebase", "restore", "submit"]


def _base_ssh_cmd(instance: GerritInstance) -> list[str]:
    return ["ssh", "-x", "-p", str(instance.port), instance.host, "gerrit"]


def _base_ssh_review_cmd(
    instance: GerritInstance,
    revision: str,
    review_subcommand: GerritReviewSubcommand,
) -> list[str]:
    return [*_base_ssh_cmd(instance), "review", revision, f"--{review_subcommand}"]


def _base_ssh_query_cmd(instance: GerritInstance) -> list[str]:
    return [*_base_ssh_cmd(instance), "query", "--format=json", "--current-patch-set"]


class GerritCommunication:
    def __init__(self) -> None:
        self.ssh_communication = SSHCommunication()

    @property
    def ssh_request_count(self) -> int:
        return self.ssh_communication.request_count.value()

    def _query(self, instance: GerritInstance, *query_args: str) -> list[dict]:
        base_cmd = _base_ssh_query_cmd(instance)
        cmd = [*base_cmd, *query_args]

        result = self.ssh_communication.execute_ssh_request(cmd)

        if not result.ok() or result.data is None:
            return [{"error": result.msg}]

        lines = result.data.splitlines()
        changes = []

        for line in lines:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as ex:
                obj = {"error": str(ex)}

            if obj.get("type") == "stats":
                _log.info(f"ssh gerrit query stats: {obj}")
            else:
                changes.append(obj)

        return changes

    def _review(self, instance: GerritInstance, subcommand: GerritReviewSubcommand, revision: str, *args: str) -> dict:
        base_cmd = _base_ssh_review_cmd(instance, revision, subcommand)
        cmd = [*base_cmd, *args]

        result = self.ssh_communication.execute_ssh_request(cmd)

        if result.ok():
            return {"success": True}

        if result.msg:
            err_lines = result.msg.splitlines()
            err_lines = [line for line in err_lines if line.startswith("error: ")]
            for line in err_lines:
                return {"error": line.removeprefix("error: ")}

        return {"error": "Fatal: error occurred but no error message was collected"}

    def review_set_label(self, instance: GerritInstance, revision: str, label: str, value: str) -> dict:
        return self._review(instance, "label", revision, f"{label}={value}")

    def review_set_automerge(self, instance: GerritInstance, revision: str) -> dict:
        return self.review_set_label(instance, revision, "Automerge", "+1")

    def review_abandon(self, instance: GerritInstance, revision: str) -> dict:
        return self._review(instance, "abandon", revision)

    def review_restore(self, instance: GerritInstance, revision: str) -> dict:
        return self._review(instance, "restore", revision)

    def review_submit(self, instance: GerritInstance, revision: str) -> dict:
        return self._review(instance, "submit", revision)

    def review_rebase(self, instance: GerritInstance, revision: str) -> dict:
        return self._review(instance, "rebase", revision)

    def review_code_review(self, instance: GerritInstance, revision: str, score: int) -> dict:
        return self._review(instance, "code-review", revision, str(score))

    def query_change(self, instance: GerritInstance, change_id: str) -> dict:
        if changes := self._query(instance, change_id):
            return next(iter(changes))

        return {"error": "Change not found"}

    def query_change_comments(self, instance: GerritInstance, change_id: str) -> list[dict]:
        changes = self._query(instance, change_id, "--comments")

        if not changes:
            return {"error": "Change not found"}

        change = next(iter(changes))

        if "comments" not in change:
            return {"error": "Could not get comments"}

        return change["comments"]

    def query_open_changes(self, instance: GerritInstance) -> list[dict]:
        return self._query(instance, f"owner:{instance.email}", "is:open")
