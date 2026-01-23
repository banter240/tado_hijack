"""Monkey-patch utilities for Tado Hijack."""

from __future__ import annotations

import sys
from typing import Any


from ..const import TADO_VERSION_PATCH
from .logging_utils import get_redacted_logger
from .tado_request_handler import TadoRequestHandler

_LOGGER = get_redacted_logger(__name__)

_HANDLER = TadoRequestHandler()
_PATCHES_APPLIED = False


def get_handler() -> TadoRequestHandler:
    """Get the global Tado request handler."""
    return _HANDLER


def apply_patch() -> None:
    """Apply global library patches (idempotent - safe to call multiple times)."""
    global _PATCHES_APPLIED
    if _PATCHES_APPLIED:
        return

    try:
        import tadoasync

        tadoasync_version = getattr(tadoasync, "__version__", "unknown")
        _LOGGER.debug(
            "Applying tadoasync patches (tadoasync version: %s)", tadoasync_version
        )
    except ImportError:
        _LOGGER.warning("Failed to import tadoasync, skipping patches")
        return

    _patch_version()
    _patch_zone_state()
    _PATCHES_APPLIED = True


def _patch_version() -> None:
    """Patch tadoasync VERSION string for User-Agent compatibility."""
    try:
        import tadoasync.tadoasync

        # Check if VERSION attribute exists before patching
        if not hasattr(tadoasync.tadoasync, "VERSION"):
            _LOGGER.warning(
                "tadoasync.tadoasync.VERSION not found - library structure may have changed"
            )
            return

        tadoasync.tadoasync.VERSION = TADO_VERSION_PATCH
        _LOGGER.debug(
            "Successfully patched tadoasync.tadoasync.VERSION to %s", TADO_VERSION_PATCH
        )

        if "tadoasync" in sys.modules:
            setattr(sys.modules["tadoasync"], "VERSION", TADO_VERSION_PATCH)
    except ImportError as e:
        _LOGGER.warning("Failed to import tadoasync for version patch: %s", e)
    except Exception as e:
        _LOGGER.error("Unexpected error patching tadoasync version: %s", e)


def _patch_zone_state() -> None:
    """Fix ZoneState deserialization (nextTimeBlock null issue)."""
    try:
        import tadoasync.models

        # Check if ZoneState exists
        if not hasattr(tadoasync.models, "ZoneState"):
            _LOGGER.warning(
                "tadoasync.models.ZoneState not found - library structure may have changed"
            )
            return

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
        _LOGGER.debug("Successfully patched ZoneState.__pre_deserialize__")
    except ImportError as e:
        _LOGGER.warning("Failed to import tadoasync.models for ZoneState patch: %s", e)
    except AttributeError as e:
        _LOGGER.warning("ZoneState attribute not found, patch may not be needed: %s", e)
    except Exception as e:
        _LOGGER.error("Unexpected error patching ZoneState model: %s", e)
