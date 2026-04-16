import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_APP = "gcd.app"
_SSH = "gcd.ssh"
_MCP = "gcd.mcp"

_MAX_BYTES = 5 * 1024 * 1024
_BACKUPS = 5
_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%S"


def _build(name: str, log_dir: Path, filename: str) -> logging.Logger:
    logger = logging.getLogger(name)
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()

    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = RotatingFileHandler(
        log_dir / filename,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUPS,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))
    logger.addHandler(handler)
    return logger


def setup_logging(log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    _build(_APP, log_dir, "app.log")
    _build(_SSH, log_dir, "ssh.log")
    _build(_MCP, log_dir, "mcp.log")
    return log_dir


def app_logger() -> logging.Logger:
    return logging.getLogger(_APP)


def ssh_logger() -> logging.Logger:
    return logging.getLogger(_SSH)


def mcp_logger() -> logging.Logger:
    return logging.getLogger(_MCP)
