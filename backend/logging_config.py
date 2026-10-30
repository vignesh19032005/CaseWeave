"""
Stage 17 — Structured logging. Separate from the audit trail (db.py's
AuditEvent, which answers "who did what to which case"). This is
operational logging: errors, latency, LLM provider-fallback events — the
stuff that tells you the system is unhealthy before a case is affected.
JSON-formatted so it's real-monitoring-stack-ready (Grafana/Loki or
equivalent) once that infra exists — alerting itself is still a Stage 17
follow-on once there's somewhere to send these logs.
"""
import json
import logging
import sys
import time
from pathlib import Path

LOG_PATH = Path(__file__).parent / "caseweave.jsonl"


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        return json.dumps(payload)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured, avoid duplicate handlers on reimport

    logger.setLevel(logging.INFO)

    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(JsonFormatter())
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(JsonFormatter())
    logger.addHandler(console_handler)

    return logger


def log_event(logger: logging.Logger, level: str, message: str, **fields):
    """Convenience: log_event(logger, 'warning', 'provider fallback used', provider='groq', stage='observe')"""
    getattr(logger, level)(message, extra={"extra_fields": fields})
