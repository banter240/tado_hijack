"""Auto-calibrate Tado device offset against a linked room thermostat."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..const import (
    CAPABILITY_INSIDE_TEMP,
    ZONE_TYPE_AIR_CONDITIONING,
    ZONE_TYPE_HEATING,
)
from .logging_utils import get_redacted_logger
from .zone_utils import cloud_reading_is_live

_LOGGER = get_redacted_logger(__name__)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, State

    from ..coordinator import TadoDataUpdateCoordinator

OFFSET_MIN = -10.0
OFFSET_MAX = 10.0
OFFSET_STEP = 0.1
OFFSET_CAL_OFF = "off"
OFFSET_CAL_ON_RESET = "on_reset"
OFFSET_CAL_THRESHOLD = "threshold"
OFFSET_CAL_INHERIT = "inherit"
OFFSET_CAL_HOUR_STEPS: tuple[int, ...] = (3, 6, 9, 12, 15, 18, 21, 24)
OFFSET_CAL_INTERVALS: tuple[str, ...] = tuple(
    f"{hours}h" for hours in OFFSET_CAL_HOUR_STEPS
)
OFFSET_CAL_OPTIONS: tuple[str, ...] = (
    OFFSET_CAL_OFF,
    *OFFSET_CAL_INTERVALS,
    OFFSET_CAL_ON_RESET,
    OFFSET_CAL_THRESHOLD,
)


# threshold writes only when a linked sensor moves far enough. One PUT is the
# daily budget guess for that device. The throttle floor covers a noisy day.
_THRESHOLD_DAILY_PUTS = 1


def _puts_for_cal_option(option: str) -> int:
    """PUTs one device is reserved for this resolved calibration mode."""
    if option in {OFFSET_CAL_OFF, OFFSET_CAL_INHERIT}:
        return 0
    if option == OFFSET_CAL_ON_RESET:
        return 1
    if option == OFFSET_CAL_THRESHOLD:
        return _THRESHOLD_DAILY_PUTS
    hours = hours_from_midnight(option)
    return len(hours) if hours else 0


def daily_offset_cal_puts(coordinator: TadoDataUpdateCoordinator) -> int:
    """How many offset PUTs auto-cal will spend per quota day (0 if off).

    Each linked measuring device uses its own zone mode. inherit is already
    resolved to the bridge option, so a threshold zone does not raise the
    reserve for an on_reset zone.
    """
    from ..const import (
        CONF_OFFSET_CAL_INTERVAL,
        CONF_ZONE_TEMP_ENTITIES,
        DEFAULT_OFFSET_CAL_INTERVAL,
    )

    if coordinator.config_entry is None:
        return 0

    linked = coordinator.config_entry.data.get(CONF_ZONE_TEMP_ENTITIES) or {}
    if not isinstance(linked, dict) or not linked:
        return 0

    resolver = getattr(coordinator, "effective_zone_offset_cal_interval", None)
    fallback = str(
        coordinator.config_entry.data.get(
            CONF_OFFSET_CAL_INTERVAL, DEFAULT_OFFSET_CAL_INTERVAL
        )
    )
    total = 0
    for _serial, zone_id in measuring_devices(coordinator):
        if not linked.get(str(zone_id)):
            continue
        option = resolver(zone_id) if resolver is not None else fallback
        total += _puts_for_cal_option(str(option))
    return total


def hours_from_midnight(option: str) -> list[int] | None:
    """Local hours (from 00:00) for a 3h-grid interval, or None if not clock-based."""
    if option in {OFFSET_CAL_OFF, OFFSET_CAL_ON_RESET, OFFSET_CAL_THRESHOLD}:
        return None
    if not option.endswith("h"):
        return None
    try:
        step = int(option[:-1])
    except ValueError:
        return None
    return None if step not in OFFSET_CAL_HOUR_STEPS else list(range(0, 24, step))


def offset_reading_is_anchored(
    anchor: tuple[float, float] | None,
    *,
    current: float,
    tado_inside: float,
) -> bool:
    """True when this inside reading was already used for the current offset.

    The reading includes the offset, so another pass would add the same gap.
    """
    if anchor is None:
        return False
    anchored_inside, anchored_offset = anchor
    return (
        abs(current - anchored_offset) < OFFSET_STEP
        and abs(tado_inside - anchored_inside) < OFFSET_STEP
    )


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
    if inside is None or not cloud_reading_is_live(inside):
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


def _offset_number_state(
    coordinator: TadoDataUpdateCoordinator, serial: str
) -> float | None:
    """State of this device's offset number."""
    from homeassistant.helpers import entity_registry as er

    from ..const import DOMAIN

    reg = er.async_get(coordinator.hass)
    unique_ids = []
    if coordinator.config_entry is not None:
        entry_id = coordinator.config_entry.entry_id
        unique_ids.append(f"{entry_id}_temperature_offset_{serial}")

    for unique_id in unique_ids:
        entity_id = reg.async_get_entity_id("number", DOMAIN, unique_id)
        if entity_id is None:
            continue
        state = coordinator.hass.states.get(entity_id)
        if state is None or state.state in {"unknown", "unavailable"}:
            continue
        try:
            return float(state.state)
        except TypeError, ValueError:
            continue
    return None


def current_device_offset(
    coordinator: TadoDataUpdateCoordinator, serial: str
) -> float | None:
    """Optimistic offset, cache, device snapshot, or the offset number."""
    optimistic = coordinator.optimistic.get_offset(serial)
    if optimistic is not None:
        return float(optimistic)
    cached = coordinator.data_manager.offsets_cache.get(serial)
    if cached is not None:
        celsius = getattr(cached, "celsius", None)
        if celsius is not None:
            return float(celsius)
        if isinstance(cached, int | float) and not isinstance(cached, bool):
            return float(cached)
    device = coordinator.devices_meta.get(serial)
    if device is not None:
        value = getattr(device, "temperature_offset", None)
        if value is not None:
            return float(value)
    return _offset_number_state(coordinator, serial)


def measuring_devices(
    coordinator: TadoDataUpdateCoordinator,
) -> list[tuple[str, int]]:
    """Serial + zone for devices that expose a temperature offset."""
    from .discovery import yield_devices

    found: list[tuple[str, int]] = []
    for device, zone_id in yield_devices(
        coordinator,
        include_zone_types={ZONE_TYPE_HEATING, ZONE_TYPE_AIR_CONDITIONING},
        capability=CAPABILITY_INSIDE_TEMP,
    ):
        if serial := getattr(device, "serial_no", None):
            found.append((str(serial), int(zone_id)))
    return found


async def queue_offset_cal_writes(
    coordinator: TadoDataUpdateCoordinator,
    reason: str,
    linked: dict[str, Any],
    zone_id: int | None = None,
) -> int:
    """Queue one offset PUT per measuring device that needs a change."""
    wrote = 0
    zone_states = getattr(coordinator.data, "zone_states", None) or {}
    for serial, zid in measuring_devices(coordinator):
        if await _queue_one_offset(
            coordinator, reason, linked, zone_id, serial, zid, zone_states
        ):
            wrote += 1
    return wrote


def _linked_entity_id(
    coordinator: TadoDataUpdateCoordinator,
    requested_zone: int | None,
    zone_id: int,
    linked: dict[str, Any],
) -> str | None:
    """Linked thermostat, or None when this device is outside the request."""
    if requested_zone is not None and zone_id != requested_zone:
        return None
    dummy = coordinator.dummy_handler
    if dummy and dummy.is_dummy_zone(zone_id):
        return None
    entity_id = linked.get(str(zone_id))
    return str(entity_id) if entity_id else None


async def _current_offset(
    coordinator: TadoDataUpdateCoordinator, serial: str, zone_id: int
) -> float | None:
    """Device offset, fetched once when the cache has none."""
    current = current_device_offset(coordinator, serial)
    if current is not None:
        return current
    try:
        await coordinator.data_manager._fetch_offset_for(serial)
    except Exception:
        _LOGGER.debug(
            "Offset cal zone %s device %s: offset fetch failed",
            zone_id,
            serial,
        )
    return current_device_offset(coordinator, serial)


def _log_missing_offset(
    reason: str,
    zone_id: int,
    serial: str,
    thermostat: float | None,
    tado_inside: float | None,
    current: float | None,
) -> None:
    """Manual skips warn. Scheduled skips stay at debug."""
    values = (zone_id, serial, thermostat, tado_inside, current)
    if reason == "manual":
        _LOGGER.warning(
            "Offset cal skipped: zone %s device %s (thermostat=%s tado=%s offset=%s)",
            *values,
        )
        return
    _LOGGER.debug(
        "Skip offset cal zone %s device %s (thermostat=%s tado=%s offset=%s)",
        *values,
    )


async def _queue_one_offset(
    coordinator: TadoDataUpdateCoordinator,
    reason: str,
    linked: dict[str, Any],
    requested_zone: int | None,
    serial: str,
    zone_id: int,
    zone_states: Any,
) -> bool:
    """Queue one device write. False when the device needs no change."""
    entity_id = _linked_entity_id(coordinator, requested_zone, zone_id, linked)
    if entity_id is None:
        return False
    thermostat = read_entity_temperature(coordinator.hass, entity_id)
    tado_inside = inside_from_zone_state(
        zone_states.get(str(zone_id)) or zone_states.get(zone_id)
    )
    current = await _current_offset(coordinator, serial, zone_id)
    if thermostat is None or tado_inside is None or current is None:
        _log_missing_offset(reason, zone_id, serial, thermostat, tado_inside, current)
        return False
    if reason != "manual" and offset_reading_is_anchored(
        coordinator._offset_cal_inside_anchor.get(serial),
        current=current,
        tado_inside=tado_inside,
    ):
        return False
    desired = compute_device_offset(thermostat, tado_inside, current)
    threshold = coordinator.get_zone_offset_cal_threshold(zone_id)
    if abs(desired - current) < max(threshold, OFFSET_STEP):
        return False
    _LOGGER.info(
        "Offset cal (%s) %s: thermostat=%.2f tado=%.2f offset %.1f -> %.1f",
        reason,
        serial,
        thermostat,
        tado_inside,
        current,
        desired,
    )
    await coordinator.async_set_temperature_offset(serial, desired)
    coordinator._offset_cal_inside_anchor[serial] = (tado_inside, desired)
    return True
