"""Zone utility functions for Tado Hijack."""

from __future__ import annotations

from typing import Any

from ..const import ZONE_TYPE_HEATING


def get_zone_type(
    zone: Any | None, default: str | None = ZONE_TYPE_HEATING
) -> str | None:
    """Safely extract zone type with consistent fallback.

    Args:
        zone: Zone object (can be None)
        default: Default value if zone is None or has no type (default: ZONE_TYPE_HEATING)

    Returns:
        Zone type string or default value

    """
    return default if zone is None else getattr(zone, "type", default)
