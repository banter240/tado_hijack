"""Pre-API validation for Tado overlay payloads.

Validates overlay payloads before sending to Tado API to prevent 422 errors
and save API quota. Simulates API-side validation rules.
"""

from __future__ import annotations

from typing import Any


def validate_overlay_payload(
    data: dict[str, Any], zone_type: str, supports_temp: bool = True
) -> tuple[bool, str | None]:
    """Validate overlay payload before sending to Tado API.

    Args:
        data: The overlay payload dict with 'setting' and 'termination'
        zone_type: Zone type (HOT_WATER, HEATING, AIR_CONDITIONING)
        supports_temp: Whether this zone supports temperature (for HOT_WATER with/without OpenTherm)

    Returns:
        (is_valid, error_message) - error_message is None if valid

    """
    setting = data.get("setting", {})
    power = setting.get("power")
    # Temperature is a dict like {'celsius': 21.0}
    temp_dict = setting.get("temperature")
    has_temp = temp_dict is not None and temp_dict.get("celsius") is not None
    mode = setting.get("mode")

    # Rule 1: AIR_CONDITIONING with power=ON requires mode. Temperature depends on mode.
    if zone_type == "AIR_CONDITIONING":
        if power == "ON":
            if mode is None:
                return (
                    False,
                    f"mode required for AIR_CONDITIONING with power=ON (Payload settings: {setting.keys()})",
                )
            # Temperature is only strictly required for COOL and HEAT
            if mode in ("COOL", "HEAT") and not has_temp:
                return (
                    False,
                    f"temperature (celsius) required for AIR_CONDITIONING in {mode} mode",
                )
            # FAN mode requires fanLevel or fanSpeed
            if mode == "FAN":
                has_fan_level = setting.get("fanLevel") is not None
                has_fan_speed = setting.get("fanSpeed") is not None
                if not (has_fan_level or has_fan_speed):
                    return (
                        False,
                        f"fanLevel or fanSpeed required for AIR_CONDITIONING in FAN mode (Payload settings: {setting.keys()})",
                    )

    elif zone_type == "HEATING":
        # HEATING with power=ON requires temperature
        # Exception: temperature=0 is magic number for OFF mode (validated in executor)
        if power == "ON" and not has_temp:
            return False, "temperature (celsius) required for HEATING with power=ON"

    elif zone_type == "HOT_WATER":
        # Hot Water with OpenTherm supports temperature, non-OpenTherm does not
        if not supports_temp and has_temp:
            return (
                False,
                "temperature not allowed for HOT_WATER without OpenTherm (API limitation)",
            )

    return True, None
