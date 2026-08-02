"""Structured logging configuration.

Provides a single ``get_logger`` factory so every module logs consistently
instead of using bare ``print`` statements.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from config import PROJECT_ROOT, settings

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def configure_logging(debug: bool | None = None, log_dir: Path | None = None) -> None:
    """Configure the root logger once.

    Args:
        debug: If True, set level to DEBUG and add a console handler.
            Defaults to ``settings.debug``.
        log_dir: Directory where the rotating file log is written.
            Defaults to ``<project>/logs``.
    """
    global _configured
    if _configured:
        return

    level = logging.DEBUG if (debug if debug is not None else settings.debug) else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(formatter)
    root.addHandler(console)

    # File handler (rotating)
    log_dir = log_dir or (PROJECT_ROOT / "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    try:
        from logging.handlers import RotatingFileHandler

        file_handler = RotatingFileHandler(
            log_dir / "app.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        # If the log file cannot be created, fall back to console only.
        pass

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger for the given module name.

    Args:
        name: Usually ``__name__`` of the calling module.

    Returns:
        A configured :class:`logging.Logger` instance.
    """
    configure_logging()
    return logging.getLogger(name)
