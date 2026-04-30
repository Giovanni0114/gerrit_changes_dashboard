import subprocess
import time
from dataclasses import dataclass
from typing import Literal

from gcd.core.logs import ssh_logger
from gcd.core.utils import AtomicCounter

Result = Literal["success", "failure"]

_log = ssh_logger()


@dataclass(frozen=True)
class SshResult:
    result: Result
    duration: float
    msg: str | None = None
    data: str | None = None

    def ok(self) -> bool:
        return self.result == "success"


def _make_success_ssh_result(duration: float, data: str) -> SshResult:
    return SshResult("success", duration=duration, data=data)


def _make_failure_ssh_result(duration: float, msg: str) -> SshResult:
    return SshResult("failure", duration=duration, msg=msg)


class SSHCommunication:
    request_count = AtomicCounter()

    def execute_ssh_request(self, cmd: list[str]) -> SshResult:
        self.request_count.increment()

        start = time.monotonic()
        _log.info(f"executing {cmd}")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            duration = time.monotonic() - start
            if result.returncode != 0:
                return _make_failure_ssh_result(duration, result.stderr.strip())

            return _make_success_ssh_result(duration, result.stdout.strip())
        except subprocess.TimeoutExpired as ex:
            duration = time.monotonic() - start
            return _make_failure_ssh_result(duration, str(ex))
