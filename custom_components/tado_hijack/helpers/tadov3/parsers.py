"""Parsing utilities for Tado v3 (Classic) zone state."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import homeassistant.util.dt as dt_util


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
