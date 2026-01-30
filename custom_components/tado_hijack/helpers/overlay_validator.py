"""Pre-API validation for Tado overlay payloads.

Validates overlay payloads before sending to Tado API to prevent 422 errors
and save API quota. Simulates API-side validation rules.
"""

from __future__ import annotations


def validate_overlay_payload(
    data: dict, zone_type: str
) -> tuple[bool, str | None]:
    """Validate overlay payload before sending to Tado API.

    Args:
        data: The overlay payload dict with 'setting' and 'termination'
        zone_type: Zone type (HOT_WATER, HEATING, AIR_CONDITIONING)

    Returns:
        (is_valid, error_message) - error_message is None if valid
    """
    setting = data.get("setting", {})
    power = setting.get("power")
    temperature = setting.get("temperature")
    mode = setting.get("mode")

    # Rule 1: HOT_WATER with power=ON requires temperature
    if zone_type == "HOT_WATER":
        if power == "ON" and temperature is None:
            return False, "temperature required for HOT_WATER with power=ON"

    # Rule 2: HEATING with power=ON requires temperature
    if zone_type == "HEATING":
        if power == "ON" and temperature is None:
            return False, "temperature required for HEATING with power=ON"

    # Rule 3: AIR_CONDITIONING with power=ON requires temperature AND mode
    if zone_type == "AIR_CONDITIONING":
        if power == "ON":
            if temperature is None:
                return False, "temperature required for AIR_CONDITIONING with power=ON"
            if mode is None:
                return False, "mode required for AIR_CONDITIONING with power=ON"

    return True, None
