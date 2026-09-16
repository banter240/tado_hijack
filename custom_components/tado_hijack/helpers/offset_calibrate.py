"""Auto-calibrate Tado device offset against a linked room thermostat."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..const import CAPABILITY_INSIDE_TEMP

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, State

    from ..coordinator import TadoDataUpdateCoordinator

OFFSET_MIN = -10.0
OFFSET_MAX = 10.0
OFFSET_STEP = 0.1
OFFSET_CAL_OFF = "off"
OFFSET_CAL_ON_RESET = "on_reset"
OFFSET_CAL_HOUR_STEPS: tuple[int, ...] = (3, 6, 9, 12, 15, 18, 21, 24)
OFFSET_CAL_INTERVALS: tuple[str, ...] = tuple(
    f"{hours}h" for hours in OFFSET_CAL_HOUR_STEPS
)
OFFSET_CAL_OPTIONS: tuple[str, ...] = (
    OFFSET_CAL_OFF,
    *OFFSET_CAL_INTERVALS,
    OFFSET_CAL_ON_RESET,
)


def daily_offset_cal_puts(coordinator: TadoDataUpdateCoordinator) -> int:
    """How many offset PUTs auto-cal will spend per quota day (0 if off)."""
    from ..const import (
        CONF_OFFSET_CAL_INTERVAL,
        CONF_ZONE_TEMP_ENTITIES,
        DEFAULT_OFFSET_CAL_INTERVAL,
    )

    if coordinator.config_entry is None:
        return 0
    option = str(
        coordinator.config_entry.data.get(
            CONF_OFFSET_CAL_INTERVAL, DEFAULT_OFFSET_CAL_INTERVAL
        )
    )
    hours = hours_from_midnight(option)
    if option == OFFSET_CAL_ON_RESET:
        fires = 1
    elif hours:
        fires = len(hours)
    else:
        return 0
    linked = coordinator.config_entry.data.get(CONF_ZONE_TEMP_ENTITIES) or {}
    if not isinstance(linked, dict) or not linked:
        return 0
    devices = sum(
        bool(linked.get(str(zone_id)))
        for _serial, zone_id in measuring_devices(coordinator)
    )
    return devices * fires


def hours_from_midnight(option: str) -> list[int] | None:
    """Local hours (from 00:00) for a 3h-grid interval, or None if not clock-based."""
    if option in {OFFSET_CAL_OFF, OFFSET_CAL_ON_RESET}:
        return None
    if not option.endswith("h"):
        return None
    try:
        step = int(option[:-1])
    except ValueError:
        return None
    return None if step not in OFFSET_CAL_HOUR_STEPS else list(range(0, 24, step))


def compute_device_offset(
    thermostat: float, tado_inside: float, current_offset: float
) -> float:
    """Offset so Tado's displayed temp matches the linked thermostat.

    Tado inside already includes the current offset, so the raw TRV is
    inside - current, and the new offset is thermostat - raw.
    """
    raw = tado_inside - current_offset
    desired = thermostat - raw
    clamped = max(OFFSET_MIN, min(OFFSET_MAX, desired))
    stepped = round(clamped / OFFSET_STEP) * OFFSET_STEP
    return round(stepped, 1)


def inside_from_zone_state(state: Any) -> float | None:
    """Tado's own zone measurement (not a linked HA thermostat)."""
    if not state:
        return None
    sdp = getattr(state, "sensor_data_points", None)
    if not sdp:
        return None
    inside = getattr(sdp, "inside_temperature", None)
    if inside is None:
        return None
    val = getattr(inside, "celsius", None)
    if val is None:
        val = getattr(inside, "value", None)
    return float(val) if val is not None else None


def read_entity_temperature(hass: HomeAssistant, entity_id: str) -> float | None:
    """Read current_temperature or the state from a climate/sensor entity."""
    state: State | None = hass.states.get(entity_id)
    if state is None or state.state in ("unavailable", "unknown"):
        return None
    raw = state.attributes.get("current_temperature")
    if raw is None:
        raw = state.state
    try:
        return float(raw)
    except TypeError, ValueError:
        return None


def current_device_offset(
    coordinator: TadoDataUpdateCoordinator, serial: str
) -> float | None:
    """Optimistic offset, then v3 cache, then Tado X device snapshot."""
    optimistic = coordinator.optimistic.get_offset(serial)
    if optimistic is not None:
        return float(optimistic)
    cached = coordinator.data_manager.offsets_cache.get(serial)
    if cached is not None:
        celsius = getattr(cached, "celsius", None)
        if celsius is not None:
            return float(celsius)
        if isinstance(cached, int | float):
            return float(cached)
    device = coordinator.devices_meta.get(serial)
    if device is not None:
        value = getattr(device, "temperature_offset", None)
        if value is not None:
            return float(value)
    return None


def measuring_devices(
    coordinator: TadoDataUpdateCoordinator,
) -> list[tuple[str, int]]:
    """Serial + zone for devices that expose a temperature offset."""
    from .discovery import yield_devices

    found: list[tuple[str, int]] = []
    for device, zone_id in yield_devices(
        coordinator, capability=CAPABILITY_INSIDE_TEMP
    ):
        if serial := getattr(device, "serial_no", None):
            found.append((str(serial), int(zone_id)))
    return found
