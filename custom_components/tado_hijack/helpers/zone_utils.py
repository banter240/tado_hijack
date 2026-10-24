"""Zone utility functions for Tado Hijack."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..const import ZONE_TYPE_AIR_CONDITIONING, ZONE_TYPE_HEATING

if TYPE_CHECKING:
    from ..coordinator import TadoDataUpdateCoordinator

# Cloud climates for these zones always offer auto. Hot water is a water heater.
# The cached week is not part of this: resume paints it when it is already loaded.
_CLOUD_CLIMATE_TYPES = frozenset({ZONE_TYPE_HEATING, ZONE_TYPE_AIR_CONDITIONING})


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


def cloud_climate_can_follow_schedule(
    coordinator: TadoDataUpdateCoordinator, zone_id: int
) -> bool:
    """True when this zone's cloud climate can resume onto its plan.

    Heating and air conditioning can. The cached week is not required.
    """
    zone = coordinator.zones_meta.get(zone_id)
    return False if zone is None else get_zone_type(zone) in _CLOUD_CLIMATE_TYPES


def zone_follows_cloud_schedule(
    coordinator: TadoDataUpdateCoordinator, zone_id: int
) -> bool:
    """True when no manual overlay is set. Optimistic state wins.

    A missing cloud state counts as following the plan.
    """
    overlay = coordinator.optimistic.get_zone_overlay(zone_id)
    if overlay is not None:
        return not overlay
    data = coordinator.data
    states = getattr(data, "zone_states", None) if data is not None else None
    state = states.get(str(zone_id)) if isinstance(states, dict) else None
    return not bool(state and getattr(state, "overlay_active", False))


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


def zone_id_for_serial(zones_meta: Mapping[int, Any], serial: str) -> int | None:
    """Zone that owns this TRV serial, or None."""
    return next(
        (
            int(zone_id)
            for zone_id in zones_meta
            if serial in trv_serials(zones_meta, int(zone_id))
        ),
        None,
    )


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
