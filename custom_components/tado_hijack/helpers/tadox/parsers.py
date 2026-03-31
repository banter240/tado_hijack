"""Parsing utilities for Tado X (Hops API) zone state."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import homeassistant.util.dt as dt_util

from ..climate_physics import (
    VENTILATION_AH_THRESHOLD as _DEFAULT_VENTILATION_AH_THRESHOLD,
)
from ..climate_physics import (
    compute_absolute_humidity,
    compute_mold_risk_level,
    compute_ventilation_beneficial,
)
from ..climate_physics import (
    compute_dew_point as _compute_dew_point,
)

if TYPE_CHECKING:
    from datetime import datetime

    from ...lib.tadox_models import TadoXDevice, TadoXZoneState


def parse_heating_power(state: TadoXZoneState | None) -> float:
    """Extract heating power percentage from Tado X zone state."""
    if not state or not state.heating_power:
        return 0.0
    return float(state.heating_power.percentage)


def parse_next_schedule_temp(state: TadoXZoneState | None) -> float | None:
    """Extract next schedule target temperature from Tado X zone state."""
    if not state or not state.next_schedule_change:
        return None
    temp = state.next_schedule_change.setting.temperature
    return temp.value if temp else None


def parse_next_schedule_mode(state: TadoXZoneState | None) -> str | None:
    """Extract next schedule mode from Tado X zone state (HEATING or OFF)."""
    if not state or not state.next_schedule_change:
        return None
    power = state.next_schedule_change.setting.power
    if power is None:
        return None
    return "HEATING" if power == "ON" else "OFF"


def parse_next_time_block_start(state: TadoXZoneState | None) -> datetime | None:
    """Extract next time block start as datetime from Tado X zone state."""
    if not state or not state.next_time_block:
        return None
    return cast("datetime | None", dt_util.parse_datetime(state.next_time_block.start))


def resolve_ac_mode(opt_mode: str | None, state: TadoXZoneState | None) -> str:
    """Resolve AC mode for Tado X (mode not in Setting, Matter controls it).

    Returns a physical AC mode (COOL, HEAT, DRY, FAN) — never AUTO.
    """
    current_mode = opt_mode
    if current_mode == "AUTO":
        current_mode = "COOL"
    return current_mode or "COOL"


def parse_temperature_offset(device: TadoXDevice | None) -> float | None:
    """Extract temperature offset from Tado X device metadata."""
    if not device or device.temperature_offset is None:
        return None
    return float(device.temperature_offset)


def _get_humidity(state: TadoXZoneState | None) -> float | None:
    """Extract current relative humidity (%) from Tado X zone state."""
    if not state:
        return None
    rh = state.sensor_data_points.humidity.percentage
    return float(rh) if rh is not None else None


def parse_dew_point(
    state: TadoXZoneState | None, temp_celsius: float | None
) -> float | None:
    """Return dew point (°C) for a Tado X zone.

    Args:
        state:        Zone state from the Hops API (supplies humidity).
        temp_celsius: Current room temperature from the linked Matter climate
                      entity. Pass None if no entity is configured — returns None.

    """
    if temp_celsius is None:
        return None
    rh = _get_humidity(state)
    if rh is None or rh <= 0:
        return None
    return round(_compute_dew_point(temp_celsius, rh), 1)


def parse_mold_risk_level(
    state: TadoXZoneState | None, temp_celsius: float | None
) -> str | None:
    """Return mold risk level for a Tado X zone.

    Args:
        state:        Zone state from the Hops API (supplies humidity).
        temp_celsius: Current room temperature from the linked Matter climate
                      entity. Pass None if no entity is configured — returns None.

    """
    if temp_celsius is None:
        return None
    rh = _get_humidity(state)
    return None if rh is None else compute_mold_risk_level(temp_celsius, rh)


def parse_indoor_absolute_humidity(
    state: TadoXZoneState | None, temp_celsius: float | None
) -> float | None:
    """Return indoor absolute humidity (g/m³) for a Tado X zone.

    Args:
        state:        Zone state from the Hops API (supplies humidity).
        temp_celsius: Current room temperature from the linked Matter climate
                      entity. Pass None if no entity is configured — returns None.

    """
    if temp_celsius is None:
        return None
    rh = _get_humidity(state)
    if rh is None or rh <= 0:
        return None
    return round(compute_absolute_humidity(temp_celsius, rh), 1)


def parse_ventilation_recommended(
    state: TadoXZoneState | None,
    temp_celsius: float | None,
    outdoor_temp: float,
    outdoor_rh: float,
    threshold: float = _DEFAULT_VENTILATION_AH_THRESHOLD,
) -> bool | None:
    """Return True if ventilating reduces indoor moisture load for a Tado X zone.

    Args:
        state:        Zone state from the Hops API (supplies humidity).
        temp_celsius: Current room temperature from the linked Matter climate
                      entity. Pass None if no entity is configured — returns None.
        outdoor_temp: Outdoor temperature in °C (from weather entity).
        outdoor_rh:   Outdoor relative humidity in % (from weather entity).
        threshold:    Minimum AH delta (g/m³) to consider ventilation worthwhile.

    """
    if temp_celsius is None:
        return None
    rh = _get_humidity(state)
    if rh is None or rh <= 0:
        return False
    indoor_ah = compute_absolute_humidity(temp_celsius, rh)
    outdoor_ah = compute_absolute_humidity(outdoor_temp, outdoor_rh)
    return compute_ventilation_beneficial(indoor_ah, outdoor_ah, threshold)
