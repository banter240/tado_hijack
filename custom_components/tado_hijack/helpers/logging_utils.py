"""Logging utilities for Tado Hijack."""

from __future__ import annotations

import contextvars
import json
import logging
import re
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

try:
    INTEGRATION_VERSION = json.loads(
        (Path(__file__).parent.parent / "manifest.json").read_text()
    ).get("version", "unknown")
except Exception:
    INTEGRATION_VERSION = "unknown"

# Query values that must not survive into a log line.
_URL_PARAM_PATTERNS = [
    re.compile(
        r"(?:user_code|access_token|refresh_token|id_token|proxy_token|client_secret|"
        r"device_code|password|username|email|authorization)=[^& ]+",
        re.IGNORECASE,
    ),
]

_JSON_SECRET_KEYS = (
    "user_code|password|access_token|refresh_token|id_token|proxy_token|"
    "client_secret|device_code|authorization|username|email|serialNo|shortSerialNo"
)

# Token values currently in scope. Tracebacks are formatted later, so the value
# itself has to be recognizable without a field name.
_MIN_SECRET_LENGTH = 8
_log_secrets: contextvars.ContextVar[tuple[str, ...]] = contextvars.ContextVar(
    "tado_hijack_log_secrets",
    default=(),
)


@contextmanager
def log_secrets(*secrets: str | None) -> Iterator[None]:
    """Hide concrete token values in logs emitted inside the block."""
    current = _log_secrets.get()
    extra = tuple(
        secret
        for secret in secrets
        if secret and len(secret) >= _MIN_SECRET_LENGTH and secret not in current
    )
    if not extra:
        yield
        return
    token = _log_secrets.set(current + extra)
    try:
        yield
    finally:
        _log_secrets.reset(token)


def redact(data: Any) -> Any:
    """Redact secrets in a string. Other types pass through unchanged."""
    if isinstance(data, Exception):
        return redact(str(data))

    if not isinstance(data, str):
        return data

    for secret in _log_secrets.get():
        if secret in data:
            data = data.replace(secret, "REDACTED")

    for pattern in _URL_PARAM_PATTERNS:
        data = pattern.sub(lambda m: m.group(0).split("=")[0] + "=REDACTED", data)

    # Home IDs in URLs, error text, and JSON ("homes/12345", "home 12345", homeId)
    data = re.sub(r"homes?/\d+", "homes/REDACTED", data, flags=re.IGNORECASE)
    data = re.sub(r"\bhome\s+\d{4,}", "home REDACTED", data, flags=re.IGNORECASE)
    data = re.sub(
        r'(["\'])(homeId|home_id)\1\s*[:=]\s*["\']?\d+["\']?',
        r"\1\2\1: REDACTED",
        data,
        flags=re.IGNORECASE,
    )
    data = re.sub(
        r"\b(homeId|home_id)\b\s*[:=]\s*[\"']?\d+[\"']?",
        r"\1=REDACTED",
        data,
        flags=re.IGNORECASE,
    )

    data = re.sub(r"[\w.+-]+@[\w.-]+\.\w+", "REDACTED@REDACTED", data)
    data = re.sub(r"Bearer\s+\S+", "Bearer REDACTED", data, flags=re.IGNORECASE)

    def _redact_serial(match: re.Match[str]) -> str:
        return "_REDACTED" if match.group(0).startswith("_") else "REDACTED"

    # Tado serials are 2-3 letters plus 8-12 more characters. Zone ids stay.
    data = re.sub(
        r"(?:\b|_|^)[A-Z]{2,3}[A-Z0-9]{8,12}(?=\b|_|$)",
        _redact_serial,
        data,
    )

    data = re.sub(
        r'(["\'])(' + _JSON_SECRET_KEYS + r')\1\s*[:=]\s*(["\'])(.*?)\3',
        r"\1\2\1: \3REDACTED\3",
        data,
        flags=re.IGNORECASE,
    )

    return data


_VERSION_PREFIX_ENABLED: bool = True
_VERSION_PREFIX = f"[v{INTEGRATION_VERSION}] "


class TadoVersionFilter(logging.Filter):
    """Prepend integration version to every log message when enabled."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Prepend version tag to the log message."""
        if _VERSION_PREFIX_ENABLED and isinstance(record.msg, str):
            record.msg = _VERSION_PREFIX + record.msg
        return True


def _redact_record(record: logging.LogRecord) -> None:
    """Redact the rendered line and any traceback attached to it."""
    if record.args:
        try:
            rendered = record.getMessage()
        except Exception:
            rendered = str(record.msg)
        record.msg = redact(rendered)
        record.args = ()
    elif isinstance(record.msg, str):
        record.msg = redact(record.msg)

    if record.exc_info and not record.exc_text:
        record.exc_text = redact("".join(traceback.format_exception(*record.exc_info)))
        record.exc_info = None
    elif isinstance(record.exc_text, str):
        record.exc_text = redact(record.exc_text)

    if isinstance(record.stack_info, str):
        record.stack_info = redact(record.stack_info)


class TadoRedactionFilter(logging.Filter):
    """Filter to redact sensitive information from logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact the rendered message, its arguments, and the traceback."""
        _redact_record(record)
        return True


# Global state to track desired log level for newly created loggers
_CURRENT_INTEGRATION_LOG_LEVEL: int = logging.INFO


def get_redacted_logger(name: str) -> logging.Logger:
    """Get a logger with version and redaction filters attached."""
    logger = logging.getLogger(name)
    existing = {type(f) for f in logger.filters}
    if TadoVersionFilter not in existing:
        logger.addFilter(TadoVersionFilter())
    if TadoRedactionFilter not in existing:
        logger.addFilter(TadoRedactionFilter())
    if name.startswith("custom_components.tado_hijack"):
        logger.setLevel(_CURRENT_INTEGRATION_LOG_LEVEL)
    return logger


_LOGGER = get_redacted_logger(__name__)


def set_version_prefix_enabled(enabled: bool) -> None:
    """Enable or disable version prefix injection in log messages."""
    global _VERSION_PREFIX_ENABLED
    _VERSION_PREFIX_ENABLED = enabled


def set_redacted_log_level(level: str) -> None:
    """Synchronize log levels for all Tado-related loggers."""
    global _CURRENT_INTEGRATION_LOG_LEVEL
    log_level = getattr(logging, level.upper(), logging.INFO)
    _CURRENT_INTEGRATION_LOG_LEVEL = log_level

    # Update root and all existing sub-loggers
    logging.getLogger("custom_components.tado_hijack").setLevel(log_level)
    logging.getLogger("tadoasync").setLevel(log_level)

    for name in logging.root.manager.loggerDict:
        if name.startswith(("custom_components.tado_hijack", "tadoasync")):
            logging.getLogger(name).setLevel(log_level)

    _LOGGER.info("Tado Hijack log level synchronized to: %s", level.upper())
    if log_level == logging.DEBUG:
        _LOGGER.debug("Debug logging is now ACTIVE for Tado Hijack")
