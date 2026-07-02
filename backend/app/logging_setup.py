"""Central logging configuration for the backend.

Every module logs through the standard ``logging`` module under the ``app.*``
namespace. ``configure_logging()`` attaches a rotating file handler (so the
log survives restarts and can be attached to bug reports) plus a console
handler, and captures uvicorn/FastAPI access and error logs into the same
file so one place tells the whole story of a request.

Environment overrides:
- ``LOG_LEVEL``: root level for the app loggers (default INFO; DEBUG adds
  per-request planner diagnostics such as the hydrant filter counters).
- ``LOG_FILE``: alternate log file path (default ``data/logs/backend.log``).
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

from app.config import BACKEND_LOG_FILE

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB per file
_BACKUP_COUNT = 5  # keep backend.log.1 ... backend.log.5

_configured = False


def configure_logging() -> Path:
    """Idempotently configure app-wide logging; returns the log file path."""
    global _configured
    log_file = Path(os.environ.get("LOG_FILE", str(BACKEND_LOG_FILE)))
    if _configured:
        return log_file
    log_file.parent.mkdir(parents=True, exist_ok=True)
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    formatter = logging.Formatter(_FORMAT)
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    app_logger = logging.getLogger("app")
    app_logger.setLevel(level)
    # Idempotence guard for reloads: never stack duplicate handlers.
    app_logger.handlers.clear()
    app_logger.addHandler(file_handler)
    app_logger.addHandler(console_handler)
    app_logger.propagate = False

    # Route uvicorn's error/access logs into the same file (keep their console
    # handlers untouched so the terminal still shows requests as before).
    # Attach only to the parent "uvicorn" logger: "uvicorn.error"/"uvicorn.access"
    # propagate to it, so adding the handler to the children too would write
    # every server line twice.
    logging.getLogger("uvicorn").addHandler(file_handler)

    _configured = True
    app_logger.info("Logging configured: level=%s file=%s", level_name, log_file)
    return log_file
