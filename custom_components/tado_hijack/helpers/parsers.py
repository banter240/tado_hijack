"""Parsing utilities for Tado Hijack."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from ..models import RateLimit

if TYPE_CHECKING:
    from tadoasync.models import Capabilities


_QUOTA_REGEX = re.compile(r"q=(\d+)")
_REMAINING_REGEX = re.compile(r"r=(\d+)")


def parse_ratelimit_headers(headers: dict[str, Any]) -> RateLimit | None:
    """Extract RateLimit information from Tado API headers."""

    def extract(pattern: re.Pattern[str], value: str) -> int | None:
        match = pattern.search(value)
        return int(match[1]) if match else None

    policy = headers.get("RateLimit-Policy", "")
    rl = headers.get("RateLimit", "")

    limit = extract(_QUOTA_REGEX, policy)
    remaining = extract(_REMAINING_REGEX, rl)

    if limit is not None or remaining is not None:
        return RateLimit(limit=limit or 0, remaining=remaining or 0)

    return None


def get_ac_capabilities(capabilities: Capabilities) -> dict[str, set[str]]:
    """Extract all available AC options across all supported modes."""
    fan_speeds: set[str] = set()
    v_swings: set[str] = set()
    h_swings: set[str] = set()

    for mode_attr in ("auto", "cool", "dry", "fan", "heat"):
        if ac_mode := getattr(capabilities, mode_attr, None):
            if fan_speeds_attr := getattr(ac_mode, "fan_speeds", None):
                fan_speeds.update(fan_speeds_attr)
            if fan_level_attr := getattr(ac_mode, "fan_level", None):
                fan_speeds.update(fan_level_attr)
            if vertical_swing_attr := getattr(ac_mode, "vertical_swing", None):
                v_swings.update(vertical_swing_attr)
            if swing_attr := getattr(ac_mode, "swing", None):
                v_swings.update(swing_attr)
            if horizontal_swing_attr := getattr(ac_mode, "horizontal_swing", None):
                h_swings.update(horizontal_swing_attr)

    return {
        "fan_speeds": fan_speeds,
        "vertical_swings": v_swings,
        "horizontal_swings": h_swings,
    }


def parse_schedule_temperature(state: Any) -> float | None:
    """Extract the target temperature from the active schedule in zone state.

    Returns None if the schedule is OFF or no temperature is defined.
    """
    if not state or not (setting := getattr(state, "setting", None)):
        return None

    # If schedule power is explicitly OFF, there is no target temperature
    if getattr(setting, "power", "ON") == "OFF":
        return None

    if temp := getattr(setting, "temperature", None):
        celsius = getattr(temp, "celsius", None)
        return float(celsius) if celsius is not None else None
    return None
