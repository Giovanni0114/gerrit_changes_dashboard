import json
import subprocess


def query_approvals(commit_hash: str, host: str) -> dict:
    cmd = [
        "ssh",
        "-x",
        host,
        "gerrit",
        "query",
        "--format=json",
        "--all-approvals",
        commit_hash,
    ]
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


def approval_snapshot(data: dict) -> frozenset[tuple[str, str, str]]:
    """Return a fingerprint of the current approvals for change-detection."""
    patch_sets = data.get("patchSets", [])
    if not patch_sets:
        return frozenset()
    approvals = patch_sets[-1].get("approvals", [])
    return frozenset(
        (appr.get("type", ""), appr.get("value", ""), appr.get("by", {}).get("name", "")) for appr in approvals
    )


def is_submitted(data: dict) -> bool:
    """Check if any patchset has a SUBM approval (change is submitted)."""
    for ps in data.get("patchSets", []):
        if any(appr.get("type", "?") == "SUBM" for appr in ps.get("approvals", [])):
            return True
    return False
