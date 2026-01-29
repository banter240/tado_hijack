"""Parsing utilities for Tado Hijack."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from ..models import RateLimit

if TYPE_CHECKING:
    from tadoasync.models import Capabilities


def parse_ratelimit_headers(headers: dict[str, Any]) -> RateLimit | None:
    """Extract RateLimit information from Tado API headers."""
    policy = headers.get("RateLimit-Policy", "")
    limit_info = headers.get("RateLimit", "")

    try:
        limit = 0
        remaining = 0
        found = False

        if q_match := re.search(r"q=(\d+)", policy):
            limit = int(q_match[1])
            found = True

        if r_match := re.search(r"r=(\d+)", limit_info):
            remaining = int(r_match[1])
            found = True

        if found:
            return RateLimit(limit=limit, remaining=remaining)
    except (ValueError, TypeError, AttributeError):
        pass

    return None


def get_ac_capabilities(capabilities: Capabilities) -> dict[str, set[str]]:
    """Extract all available AC options across all supported modes."""
    fan_speeds: set[str] = set()
    v_swings: set[str] = set()
    h_swings: set[str] = set()

    for mode_attr in ("auto", "cool", "dry", "fan", "heat"):
        if ac_mode := getattr(capabilities, mode_attr, None):
            if ac_mode.fan_speeds:
                fan_speeds.update(ac_mode.fan_speeds)
            if ac_mode.fan_level:
                fan_speeds.update(ac_mode.fan_level)
            if ac_mode.vertical_swing:
                v_swings.update(ac_mode.vertical_swing)
            if ac_mode.swing:
                v_swings.update(ac_mode.swing)
            if ac_mode.horizontal_swing:
                h_swings.update(ac_mode.horizontal_swing)

    return {
        "fan_speeds": fan_speeds,
        "vertical_swing": v_swings,
        "horizontal_swings": h_swings,
    }


def parse_heating_power(state: Any) -> float:
    """Extract heating power percentage from zone state."""
    if not state or not getattr(state, "activity_data_points", None):
        return 0.0

    # Heating Power (Percentage)
    if (
        hasattr(state.activity_data_points, "heating_power")
        and state.activity_data_points.heating_power
    ):
        return float(state.activity_data_points.heating_power.percentage)

    return 0.0


def parse_hot_water_in_use(state: Any) -> bool:
    """Extract hot water activity status from zone state."""
    if not state or not getattr(state, "activity_data_points", None):
        return False

    if (
        hasattr(state.activity_data_points, "hot_water_in_use")
        and state.activity_data_points.hot_water_in_use
    ):
        return str(state.activity_data_points.hot_water_in_use.value) == "ON"

    return False
