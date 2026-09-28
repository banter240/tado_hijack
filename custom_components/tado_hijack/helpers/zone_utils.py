"""Zone utility functions for Tado Hijack."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..const import ZONE_TYPE_HEATING


@dataclass(frozen=True)
class TadoUnifiedZone:
    """Unified zone representation across all generations."""

    id: int
    name: str
    type: str
    raw_zone: Any


def get_zone_type(
    zone: Any | None, default: str | None = ZONE_TYPE_HEATING
) -> str | None:
    """Safely extract zone type with consistent fallback."""
    return default if zone is None else getattr(zone, "type", default)


def trv_serials(zones_meta: Mapping[int, Any], zone_id: int | None = None) -> list[str]:
    """TRV serials for one zone, or for every zone when zone_id is omitted."""
    zones = (
        [zones_meta.get(zone_id)] if zone_id is not None else list(zones_meta.values())
    )
    serials: list[str] = []
    for zone in zones:
        if zone is None or not getattr(zone, "devices", None):
            continue
        for dev in zone.devices:
            serial = getattr(dev, "serial_no", None)
            if serial and (text := str(serial)) not in serials:
                serials.append(text)
    return serials


def unify_zone(zone: Any) -> TadoUnifiedZone:
    """Convert a generation-specific zone object into a unified representation."""
    # Tado X (HopsRoomSnapshot)
    if hasattr(zone, "room_id"):
        return TadoUnifiedZone(
            id=int(zone.room_id),
            name=str(zone.room_name),
            type=ZONE_TYPE_HEATING,  # Tado X rooms are currently treated as HEATING zones
            raw_zone=zone,
        )

    # v3 Classic (Zone)
    return TadoUnifiedZone(
        id=int(zone.id),
        name=str(zone.name),
        type=str(getattr(zone, "type", ZONE_TYPE_HEATING)),
        raw_zone=zone,
    )
