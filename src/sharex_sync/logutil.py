"""Logging setup for sharex-sync.

Writes to a daily-rotating log file with a configurable retention window
(TTL), plus the console. Stdlib-only so ``uv tool install`` has zero deps.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

LOGGER_NAME = "sharex_sync"

# Env overrides: SHAREX_SYNC_LOG_DIR, SHAREX_SYNC_LOG_RETENTION
ENV_LOG_DIR = "SHAREX_SYNC_LOG_DIR"
ENV_LOG_RETENTION = "SHAREX_SYNC_LOG_RETENTION"

_LOG_FILE_NAME = "sharex-sync.log"


class _SafeTimedRotatingFileHandler(TimedRotatingFileHandler):
    """TimedRotatingFileHandler that does not explode on Windows file locks.

    Long-running commands (e.g. ``sharex-sync recctl``) keep the log open.
    A short CLI run then tries to rotate at midnight and hits WinError 32
    (file in use). Swallow that and keep logging to the current file.
    """

    def doRollover(self) -> None:  # noqa: N802 - stdlib name
        try:
            super().doRollover()
        except PermissionError:
            # Another process holds the log; skip rotation this pass.
            pass
        except OSError as exc:
            # Windows sharing violation
            if getattr(exc, "winerror", None) == 32:
                pass
            else:
                raise


def default_log_dir() -> Path:
    env = os.environ.get(ENV_LOG_DIR)
    if env:
        return Path(env).expanduser()
    return Path.home() / ".sharex-sync" / "logs"


def default_retention_days() -> int:
    env = os.environ.get(ENV_LOG_RETENTION)
    if env and env.strip().isdigit():
        return max(1, int(env.strip()))
    return 7


def setup_logging(
    log_dir: Path | None = None,
    retention_days: int | None = None,
    verbose: bool = False,
) -> logging.Logger:
    """Configure the package logger. Returns the logger.

    ``log_dir``   directory for the rotating log file (None => default dir).
    ``retention_days`` number of daily backups to keep (TTL in days).
    """
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s")
    fmt.default_msec_format = "%s.%03d"

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(fmt)
    logger.addHandler(console)

    if log_dir is None:
        log_dir = default_log_dir()
    if retention_days is None:
        retention_days = default_retention_days()

    log_dir = Path(log_dir).expanduser()
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = _SafeTimedRotatingFileHandler(
            log_dir / _LOG_FILE_NAME,
            when="midnight",
            backupCount=max(1, retention_days),
            encoding="utf-8",
            delay=True,  # open on first emit; reduces lock fights a bit
        )
        file_handler.suffix = "%Y-%m-%d"
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
        logger.debug("Log file: %s (retention %d days)", log_dir / _LOG_FILE_NAME, retention_days)
    except OSError as exc:
        logger.warning("Could not set up log file in %s: %s", log_dir, exc)

    return logger
