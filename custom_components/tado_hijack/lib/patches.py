"""Patches for tadoasync compatibility - formatted for upstream contribution.

This module contains runtime patches for tadoasync library bugs and compatibility issues.
These patches are designed to be eventually contributed upstream to tadoasync.

Patches applied:
1. ZoneState deserialization fixes (null nextTimeBlock, hot water activity rescue)
2. VERSION string update for User-Agent compatibility
"""

from __future__ import annotations

import sys
from datetime import datetime
from typing import Any

from ..const import TADO_VERSION_PATCH
from ..helpers.logging_utils import get_redacted_logger
from ..helpers.tado_request_handler import TadoRequestHandler

_LOGGER = get_redacted_logger(__name__)

_HANDLER = TadoRequestHandler()
_PATCHES_APPLIED = False


def get_handler() -> TadoRequestHandler:
    """Get the global Tado request handler."""
    return _HANDLER


def apply_patches() -> None:
    """Apply global library patches (idempotent - safe to call multiple times).

    This function patches tadoasync to fix known issues:
    - ZoneState deserialization for null nextTimeBlock
    - Hot water activity data rescue
    - VERSION string for User-Agent
    """
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

    patch_zone_state_deserialization()
    patch_version_string()
    _PATCHES_APPLIED = True
    _LOGGER.info("tadoasync patches applied successfully")


def patch_zone_state_deserialization() -> None:
    """Fix ZoneState deserialization issues.

    Addresses two issues:
    1. Null nextTimeBlock handling - API sometimes returns null instead of object
    2. Hot water activity data rescue - activityDataPoints.hotWaterInUse gets dropped

    This patch should be contributed to tadoasync upstream.

    Implementation:
        Adds a __pre_deserialize__ classmethod to ZoneState that:
        - Ensures nextTimeBlock is always a dict (convert null to {})
        - Rescues hot water activity into heatingPower for later access
        - Maintains backward compatibility with existing code
    """
    try:
        import tadoasync.models

        if not hasattr(tadoasync.models, "ZoneState"):
            _LOGGER.warning(
                "tadoasync.models.ZoneState not found - library structure may have changed"
            )
            return

        original_pre_deserialize = getattr(
            tadoasync.models.ZoneState, "__pre_deserialize__", None
        )

        def patched_pre_deserialize(cls: Any, d: dict[str, Any]) -> dict[str, Any]:
            """Pre-process ZoneState data before deserialization.

            Args:
                cls: The class being deserialized
                d: Raw API response data

            Returns:
                Processed data ready for deserialization

            """
            # Call original if exists (chain patches)
            if original_pre_deserialize:
                d = original_pre_deserialize(d)

            # Fix 1: Ensure sensorDataPoints is never None
            if not d.get("sensorDataPoints"):
                d["sensorDataPoints"] = None

            # Fix 2: Convert null nextTimeBlock to empty dict
            # API sometimes returns null which breaks deserialization
            if d.get("nextTimeBlock") is None:
                d["nextTimeBlock"] = {}

            # Fix 3: Rescue hot water activity before it gets dropped
            # The strict dataclass drops activityDataPoints but we need hotWaterInUse
            if activity := d.get("activityDataPoints"):
                if (
                    "hotWaterInUse" in activity
                    and isinstance(activity["hotWaterInUse"], dict)
                    and "value" in activity["hotWaterInUse"]
                ):
                    hw_val = activity["hotWaterInUse"]["value"]
                    # Inject into heatingPower for later access in sensors
                    activity["heatingPower"] = {
                        "type": "HOT_WATER_POWER",
                        "percentage": 100.0 if hw_val == "ON" else 0.0,
                        "timestamp": datetime.now().isoformat(),
                        "value": hw_val,
                    }

            return d

        setattr(
            tadoasync.models.ZoneState,
            "__pre_deserialize__",
            classmethod(patched_pre_deserialize),
        )
        _LOGGER.debug("Successfully patched ZoneState.__pre_deserialize__")

    except ImportError as e:
        _LOGGER.warning("Failed to import tadoasync.models for ZoneState patch: %s", e)
    except AttributeError as e:
        _LOGGER.warning("ZoneState attribute not found, patch may not be needed: %s", e)
    except Exception as e:
        _LOGGER.error("Unexpected error patching ZoneState model: %s", e)


def patch_version_string() -> None:
    """Update VERSION string for User-Agent compatibility.

    This patch updates tadoasync.VERSION to match the expected format.
    May not be needed if tadoasync updates version handling properly.

    Implementation:
        Sets tadoasync.tadoasync.VERSION to TADO_VERSION_PATCH value
        Updates sys.modules cache if already imported
    """
    try:
        import tadoasync.tadoasync

        if not hasattr(tadoasync.tadoasync, "VERSION"):
            _LOGGER.warning(
                "tadoasync.tadoasync.VERSION not found - library structure may have changed"
            )
            return

        tadoasync.tadoasync.VERSION = TADO_VERSION_PATCH
        _LOGGER.debug(
            "Successfully patched tadoasync.tadoasync.VERSION to %s", TADO_VERSION_PATCH
        )

        # Update sys.modules cache if already imported
        if "tadoasync" in sys.modules:
            setattr(sys.modules["tadoasync"], "VERSION", TADO_VERSION_PATCH)

    except ImportError as e:
        _LOGGER.warning("Failed to import tadoasync for version patch: %s", e)
    except Exception as e:
        _LOGGER.error("Unexpected error patching tadoasync version: %s", e)


# Alias for backward compatibility
apply_patch = apply_patches
