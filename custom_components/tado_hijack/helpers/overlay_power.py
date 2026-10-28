"""Power and temperature for one merged overlay."""

from __future__ import annotations

from typing import Any

from ..const import OFF_MAGIC_TEMP, POWER_OFF, POWER_ON


def map_magic_temp_to_power(temp: float | None) -> tuple[float | None, str]:
    """Magic off temperature is power OFF. Any other target stays on."""
    return (None, POWER_OFF) if temp == OFF_MAGIC_TEMP else (temp, POWER_ON)


def resolve_overlay_power(
    setting: dict[str, Any] | None,
) -> tuple[float | None, str]:
    """Temperature and power for one merged overlay."""
    setting = setting or {}
    temp = (setting.get("temperature") or {}).get("celsius")
    # A later off keeps an older temperature in the merged setting.
    if setting.get("power") == POWER_OFF:
        return None, POWER_OFF
    return map_magic_temp_to_power(temp)
