"""
RAAH Structured Observability — Logging
=======================================

Provides standard structured JSON logging with correlation IDs and execution metadata.
Conforms to cloud-native log aggregation standards (Elasticsearch, Loki, CloudWatch).
"""

import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from api.observability.middleware import get_request_id


class StructuredJsonFormatter(logging.Formatter):
    """
    Formats log records as compact, single-line JSON objects with ISO 8601 timestamps,
    correlation IDs, logger names, severity levels, and exception tracebacks.
    """

    def __init__(self, service_name: str = "raah-dispatch"):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        # Standard payload
        timestamp_str = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        
        payload: Dict[str, Any] = {
            "timestamp": timestamp_str,
            "level": record.levelname,
            "service": self.service_name,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Correlation / Request ID from active context
        req_id = get_request_id()
        if req_id:
            payload["correlation_id"] = req_id
            payload["request_id"] = req_id

        # Location details
        payload["source"] = {
            "file": record.filename,
            "line": record.lineno,
            "function": record.funcName,
        }

        # Extra metadata attached via extra={...}
        extra_fields = {}
        for key, val in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
                "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
                "created", "msecs", "relativeCreated", "thread", "threadName",
                "processName", "process", "message"
            } and not key.startswith("_"):
                extra_fields[key] = val
        if extra_fields:
            payload["extra"] = extra_fields

        # Exception formatting
        if record.exc_info:
            payload["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else "UnknownException",
                "message": str(record.exc_info[1]),
                "stacktrace": traceback.format_exception(*record.exc_info),
            }

        return json.dumps(payload, ensure_ascii=False)


def setup_structured_logging(
    log_level: str = "INFO",
    log_format: str = "json",
    service_name: str = "raah-dispatch",
) -> None:
    """
    Configure root and application loggers to output structured JSON or standard text.
    Additive and non-destructive to existing library loggers.
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Avoid duplicate handlers
    has_stream_handler = False
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            has_stream_handler = True
            if log_format.lower() == "json":
                handler.setFormatter(StructuredJsonFormatter(service_name=service_name))
            else:
                handler.setFormatter(
                    logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s")
                )
            break

    if not has_stream_handler:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(numeric_level)
        if log_format.lower() == "json":
            handler.setFormatter(StructuredJsonFormatter(service_name=service_name))
        else:
            handler.setFormatter(
                logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s")
            )
        root_logger.addHandler(handler)
