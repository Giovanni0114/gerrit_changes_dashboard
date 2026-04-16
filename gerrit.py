import json
import subprocess
import threading
import time

from logs import ssh_logger

_ssh_lock = threading.Lock()
ssh_request_count: int = 0
_log = ssh_logger()


def _endpoint(host: str, port: int | None) -> str:
    return f"{host}:{port}" if port is not None else host


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
                endpoint, revision, duration, result.returncode, stderr,
            )
            msg = f"Gerrit review failed ({stderr})" if stderr else "Gerrit review failed"
            return {"error": msg}
        _log.info(
            "action=set_automerge endpoint=%s revision=%s duration=%.3fs status=ok",
            endpoint, revision, duration,
        )
        return {"success": True}
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - start
        _log.warning(
            "action=set_automerge endpoint=%s revision=%s duration=%.3fs status=timeout",
            endpoint, revision, duration,
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
                endpoint, query_id, duration, stderr,
            )
            msg = f"No output from Gerrit ({stderr})" if stderr else "No output from Gerrit"
            return {"error": msg}
        data = json.loads(lines[0])
        if "type" in data and data["type"] == "stats":
            _log.info(
                "action=query_approvals endpoint=%s id=%s duration=%.3fs status=not_found",
                endpoint, query_id, duration,
            )
            return {"error": "Change not found"}
        _log.info(
            "action=query_approvals endpoint=%s id=%s duration=%.3fs status=ok",
            endpoint, query_id, duration,
        )
        return data
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - start
        _log.warning(
            "action=query_approvals endpoint=%s id=%s duration=%.3fs status=timeout",
            endpoint, query_id, duration,
        )
        return {"error": "SSH timeout"}
    except (json.JSONDecodeError, IndexError) as exc:
        duration = time.monotonic() - start
        _log.error(
            "action=query_approvals endpoint=%s id=%s duration=%.3fs status=parse_error error=%r",
            endpoint, query_id, duration, str(exc),
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
                endpoint, email, duration, result.returncode,
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
            endpoint, email, duration, len(changes),
        )
        return changes
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - start
        _log.warning(
            "action=query_open_changes endpoint=%s owner=%s duration=%.3fs status=timeout",
            endpoint, email, duration,
        )
        return []
