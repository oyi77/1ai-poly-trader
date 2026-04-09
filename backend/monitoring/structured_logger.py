"""Structured JSON logging with correlation ID support."""

import json
import logging
import uuid
from contextvars import ContextVar

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id_var.get(""),
        }
        # Add extra fields if present
        for key in ["strategy", "market_ticker", "event_type"]:
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def configure_logging(json_output: bool = False, level: str = "INFO") -> None:
    """Configure root logger with JSONFormatter if json_output=True, else standard format."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers
    root_logger.handlers.clear()

    handler = logging.StreamHandler()
    handler.setLevel(numeric_level)

    if json_output:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )

    root_logger.addHandler(handler)


def new_correlation_id() -> str:
    """Generate a new UUID, set it in the context var, and return it."""
    cid = str(uuid.uuid4())
    correlation_id_var.set(cid)
    return cid


def get_correlation_id() -> str:
    """Return the current correlation ID from the context var."""
    return correlation_id_var.get("")
