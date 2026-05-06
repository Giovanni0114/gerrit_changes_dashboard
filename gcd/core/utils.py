import os
import select
import subprocess
import sys
import termios
import tty
from enum import Enum
from functools import lru_cache
from threading import Lock
from typing import Self


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


ENDLINES = ("\r", "\n")
BACKSPACES = ("\x7f", "\x08")
ESCAPE = "\x1b"
ARROWS_PREFIXES = (b"[", b"O")


class Arrow(Enum):
    UP = b"A"
    DOWN = b"B"
    RIGHT = b"C"
    LEFT = b"D"


ARROWS = {a.value: a for a in Arrow}


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

    def read_key(self, timeout: float = 0.1) -> str | Arrow | None:
        ready, _, _ = select.select([self.fd], [], [], timeout)
        if not ready:
            return None
        data = os.read(self.fd, 1).decode("utf-8", errors="replace")
        if data == ESCAPE:
            # Possible escape sequence — drain remaining bytes
            while select.select([self.fd], [], [], 0.02)[0]:
                if os.read(self.fd, 1) in ARROWS_PREFIXES:
                    key = os.read(self.fd, 1)
                    if key in ARROWS:
                        return ARROWS[key]

            return "<esc>"

        if data == "\t":
            return "<tab>"

        if data in ENDLINES:
            return "<enter>"

        if data in BACKSPACES:
            return "<bs>"

        return data

    def __enter__(self) -> Self:
        return self.enable()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.disable()

@lru_cache(maxsize=1)
def get_email_from_git_config() -> str | None:
    try:
        result = subprocess.run(
            ["git", "config", "user.email"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        email = result.stdout.strip()
        return email
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
