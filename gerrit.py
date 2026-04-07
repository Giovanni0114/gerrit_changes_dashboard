import json
import subprocess
import threading

_ssh_lock = threading.Lock()
ssh_request_count: int = 0


def query_set_automerge(commit_hash: str, host: str, port: int | None = None) -> dict:
    global ssh_request_count
    with _ssh_lock:
        ssh_request_count += 1
    cmd = ["ssh", "-x"]
    if port is not None:
        cmd += ["-p", str(port)]
    cmd += [host, "gerrit", "review", commit_hash, "--label", "Automerge=+1"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            stderr = result.stderr.strip()
            msg = f"Gerrit review failed ({stderr})" if stderr else "Gerrit review failed"
            return {"error": msg}
        return {"success": True}
    except subprocess.TimeoutExpired:
        return {"error": "SSH timeout"}


def query_approvals(commit_hash: str, host: str, port: int | None = None) -> dict:
    global ssh_request_count
    with _ssh_lock:
        ssh_request_count += 1
    cmd = ["ssh", "-x"]
    if port is not None:
        cmd += ["-p", str(port)]
    cmd += [host, "gerrit", "query", "--format=json", "--all-approvals", commit_hash]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        lines = result.stdout.strip().splitlines()
        if not lines:
            stderr = result.stderr.strip()
            msg = f"No output from Gerrit ({stderr})" if stderr else "No output from Gerrit"
            return {"error": msg}
        data = json.loads(lines[0])
        if "type" in data and data["type"] == "stats":
            return {"error": "Change not found"}
        return data
    except subprocess.TimeoutExpired:
        return {"error": "SSH timeout"}
    except (json.JSONDecodeError, IndexError) as exc:
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
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
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
        return changes
    except subprocess.TimeoutExpired:
        return []
