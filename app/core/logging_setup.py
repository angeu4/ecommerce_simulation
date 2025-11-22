import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any

from app.core.constants import (FILE_BASED_LOG_MAX_COUNT,
                                FILE_BASED_LOG_MAX_SIZE, UTF_ENCODING)

# Default location (Docker container)
DEFAULT_LOG_DIR = "/app/logs"

# If pytest explicitly sets PYTEST_RUNNING, redirect logs to /tmp
if os.environ.get("PYTEST_RUNNING") == "1":
    LOG_DIR = os.path.join(tempfile.gettempdir(), "ecommerce_simulation_logs")
else:
    # Try the default directory, but fall back to /tmp if it's read-only
    try:
        os.makedirs(DEFAULT_LOG_DIR, exist_ok=True)
        LOG_DIR = DEFAULT_LOG_DIR
    except OSError:
        # Read-only filesystem → fallback
        LOG_DIR = os.path.join(tempfile.gettempdir(), "ecommerce_simulation_logs")

# ensuring the final log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = f"{LOG_DIR}/app.log"


class JSONFormatter(logging.Formatter):
    def format(self, record: Any) -> str:
        """
        Formats a log record as a JSON string.

        The JSON string contains the following fields by default:
        - timestamp: ISO 8601 timestamp in UTC timezone
        - level: Log level (e.g. DEBUG, INFO, etc.)
        - logger: Name of the logger
        - message: Log message

        Additionally, the following fields are included if they are present
        in the log record:
        - request_id: Request ID if included in the LogRecord
        - Any additional structured data from extra={}

        The JSON string is returned as a str.
        """
        
        log_record = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Attach request_id if included in the LogRecord
        if hasattr(record, "request_id"):
            log_record["request_id"] = record.request_id

        # Attach additional structured data from extra={}
        for key, value in record.__dict__.items():
            if key not in log_record and key not in (
                "args", "msg", "message", "exc_info", "exc_text", "stack_info",
                "levelname", "levelno", "pathname", "filename", "module",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process",
            ):
                log_record[key] = value

        return json.dumps(log_record)


# ----------------------------
# FILE HANDLER (JSON STRUCTURED)
# ----------------------------
file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=FILE_BASED_LOG_MAX_SIZE,
    backupCount=FILE_BASED_LOG_MAX_COUNT,
    encoding=UTF_ENCODING
)
file_handler.setFormatter(JSONFormatter())


# ----------------------------
# CONSOLE HANDLER (HUMAN-FRIENDLY)
# ----------------------------
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter(
    "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
))


# ----------------------------
# GLOBAL LOGGING CONFIG
# ----------------------------
logging.basicConfig(
    level=logging.INFO,
    handlers=[console_handler, file_handler],
)


# ----------------------------
# Uvicorn Log Integration
# ----------------------------
for uvicorn_logger in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    logger = logging.getLogger(uvicorn_logger)
    logger.handlers = [console_handler, file_handler]
    logger.propagate = False


# ----------------------------
# Logger Factory
# ----------------------------
def get_logger(name: str) -> logging.Logger:
    """
    Return a logger instance based on the given name.

    Args:
        name: The name of the logger.

    Returns:
        A logger instance.
    """
    
    return logging.getLogger(name)
