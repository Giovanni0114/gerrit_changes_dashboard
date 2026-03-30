import datetime
import os
import select
import sys
import termios
import threading
import tty
from threading import Lock
from typing import Self

_log_lock = threading.Lock()
_session_id = datetime.datetime.now().strftime("%H%M%S")


def log(category: str, message: str, level: str = "INFO"):
    if not os.path.exists("logs"):
        os.makedirs("logs")

    today = datetime.datetime.now().strftime("%Y%m%d")
    filename = f"logs/{today}-{_session_id}.log"
    timestamp = datetime.datetime.now().isoformat(timespec="seconds")
    log_entry = f"[{timestamp}][{category}][{level}] {message}\n"
    with _log_lock:
        with open(filename, mode="a", encoding="utf-8") as f:
            f.write(log_entry)


class AtomicCounter:
    def __init__(self, initial_value: int = 0) -> None:
        self._counter = initial_value
        self._lock = Lock()

    def value(self):
        with self._lock:
            return self._counter

    def increment(self):
        with self._lock:
            self._counter += 1

    def decrement(self):
        with self._lock:
            self._counter -= 1

    def reset(self, value: int = 0):
        with self._lock:
            self._counter = value


class NoEcho:
    instance: "NoEcho | None" = None

    def enable(self) -> Self:
        self.fd = sys.stdin.fileno()
        self.old_settings = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)  # no echo, no enter-newline
        NoEcho.instance = self
        return self

    def disable(self) -> None:
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)
        NoEcho.instance = None

    def read_key(self, timeout: float = 0.1) -> str | None:
        """Non-blocking key read. Returns single char, 'ESC', or None on timeout."""
        ready, _, _ = select.select([self.fd], [], [], timeout)
        if not ready:
            return None
        data = os.read(self.fd, 1).decode("utf-8", errors="replace")
        if data == "\x1b":
            # Possible escape sequence — drain remaining bytes
            while select.select([self.fd], [], [], 0.02)[0]:
                os.read(self.fd, 1)
            return "ESC"
        return data

    def __enter__(self) -> Self:
        return self.enable()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.disable()

def authorized_tokens() -> set[str]:
    with open(".authorized_tokens", "r") as f:
        return set(line.strip() for line in f if line.strip())

