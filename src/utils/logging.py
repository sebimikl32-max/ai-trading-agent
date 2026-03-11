"""Structured logging setup."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Optional


class _JSONFormatter(logging.Formatter):
    """Emit log records as single-line JSON strings."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            log_obj["exc"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)


def setup_logging(level: str = "INFO", json_format: bool = True) -> None:
    """Configure root logger.

    Args:
        level: Logging level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_format: If True, use structured JSON output; otherwise use plain text.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)

    if json_format:
        handler.setFormatter(_JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s")
        )

    root = logging.getLogger()
    root.setLevel(numeric_level)
    # Remove existing handlers to avoid duplicates when called multiple times
    root.handlers.clear()
    root.addHandler(handler)

    # Silence noisy third-party libraries
    for noisy in ("httpx", "httpcore", "telegram", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
