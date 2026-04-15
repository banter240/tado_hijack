"""Parsing utilities for Tado v3 (Classic) zone state."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import homeassistant.util.dt as dt_util

from ...const import BOOST_MODE_TEMP, TEMP_TOLERANCE
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
from ..parsers import resolve_zone_mode

# Re-export for callers that import it directly (e.g. definitions.py uses
# compute_absolute_humidity via this module).
__all__ = ["compute_absolute_humidity"]


def parse_heating_power(state: Any, zone_type: str | None = None) -> float:
    """Extract heating power percentage from v3 zone state.

    Hot Water Power: ON -> 100%, OFF -> 0% (Dev.2 Logic)
    Regular Heating: Percentage from activityDataPoints
    """
    if not state:
        return 0.0

    # Handle Hot Water (Dev.2 Logic)
    if zone_type == "HOT_WATER":
        if setting := getattr(state, "setting", None):
            return 100.0 if getattr(setting, "power", "OFF") == "ON" else 0.0
        return 0.0

    # Regular Heating Power (%)
    if not getattr(state, "activity_data_points", None):
        return 0.0

    if (
        hasattr(state.activity_data_points, "heating_power")
        and state.activity_data_points.heating_power
    ):
        return float(state.activity_data_points.heating_power.percentage)

    return 0.0


def parse_next_schedule_temp(state: Any) -> float | None:
    """Extract next schedule target temperature from v3 zone state."""
    nsc = getattr(state, "next_schedule_change", None)
    if not nsc:
        return None
    setting = getattr(nsc, "setting", None)
    if not setting:
        return None
    temp = getattr(setting, "temperature", None)
    return None if temp is None else temp.celsius or None


def parse_next_schedule_mode(state: Any) -> str | None:
    """Extract next schedule mode from v3 zone state."""
    if nsc := getattr(state, "next_schedule_change", None):
        return (
            (
                (setting.power == "ON" and (setting.mode or "HEATING"))
                or (setting.power == "OFF" and "OFF")
            )
            or None
            if (setting := getattr(nsc, "setting", None))
            else None
        )
    else:
        return None


def parse_next_time_block_start(state: Any) -> datetime | None:
    """Extract next time block start datetime from v3 zone state (dict-based)."""
    ntb = getattr(state, "next_time_block", None)
    if not ntb or not isinstance(ntb, dict):
        return None
    start = ntb.get("start")
    return dt_util.parse_datetime(start) if start else None


def get_overlay_type(state: Any) -> str | None:
    """Extract overlay type from v3 zone state setting (e.g. 'HEATING')."""
    setting = getattr(state, "setting", None)
    return getattr(setting, "type", None) if setting else None


def resolve_ac_mode(opt_mode: str | None, state: Any) -> str:
    """Resolve AC mode for v3 Classic (mode exists in state.setting).

    Returns a physical AC mode (COOL, HEAT, DRY, FAN) — never AUTO.
    """
    setting = getattr(state, "setting", None)
    state_mode = getattr(setting, "mode", None) if setting else None

    current_mode = opt_mode or state_mode
    if current_mode == "AUTO":
        current_mode = state_mode or "COOL"
    return current_mode or "COOL"


def parse_temperature_offset(offset: Any) -> float | None:
    """Extract temperature offset from v3 offset cache entry."""
    if not offset:
        return None
    celsius = getattr(offset, "celsius", None)
    return float(celsius) if celsius is not None else None


def _get_temp_and_humidity(state: Any) -> tuple[float, float] | None:
    """Extract current temperature (°C) and relative humidity (%) from zone state.

    Returns None if either value is unavailable.
    Temperature is read from our own cloud-polled sensor_data_points, which is the
    same source as humidity — consistent regardless of HomeKit or Full Cloud mode.
    """
    sdp = getattr(state, "sensor_data_points", None)
    if not sdp:
        return None
    inside_temp = getattr(sdp, "inside_temperature", None)
    humidity = getattr(sdp, "humidity", None)
    if inside_temp is None or humidity is None:
        return None
    temp = getattr(inside_temp, "celsius", None)
    rh = getattr(humidity, "percentage", None)
    return None if temp is None or rh is None else (float(temp), float(rh))


def parse_dew_point(state: Any) -> float | None:
    """Return dew point temperature (°C) for the zone, or None if data is unavailable."""
    values = _get_temp_and_humidity(state)
    if values is None:
        return None
    temp, rh = values
    return None if rh <= 0 else round(_compute_dew_point(temp, rh), 1)


def parse_indoor_absolute_humidity(state: Any) -> float | None:
    """Return indoor absolute humidity (g/m³) for the zone, or None if data unavailable."""
    values = _get_temp_and_humidity(state)
    if values is None:
        return None
    temp, rh = values
    return None if rh <= 0 else round(compute_absolute_humidity(temp, rh), 1)


def parse_ventilation_recommended(
    state: Any,
    outdoor_temp: float,
    outdoor_rh: float,
    threshold: float = _DEFAULT_VENTILATION_AH_THRESHOLD,
) -> bool | None:
    """Return True if ventilating meaningfully reduces indoor moisture load.

    Requires indoor AH to exceed outdoor AH by at least `threshold` g/m³
    to avoid automation chatter from negligible differences.
    Returns None if indoor data is unavailable.
    """
    values = _get_temp_and_humidity(state)
    if values is None:
        return None
    temp, rh = values
    if rh <= 0:
        return False
    indoor_ah = compute_absolute_humidity(temp, rh)
    outdoor_ah = compute_absolute_humidity(outdoor_temp, outdoor_rh)
    return compute_ventilation_beneficial(indoor_ah, outdoor_ah, threshold)


def parse_mold_risk_level(state: Any) -> str | None:
    """Determine mold risk level from the dew point spread (T_room - Td)."""
    values = _get_temp_and_humidity(state)
    if values is None:
        return None
    temp, rh = values
    return compute_mold_risk_level(temp, rh)


def parse_zone_mode(state: Any) -> str | None:
    """Return the current operating mode of a v3 zone."""
    if not state:
        return None
    setting = getattr(state, "setting", None)
    power = getattr(setting, "power", "OFF") if setting else "OFF"
    temp_obj = getattr(setting, "temperature", None) if setting else None
    celsius = getattr(temp_obj, "celsius", None) if temp_obj else None
    is_boost = celsius is not None and abs(celsius - BOOST_MODE_TEMP) <= TEMP_TOLERANCE
    return resolve_zone_mode(
        overlay_active=getattr(state, "overlay_active", False),
        power=power,
        is_boost=is_boost,
    )
