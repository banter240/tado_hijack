"""Shared AC overlay field resolution (requested value -> optimistic -> state -> caps)."""

from __future__ import annotations

from typing import Any

FAN_LEVEL_ALIASES: frozenset[str] = frozenset({"fan_speed"})
_FAN_ATTR_ALIASES: dict[str, frozenset[str]] = {
    "fan_level": FAN_LEVEL_ALIASES,
}


def resolve_ac_attr(
    optimistic: Any,
    zone_id: int,
    setting: Any,
    attr_name: str,
    *,
    requested_key: str | None = None,
    requested_value: Any = None,
    aliases: frozenset[str] | None = None,
) -> Any:
    """Return the value to send for one AC setting attribute.

    Prefer the value from the current user action, then optimistic state, then
    the last confirmed setting. ``aliases`` treats extra action keys as the
    same attribute (fan_speed also drives fan_level).
    """
    extra = aliases if aliases is not None else _FAN_ATTR_ALIASES.get(attr_name)
    if requested_key is not None and (
        requested_key == attr_name or (extra is not None and requested_key in extra)
    ):
        return requested_value
    if optimistic is not None:
        current = optimistic.get_optimistic("zone", zone_id, attr_name)
        if current is not None:
            return current
    return getattr(setting, attr_name, None) if setting is not None else None


def pick_cap_value(
    current: Any,
    cap_values: Any,
    *,
    prefer_off: bool = False,
) -> str:
    """Uppercase ``current`` when it is in ``cap_values``, else a safe default."""
    val = str(current).upper() if current else None
    if val is not None and val in cap_values:
        return val
    if prefer_off and "OFF" in cap_values:
        return "OFF"
    return str(cap_values[0]).upper()


def apply_capped_attr(
    fields: dict[str, str],
    api_key: str,
    current: Any,
    cap_values: Any | None,
    *,
    prefer_off: bool = False,
    include_without_caps: bool = False,
) -> None:
    """Write ``api_key`` into ``fields`` from caps, or raw current if allowed."""
    if cap_values:
        fields[api_key] = pick_cap_value(current, cap_values, prefer_off=prefer_off)
    elif include_without_caps and current:
        fields[api_key] = str(current).upper()
