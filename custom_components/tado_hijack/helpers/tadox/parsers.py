"""Parsing utilities for Tado X (Hops API) zone state."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import homeassistant.util.dt as dt_util

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
