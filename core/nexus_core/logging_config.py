"""NEXUS Structured JSON Logging with Rotating File Persistence & Secret Redaction."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
from typing import Any

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-+/=]+", re.IGNORECASE),
    re.compile(r"\b(sk-[A-Za-z0-9_\-]{8,})\b"),
    re.compile(r"\b(AIza[A-Za-z0-9_\-]{12,})\b"),
    re.compile(r"\b(nxs_[A-Za-z0-9_\-]{12,})\b"),
    re.compile(
        r'("?(?:api_?key|x-api-key|x-goog-api-key|token|secret|authorization|credential)"?\s*[:=]\s*"?(?:Bearer\s+)?)([^"\s,}]+)',
        re.IGNORECASE,
    ),
)


def redact_secrets(text: str) -> str:
    """Masks bearer tokens, API keys, and credential substrings before logging."""
    masked = text
    masked = _SECRET_PATTERNS[0].sub(r"\1[REDACTED]", masked)
    masked = _SECRET_PATTERNS[1].sub("[REDACTED_KEY]", masked)
    masked = _SECRET_PATTERNS[2].sub("[REDACTED_KEY]", masked)
    masked = _SECRET_PATTERNS[3].sub("[REDACTED_TOKEN]", masked)
    masked = _SECRET_PATTERNS[4].sub(r"\1[REDACTED]", masked)
    return masked


def _scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, dict):
        scrubbed: dict[str, Any] = {}
        for k, v in value.items():
            lowered = str(k).lower()
            if any(
                s in lowered
                for s in ("apikey", "api_key", "x-api-key", "x-goog-api-key", "authorization", "secret")
            ) or lowered == "token":
                scrubbed[str(k)] = "[REDACTED]"
            else:
                scrubbed[str(k)] = _scrub_value(v)
        return scrubbed
    if isinstance(value, list):
        return [_scrub_value(item) for item in value]
    return value


class SecretRedactionFilter(logging.Filter):
    """Logging filter that scrubs sensitive credentials from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            try:
                rendered = record.getMessage()
                record.msg = redact_secrets(rendered)
                record.args = None
            except Exception:
                if isinstance(record.args, dict):
                    record.args = _scrub_value(record.args)
                elif isinstance(record.args, tuple):
                    record.args = tuple(_scrub_value(a) for a in record.args)
        elif isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        return True


class StructuredJsonFormatter(logging.Formatter):
    """Formats log records as single-line structured JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_secrets(record.getMessage()),
        }
        event = getattr(record, "event", None)
        if event:
            payload["event"] = event
        correlation_id = getattr(record, "correlation_id", None)
        if correlation_id:
            payload["correlationId"] = correlation_id
        extra_data = getattr(record, "extra_data", None)
        if isinstance(extra_data, dict):
            payload["data"] = _scrub_value(extra_data)
        if record.exc_info:
            payload["exception"] = redact_secrets(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=True)


def configure_structured_logging(
    level: str = "INFO",
    logger_name: str = "nexus_core",
    log_file: Path | None = None,
) -> logging.Logger:
    """Configures structured JSON logging to stderr/stdout and optional rotating log file."""
    logger = logging.getLogger(logger_name)
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)
    logger.propagate = False

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredJsonFormatter())
        handler.addFilter(SecretRedactionFilter())
        logger.addHandler(handler)
    else:
        for handler in logger.handlers:
            handler.setFormatter(StructuredJsonFormatter())
            if not any(isinstance(f, SecretRedactionFilter) for f in handler.filters):
                handler.addFilter(SecretRedactionFilter())

    if log_file is not None:
        resolved_log = Path(log_file).expanduser().resolve()
        has_file_handler = any(
            isinstance(h, RotatingFileHandler)
            and Path(h.baseFilename).resolve() == resolved_log
            for h in logger.handlers
        )
        if not has_file_handler:
            resolved_log.parent.mkdir(parents=True, exist_ok=True)
            fh = RotatingFileHandler(
                filename=str(resolved_log),
                maxBytes=2 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
            fh.setFormatter(StructuredJsonFormatter())
            fh.addFilter(SecretRedactionFilter())
            logger.addHandler(fh)

    return logger
