"""
Change 3: Structured logging shipped to a central syslog sink.
============================================================
Uses Python's logging module with:
  - JSON formatter for structured, machine-parseable log events
  - SocketHandler to ship logs from remote probe nodes to primary VPS
  - SysLogHandler for rsyslog integration (UDP port 514)

TECHNICAL EXPLANATION (for interviews):
  Traditional logging writes plaintext lines — hard to query at scale.
  Structured logging emits JSON objects: every field is queryable.

  Example log event:
    {
      "ts": "2026-01-15T10:23:45.123Z",
      "level": "WARNING",
      "node": "mumbai-01",
      "logger": "netpulse.anomaly",
      "msg": "RTT spike detected",
      "host": "8.8.8.8",
      "rtt_ms": 145.3,
      "sigma": 4.2
    }

  Log shipping: Python's logging.handlers.SocketHandler sends log
  records as pickled objects over TCP to a remote logging server.
  On the receiving end, a socketserver.TCPServer unpickles and
  re-emits them into the primary node's logging pipeline.

  rsyslog integration: SysLogHandler sends RFC 5424 syslog messages
  over UDP to rsyslog on the primary VPS, which can then forward to
  Elasticsearch, Loki, or any log aggregator.
"""

import logging
import logging.handlers
import json
import socket
import sys
from datetime import datetime, timezone

from app.core.config import settings


class JSONFormatter(logging.Formatter):
    """
    Formats log records as single-line JSON objects.
    Every field is explicitly typed — no string parsing needed downstream.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "node": settings.NODE_ID,
            "region": settings.NODE_REGION,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Include any extra fields passed via logger.info("msg", extra={...})
        for key, val in record.__dict__.items():
            if key not in (
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
                "taskName",
            ):
                try:
                    json.dumps(val)   # only include JSON-serialisable extras
                    log_obj[key] = val
                except (TypeError, ValueError):
                    log_obj[key] = str(val)

        if record.exc_info:
            log_obj["exc"] = self.formatException(record.exc_info)

        return json.dumps(log_obj, default=str)


def setup_logging() -> None:
    """
    Configure the root logger with:
      1. JSON stdout handler (always)
      2. TCP SocketHandler to primary node (if SYSLOG_HOST set)
      3. UDP SysLogHandler for rsyslog (if SYSLOG_HOST set)
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    # Remove default handlers
    root.handlers.clear()

    # ── Handler 1: JSON stdout ─────────────────────────────────────────────
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(JSONFormatter())
    root.addHandler(stdout_handler)

    # ── Handler 2 & 3: Remote log shipping ────────────────────────────────
    if settings.SYSLOG_HOST and settings.NODE_ROLE == "probe":
        # TCP SocketHandler — ships structured logs to primary node
        # Primary runs a TCPServer (see log_receiver.py) to ingest these
        try:
            socket_handler = logging.handlers.SocketHandler(
                settings.SYSLOG_HOST,
                logging.handlers.DEFAULT_TCP_LOGGING_PORT,  # 9020
            )
            socket_handler.setFormatter(JSONFormatter())
            socket_handler.setLevel(logging.WARNING)   # Only WARNING+ over network
            root.addHandler(socket_handler)
            logging.getLogger("netpulse").info(
                f"Log shipping enabled → {settings.SYSLOG_HOST}:9020"
            )
        except Exception as e:
            logging.getLogger("netpulse").warning(f"Log shipping setup failed: {e}")

        # UDP SysLogHandler → rsyslog
        try:
            syslog_handler = logging.handlers.SysLogHandler(
                address=(settings.SYSLOG_HOST, settings.SYSLOG_PORT),
                facility=logging.handlers.SysLogHandler.LOG_LOCAL0,
            )
            syslog_handler.setFormatter(JSONFormatter())
            syslog_handler.setLevel(logging.ERROR)   # Only ERROR+ to syslog
            root.addHandler(syslog_handler)
        except Exception as e:
            logging.getLogger("netpulse").warning(f"Syslog handler setup failed: {e}")

    logging.getLogger("netpulse").info(
        f"Logging initialised",
        extra={"node_role": settings.NODE_ROLE, "log_level": settings.LOG_LEVEL}
    )
