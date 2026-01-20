"""Monkey-patch utilities for Tado Hijack."""

from __future__ import annotations

import sys
from typing import Any

from ..const import TADO_VERSION_PATCH
from .logging_utils import get_redacted_logger
from .tado_request_handler import TadoRequestHandler

_LOGGER = get_redacted_logger(__name__)

_HANDLER = TadoRequestHandler()


def get_handler() -> TadoRequestHandler:
    """Get the global Tado request handler."""
    return _HANDLER


def apply_patch() -> None:
    """Apply global library patches."""
    _LOGGER.debug("Applying tadoasync patches")

    _patch_version()
    _patch_zone_state()


def _patch_version() -> None:
    try:
        import tadoasync.tadoasync

        tadoasync.tadoasync.VERSION = TADO_VERSION_PATCH
        if "tadoasync" in sys.modules:
            setattr(sys.modules["tadoasync"], "VERSION", TADO_VERSION_PATCH)
    except ImportError as e:
        _LOGGER.error("Failed to patch tadoasync version: %s", e)


def _patch_zone_state() -> None:
    """Fix ZoneState deserialization (nextTimeBlock null issue)."""
    try:
        import tadoasync.models

        def robust_pre_deserialize(cls: Any, d: dict[str, Any]) -> dict[str, Any]:
            if not d.get("sensorDataPoints"):
                d["sensorDataPoints"] = None
            if d.get("nextTimeBlock") is None:
                d["nextTimeBlock"] = {}
            return d

        setattr(
            tadoasync.models.ZoneState,
            "__pre_deserialize__",
            classmethod(robust_pre_deserialize),
        )
    except (ImportError, AttributeError) as e:
        _LOGGER.error("Failed to patch ZoneState model: %s", e)
