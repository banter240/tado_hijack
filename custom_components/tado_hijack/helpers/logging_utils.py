"""Logging utilities for Tado Hijack."""

from __future__ import annotations

import logging
import re
from typing import Any

from ..const import HOME_ID_MIN_DIGITS

# Common sensitive URL parameter patterns for Tado
_URL_PARAM_PATTERNS = [
    re.compile(r"user_code=[^& ]+", re.IGNORECASE),
    re.compile(r"access_token=[^& ]+", re.IGNORECASE),
    re.compile(r"refresh_token=[^& ]+", re.IGNORECASE),
    re.compile(r"password=[^& ]+", re.IGNORECASE),
    re.compile(r"username=[^& ]+", re.IGNORECASE),
    re.compile(r"email=[^& ]+", re.IGNORECASE),
]


def redact(data: Any) -> Any:
    """Redact sensitive information from the input string or object.

    Args:
        data: Input to redact (string, int, float, bool, None, etc.)

    Returns:
        - Strings: Redacted string
        - Other types: Passed through unchanged (int, float, bool, None, etc.)

    This preserves type information for logging format strings (%d, %f, etc.)

    """
    # Pass through non-string types unchanged
    # This allows logging with %d, %f, etc. to work correctly
    if isinstance(data, Exception):
        return redact(str(data))

    if not isinstance(data, str):
        return data

    # URL Parameters
    for p in _URL_PARAM_PATTERNS:
        data = p.sub(lambda m: m.group(0).split("=")[0] + "=REDACTED", data)

    # Home IDs in URLs
    data = re.sub(r"homes/\d+", "homes/REDACTED", data, flags=re.IGNORECASE)

    # Serial Numbers (Tado format: 2 letters + 10 digits)
    def partial_redact_sn(m: re.Match[str]) -> str:
        sn = m[0]
        prefix = ""
        if sn.startswith("_"):
            prefix = "_"
            sn = sn[1:]
        return f"{prefix}{sn[:2]}...{sn[-4:]}"

    data = re.sub(
        r"(?:\b|_|^)[A-Z]{2,3}[A-Z0-9]{8,12}(?=\b|_|$)", partial_redact_sn, data
    )

    # JSON Keys and Values
    json_keys = "user_code|password|access_token|refresh_token|username|email|serialNo|shortSerialNo"
    data = re.sub(
        r'(["\'])(' + json_keys + r')\1\s*[:=]\s*(["\'])(.*?)\3',
        r"\1\2\1: \3REDACTED\3",
        data,
        flags=re.IGNORECASE,
    )

    return data


_LOGGER = logging.getLogger(__name__)


class TadoRedactionFilter(logging.Filter):
    """Filter to redact sensitive information from logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact sensitive info in the log record message and arguments."""
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)

        if record.args and isinstance(record.args, tuple):
            # Check if format string contains home_id parameter
            # If so, redact the corresponding arg (convert int to "REDACTED")
            if isinstance(record.msg, str) and "home_id=" in record.msg:
                redacted_args = []
                for arg in record.args:
                    # home_id is typically an integer - redact it
                    if isinstance(arg, int) and len(str(arg)) >= HOME_ID_MIN_DIGITS:
                        redacted_args.append("REDACTED")
                    else:
                        redacted_args.append(redact(arg))
                record.args = tuple(redacted_args)
            else:
                # Redact all args normally (redact() handles type preservation)
                record.args = tuple(redact(arg) for arg in record.args)

        return True


# Global state to track desired log level for newly created loggers
_CURRENT_INTEGRATION_LOG_LEVEL: int = logging.INFO


def get_redacted_logger(name: str) -> logging.Logger:
    """Get a logger with the redaction filter attached."""
    logger = logging.getLogger(name)
    logger.addFilter(TadoRedactionFilter())
    if name.startswith("custom_components.tado_hijack"):
        logger.setLevel(_CURRENT_INTEGRATION_LOG_LEVEL)
    return logger


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
