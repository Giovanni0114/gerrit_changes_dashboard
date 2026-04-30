import json
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Literal

from gcd.core.logs import ssh_logger
from gcd.core.models import GerritInstance

from .ssh import SSHCommunication

_log = ssh_logger()


def _endpoint(host: str, port: int) -> str:
    return f"{host}:{port}"


GerritSubcommand = Literal["review", "query"]
GerritReviewSubcommand = Literal["abandon", "code-review", "label", "rebase", "restore", "restore", "submit"]


@dataclass(frozen=True)
class GerritQueryStats:
    row_count: int | None
    run_time_miliseconds: int | None
    more_chagnges: bool | None


def make_gerrit_query_stats(data: dict) -> GerritQueryStats:
    row_count = data.get("rowCount")
    run_time = data.get("runtTimeMilliseconds")
    more_changes = data.get("moreChanges")

    return GerritQueryStats(row_count, run_time, more_changes)


def _base_ssh_cmd(instance: GerritInstance, subcommand: GerritSubcommand) -> list[str]:
    return ["ssh", "-x", "-p", str(instance.port), instance.host, "gerrit", subcommand]


def _base_ssh_review_cmd(
    instance: GerritInstance,
    revision: str,
    review_subcommand: GerritReviewSubcommand,
) -> list[str]:
    return [*_base_ssh_cmd(instance, "review"), revision, review_subcommand]


class GerritCommunication:
    ssh_communication: SSHCommunication

    def query_changes(self, instance: GerritInstance, query_args: list[str]) -> list[dict]:
        base_cmd = _base_ssh_cmd(instance, "query")
        cmd = [*base_cmd, *query_args]

        result = self.ssh_communication.execute_ssh_request(cmd)

        if not result.ok() or result.data is None:
            # TBD error log
            return [{"error": result.msg}]

        lines = result.data.splitlines()
        changes = []

        for line in lines:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            if obj.get("type") == "stats":
                # TODO think what can be done with it
                stats = make_gerrit_query_stats(obj)
                _log.info(f"ssh gerrit query stats: {stats}")
            else:
                changes.append(obj)

        return changes

    # TODO: create more generic "set label"
    # But this requires creating some mechanism for defining allowed labels
    # maybe can be done via plugin, maybe some "instance rules"???
    def review_set_automerge(self, instance: GerritInstance, revision: str) -> str | None:
        base_cmd = _base_ssh_review_cmd(instance, revision, "label")

        cmd = [*base_cmd, "Automerge=+1"]

        result = self.ssh_communication.execute_ssh_request(cmd)

        if result.ok():
            return None

        if result.msg:
            err_lines = result.msg.splitlines()
            err_lines = [line for line in err_lines if line.startswith("error: ")]
            for line in err_lines:
                return line.removeprefix("error: ")


        return "Fatal: error occured but no error message was collected"



def query_set_automerge(revision: str, host: str, port: int | None = None) -> dict:
    global ssh_request_count
    with _ssh_lock:
        ssh_request_count += 1
    cmd = ["ssh", "-x"]
    if port is not None:
        cmd += ["-p", str(port)]
    cmd += [host, "gerrit", "review", revision, "--label", "Automerge=+1"]

    start = time.monotonic()
    endpoint = _endpoint(host, port)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        duration = time.monotonic() - start
        if result.returncode != 0:
            stderr = result.stderr.strip()
            _log.warning(
                "action=set_automerge endpoint=%s revision=%s duration=%.3fs status=failed rc=%d stderr=%r",
                endpoint,
                revision,
                duration,
                result.returncode,
                stderr,
            )
            msg = f"Gerrit review failed ({stderr})" if stderr else "Gerrit review failed"
            return {"error": msg}
        _log.info(
            "action=set_automerge endpoint=%s revision=%s duration=%.3fs status=ok",
            endpoint,
            revision,
            duration,
        )
        return {"success": True}
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - start
        _log.warning(
            "action=set_automerge endpoint=%s revision=%s duration=%.3fs status=timeout",
            endpoint,
            revision,
            duration,
        )
        return {"error": "SSH timeout"}


def query_review_abandon(revision: str, host: str, port: int | None = None) -> dict:
    global ssh_request_count
    with _ssh_lock:
        ssh_request_count += 1
    cmd = ["ssh", "-x"]
    if port is not None:
        cmd += ["-p", str(port)]
    cmd += [host, "gerrit", "review", revision, "--abandon"]

    start = time.monotonic()
    endpoint = _endpoint(host, port)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        duration = time.monotonic() - start
        if result.returncode != 0:
            stderr = result.stderr.strip()
            _log.warning(
                "action=review_abandon endpoint=%s revision=%s duration=%.3fs status=failed rc=%d stderr=%r",
                endpoint,
                revision,
                duration,
                result.returncode,
                stderr,
            )
            msg = f"Gerrit review failed ({stderr})" if stderr else "Gerrit review failed"
            return {"error": msg}
        _log.info(
            "action=review_abandon endpoint=%s revision=%s duration=%.3fs status=ok",
            endpoint,
            revision,
            duration,
        )
        return {"success": True}
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - start
        _log.warning(
            "action=review_abandon endpoint=%s revision=%s duration=%.3fs status=timeout",
            endpoint,
            revision,
            duration,
        )
        return {"error": "SSH timeout"}


def query_review_restore(revision: str, host: str, port: int | None = None) -> dict:
    global ssh_request_count
    with _ssh_lock:
        ssh_request_count += 1
    cmd = ["ssh", "-x"]
    if port is not None:
        cmd += ["-p", str(port)]
    cmd += [host, "gerrit", "review", revision, "--restore"]

    start = time.monotonic()
    endpoint = _endpoint(host, port)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        duration = time.monotonic() - start
        if result.returncode != 0:
            stderr = result.stderr.strip()
            _log.warning(
                "action=review_restore endpoint=%s revision=%s duration=%.3fs status=failed rc=%d stderr=%r",
                endpoint,
                revision,
                duration,
                result.returncode,
                stderr,
            )
            msg = f"Gerrit review failed ({stderr})" if stderr else "Gerrit review failed"
            return {"error": msg}
        _log.info(
            "action=review_restore endpoint=%s revision=%s duration=%.3fs status=ok",
            endpoint,
            revision,
            duration,
        )
        return {"success": True}
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - start
        _log.warning(
            "action=review_restore endpoint=%s revision=%s duration=%.3fs status=timeout",
            endpoint,
            revision,
            duration,
        )
        return {"error": "SSH timeout"}


def query_review_submit(revision: str, host: str, port: int | None = None) -> dict:
    global ssh_request_count
    with _ssh_lock:
        ssh_request_count += 1
    cmd = ["ssh", "-x"]
    if port is not None:
        cmd += ["-p", str(port)]
    cmd += [host, "gerrit", "review", revision, "--submit"]

    start = time.monotonic()
    endpoint = _endpoint(host, port)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        duration = time.monotonic() - start
        if result.returncode != 0:
            stderr = result.stderr.strip()
            _log.warning(
                "action=review_submit endpoint=%s revision=%s duration=%.3fs status=failed rc=%d stderr=%r",
                endpoint,
                revision,
                duration,
                result.returncode,
                stderr,
            )
            msg = f"Gerrit review failed ({stderr})" if stderr else "Gerrit review failed"
            return {"error": msg}
        _log.info(
            "action=review_submit endpoint=%s revision=%s duration=%.3fs status=ok",
            endpoint,
            revision,
            duration,
        )
        return {"success": True}
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - start
        _log.warning(
            "action=review_submit endpoint=%s revision=%s duration=%.3fs status=timeout",
            endpoint,
            revision,
            duration,
        )
        return {"error": "SSH timeout"}


def query_review_rebase(revision: str, host: str, port: int | None = None) -> dict:
    global ssh_request_count
    with _ssh_lock:
        ssh_request_count += 1
    cmd = ["ssh", "-x"]
    if port is not None:
        cmd += ["-p", str(port)]
    cmd += [host, "gerrit", "review", revision, "--rebase"]

    start = time.monotonic()
    endpoint = _endpoint(host, port)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        duration = time.monotonic() - start
        if result.returncode != 0:
            stderr = result.stderr.strip()
            _log.warning(
                "action=review_rebase endpoint=%s revision=%s duration=%.3fs status=failed rc=%d stderr=%r",
                endpoint,
                revision,
                duration,
                result.returncode,
                stderr,
            )
            msg = f"Gerrit review failed ({stderr})" if stderr else "Gerrit review failed"
            return {"error": msg}
        _log.info(
            "action=review_rebase endpoint=%s revision=%s duration=%.3fs status=ok",
            endpoint,
            revision,
            duration,
        )
        return {"success": True}
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - start
        _log.warning(
            "action=review_rebase endpoint=%s revision=%s duration=%.3fs status=timeout",
            endpoint,
            revision,
            duration,
        )
        return {"error": "SSH timeout"}


def query_review_code_review(revision: str, score: int, host: str, port: int | None = None) -> dict:
    global ssh_request_count
    with _ssh_lock:
        ssh_request_count += 1
    cmd = ["ssh", "-x"]
    if port is not None:
        cmd += ["-p", str(port)]
    cmd += [host, "gerrit", "review", revision, "--code-review", str(score)]

    start = time.monotonic()
    endpoint = _endpoint(host, port)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        duration = time.monotonic() - start
        if result.returncode != 0:
            stderr = result.stderr.strip()
            _log.warning(
                "action=review_code_review endpoint=%s revision=%s score=%d "
                "duration=%.3fs status=failed rc=%d stderr=%r",
                endpoint,
                revision,
                score,
                duration,
                result.returncode,
                stderr,
            )
            msg = f"Gerrit review failed ({stderr})" if stderr else "Gerrit review failed"
            return {"error": msg}
        _log.info(
            "action=review_code_review endpoint=%s revision=%s score=%d duration=%.3fs status=ok",
            endpoint,
            revision,
            score,
            duration,
        )
        return {"success": True}
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - start
        _log.warning(
            "action=review_code_review endpoint=%s revision=%s score=%d duration=%.3fs status=timeout",
            endpoint,
            revision,
            score,
            duration,
        )
        return {"error": "SSH timeout"}


def query_approvals(query_id: str, host: str, port: int | None = None) -> dict:
    global ssh_request_count
    with _ssh_lock:
        ssh_request_count += 1
    cmd = ["ssh", "-x"]
    if port is not None:
        cmd += ["-p", str(port)]
    cmd += [host, "gerrit", "query", "--format=json", "--all-approvals", query_id]

    start = time.monotonic()
    endpoint = _endpoint(host, port)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        duration = time.monotonic() - start
        lines = result.stdout.strip().splitlines()
        if not lines:
            stderr = result.stderr.strip()
            _log.warning(
                "action=query_approvals endpoint=%s id=%s duration=%.3fs status=empty stderr=%r",
                endpoint,
                query_id,
                duration,
                stderr,
            )
            msg = f"No output from Gerrit ({stderr})" if stderr else "No output from Gerrit"
            return {"error": msg}
        data = json.loads(lines[0])
        if "type" in data and data["type"] == "stats":
            _log.info(
                "action=query_approvals endpoint=%s id=%s duration=%.3fs status=not_found",
                endpoint,
                query_id,
                duration,
            )
            return {"error": "Change not found"}
        _log.info(
            "action=query_approvals endpoint=%s id=%s duration=%.3fs status=ok",
            endpoint,
            query_id,
            duration,
        )
        return data
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - start
        _log.warning(
            "action=query_approvals endpoint=%s id=%s duration=%.3fs status=timeout",
            endpoint,
            query_id,
            duration,
        )
        return {"error": "SSH timeout"}
    except (json.JSONDecodeError, IndexError) as exc:
        duration = time.monotonic() - start
        _log.error(
            "action=query_approvals endpoint=%s id=%s duration=%.3fs status=parse_error error=%r",
            endpoint,
            query_id,
            duration,
            str(exc),
        )
        return {"error": str(exc)}


def is_submitted(data: dict) -> bool:
    """Check if any patchset has a SUBM approval (change is submitted)."""
    for ps in data.get("patchSets", []):
        if any(appr.get("type", "?") == "SUBM" for appr in ps.get("approvals", [])):
            return True
    return False


def query_open_changes(email: str, host: str, port: int | None = None) -> list[dict]:
    """Query Gerrit for all open changes owned by the given email.

    Returns a list of change dicts. Each dict contains at least
    ``currentPatchSet.revision`` and ``number``.  Returns an empty
    list on SSH failure (timeout, non-zero exit).
    """
    global ssh_request_count
    with _ssh_lock:
        ssh_request_count += 1
    cmd = ["ssh", "-x"]
    if port is not None:
        cmd += ["-p", str(port)]
    cmd += [host, "gerrit", "query", "--format=json", "--current-patch-set", f"owner:{email}", "is:open"]

    start = time.monotonic()
    endpoint = _endpoint(host, port)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        duration = time.monotonic() - start
        if result.returncode != 0:
            _log.warning(
                "action=query_open_changes endpoint=%s owner=%s duration=%.3fs status=failed rc=%d",
                endpoint,
                email,
                duration,
                result.returncode,
            )
            return []
        changes: list[dict] = []
        for line in result.stdout.strip().splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "stats":
                continue
            changes.append(obj)
        _log.info(
            "action=query_open_changes endpoint=%s owner=%s duration=%.3fs status=ok count=%d",
            endpoint,
            email,
            duration,
            len(changes),
        )
        return changes
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - start
        _log.warning(
            "action=query_open_changes endpoint=%s owner=%s duration=%.3fs status=timeout",
            endpoint,
            email,
            duration,
        )
        return []
