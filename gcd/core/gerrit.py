import json
from typing import Literal

from gcd.core.logs import ssh_logger
from gcd.core.models import CommentQueryResult, CommentRecord, GerritInstance

from .ssh import SSHCommunication

_log = ssh_logger()

GerritSubcommand = Literal["review", "query"]
GerritReviewSubcommand = Literal["abandon", "code-review", "label", "rebase", "restore", "submit"]
JsonRecord = dict[str, object]


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

    def _query(self, instance: GerritInstance, *query_args: str) -> list[JsonRecord]:
        base_cmd = _base_ssh_query_cmd(instance)
        cmd = [*base_cmd, *query_args]

        result = self.ssh_communication.execute_ssh_request(cmd)

        if not result.ok() or result.data is None:
            return [{"error": result.msg}]

        lines = result.data.splitlines()
        changes: list[JsonRecord] = []

        for line in lines:
            if not line.strip():
                continue
            try:
                decoded = json.loads(line)
            except json.JSONDecodeError as ex:
                changes.append({"error": str(ex)})
                continue

            if not isinstance(decoded, dict):
                changes.append({"error": "Expected JSON object"})
                continue

            obj: JsonRecord = {}
            for key, value in decoded.items():
                if not isinstance(key, str):
                    changes.append({"error": "Expected string JSON object keys"})
                    break
                obj[key] = value
            else:
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
        if changes := self._query(instance, f"change:{change_id}"):
            return next(iter(changes))

        return {"error": "Change not found"}

    def query_change_comments(self, instance: GerritInstance, change_id: str) -> CommentQueryResult:
        changes = self._query(instance, change_id, "--comments")

        if not changes:
            return {"error": "Change not found"}

        change = next(iter(changes))

        comments = change.get("comments")
        if not isinstance(comments, list):
            return {"error": "Could not get comments"}

        comment_records: list[CommentRecord] = []
        for comment in comments:
            if not isinstance(comment, dict):
                return {"error": "Could not get comments"}

            record: CommentRecord = {}
            for key, value in comment.items():
                if not isinstance(key, str):
                    return {"error": "Could not get comments"}
                record[key] = value
            comment_records.append(record)

        return comment_records

    def query_open_changes(self, instance: GerritInstance) -> list[JsonRecord]:
        return self._query(instance, f"owner:{instance.email}", "is:open")

    def query_operators(self, instance: GerritInstance, operators: list[str]) -> list[JsonRecord]:
        return self._query(instance, *operators)
