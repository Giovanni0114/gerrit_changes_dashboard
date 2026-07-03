import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

_APP = "gcd.app"
_SSH = "gcd.ssh"
_PLUGIN = "gcd.plugin"

_MAX_BYTES = 5 * 1024 * 1024
_BACKUPS = 5
_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%S"
_DEFAULT_LEVEL = logging.INFO


def _log_level_from_env() -> int:
    raw_level = os.getenv("LOG_LEVEL")
    if raw_level is None:
        return _DEFAULT_LEVEL

    normalized = raw_level.strip().upper()
    if not normalized:
        return _DEFAULT_LEVEL

    level = logging.getLevelNamesMapping().get(normalized)
    return level if isinstance(level, int) else _DEFAULT_LEVEL


def _build(name: str, log_dir: Path, filename: str) -> logging.Logger:
    logger = logging.getLogger(name)
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()

    level = _log_level_from_env()
    logger.setLevel(level)
    logger.propagate = False

    handler = RotatingFileHandler(
        log_dir / filename,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUPS,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))
    logger.addHandler(handler)
    logger.info("------------------ START --------------------")
    return logger


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    _build(_APP, log_dir, "app.log")
    _build(_SSH, log_dir, "ssh.log")
    _build(_PLUGIN, log_dir, "plugin.log")


def app_logger() -> logging.Logger:
    return logging.getLogger(_APP)


def ssh_logger() -> logging.Logger:
    return logging.getLogger(_SSH)


def plugin_logger(plugin_name: str, instance_name: str) -> logging.Logger:
    class PluginLogger(logging.LoggerAdapter):
        def process(self, msg, kwargs):
            return f"[{plugin_name}:{instance_name}] {msg}", kwargs

    return PluginLogger(logging.getLogger(_PLUGIN))
