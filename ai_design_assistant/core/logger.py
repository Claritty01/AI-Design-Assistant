"""Logging utilities used by the whole application (GUI‑agnostic).

Call :func:`configure_logging` exactly once — early in :pyfile:`__main__.py` —
to set up a console logger **and** a rotating file handler under the user’s
configuration directory (``~/.config/ai-design-assistant/ai_da.log`` on Linux,
``%APPDATA%\\AI Design Assistant\\ai_da.log`` on Windows, etc.).

The file handler is created even if the directory does not yet exist.
Log records are UTF‑8, max 1 MiB per file, with 3 backup files.

API keys found in well‑known environment variables are automatically masked
in every record (``sk-…`` ➜ ``***``).
"""
from __future__ import annotations

import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Final

from appdirs import user_config_dir

__all__: Final = ["configure_logging"]

_APP_NAME: Final = "AI Design Assistant"
_LOG_FILE_NAME: Final = "ai_da.log"
_MAX_BYTES: Final = 1 * 1024 * 1024  # 1 MiB
_BACKUP_COUNT: Final = 3

# Environment variable names that may contain secrets we want to mask
_SECRET_ENV_VARS: Final = (
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
)

_SECRET_PATTERN = re.compile(r"(sk-[A-Za-z0-9]{20,})")


def _mask_secrets(msg: str) -> str:
    """Replace API keys in *msg* with asterisks before they hit log sinks."""
    masked = msg
    for var in _SECRET_ENV_VARS:
        if (value := os.getenv(var)):
            masked = masked.replace(value, "***")
    # Generic pattern (sk-<token>)
    masked = _SECRET_PATTERN.sub("***", masked)
    return masked


class _SecretFilter(logging.Filter):
    """`logging.Filter` that masks secrets inside LogRecord messages."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: ANN001
        record.msg = _mask_secrets(str(record.msg))  # type: ignore[attr-defined]
        if record.args:
            # If using old‑style formatting — mask inside args too
            record.args = tuple(_mask_secrets(str(a)) for a in record.args)
        return True


def _get_log_path(custom_path: str | Path | None = None) -> Path:
    if custom_path is not None:
        return Path(custom_path).expanduser().resolve()
    cfg_dir = Path(user_config_dir(_APP_NAME))
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir / _LOG_FILE_NAME


_FMT = "% (asctime)s | %(levelname)-8s | %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: int = logging.INFO, *, log_path: str | Path | None = None) -> None:
    """Configure root logger.

    Should be invoked once at application start‑up.

    Parameters
    ----------
    level
        Minimal severity for console output (defaults to ``logging.INFO``).
    log_path
        Override default file location. ``None`` ➜ platform config dir.
    """
    root = logging.getLogger()
    if root.handlers:  # already configured
        return

    root.setLevel(logging.DEBUG)  # capture everything; handlers filter further

    secret_filter = _SecretFilter()

    # Console handler (stderr)
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(logging.Formatter(_FMT, datefmt=_DATEFMT))
    ch.addFilter(secret_filter)
    root.addHandler(ch)

    # Rotating file handler
    fh = RotatingFileHandler(
        _get_log_path(log_path),
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(_FMT, datefmt=_DATEFMT))
    fh.addFilter(secret_filter)
    root.addHandler(fh)

    logging.getLogger(__name__).debug("Logging configured (level=%s)", logging.getLevelName(level))
