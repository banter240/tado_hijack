"""Zone utility functions for Tado Hijack."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.util import dt as dt_util

from ..const import (
    POWER_OFF,
    TEMP_TOLERANCE,
    ZONE_SAMPLE_MAX_AGE_S,
    ZONE_TYPE_AIR_CONDITIONING,
    ZONE_TYPE_HEATING,
    ZONE_TYPE_HOT_WATER,
)
from .parsers import zone_setting_power_temp

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


def same_setpoint(
    power: str,
    temperature: float | None,
    other_power: str,
    other_temperature: float | None,
) -> bool:
    """True when both sides are off, or both are the same heat target."""
    if POWER_OFF in (power, other_power):
        return power == other_power
    if temperature is None or other_temperature is None:
        return False
    return abs(float(temperature) - float(other_temperature)) < TEMP_TOLERANCE


def local_heating_zone(coordinator: TadoDataUpdateCoordinator, zone_id: int) -> bool:
    """Heating zone with a metadata row. Hot water has no local actuator."""
    if coordinator._is_tadox_hot_water_zone(zone_id):
        return False
    zone = coordinator.zones_meta.get(zone_id)
    if zone is None or get_zone_type(zone, None) == ZONE_TYPE_HOT_WATER:
        return False
    return get_zone_type(zone) == ZONE_TYPE_HEATING


def known_zone_power_temp(
    coordinator: TadoDataUpdateCoordinator, zone_id: int
) -> tuple[str, float | None] | None:
    """Power and target already stored for a manual zone. Optimistic power wins."""
    power = coordinator.optimistic.get_zone_power(zone_id)
    temperature = coordinator.optimistic.get_zone_temperature(zone_id)
    if power is None and coordinator.data is not None:
        return zone_setting_power_temp(coordinator.data.zone_states.get(str(zone_id)))
    if not isinstance(power, str):
        return None
    if temperature is not None and not isinstance(temperature, int | float):
        temperature = None
    return power, float(temperature) if temperature is not None else None


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


def cloud_reading_is_live(sample: Any, *, now: datetime | None = None) -> bool:
    """True when this cloud sample can still stand in for the room.

    Age is the sample's own timestamp. A slow poll does not age a fresh
    stamp. No stamp means the age is unknown, so the sample stays.
    """
    stamp = getattr(sample, "timestamp", None) if sample is not None else None
    if not stamp:
        return True
    parsed = (
        stamp if isinstance(stamp, datetime) else dt_util.parse_datetime(str(stamp))
    )
    if parsed is None:
        return True
    moment = now or dt_util.utcnow()
    parsed_utc = dt_util.as_utc(parsed)
    age_s = float((moment - parsed_utc).total_seconds())
    return age_s <= ZONE_SAMPLE_MAX_AGE_S


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
