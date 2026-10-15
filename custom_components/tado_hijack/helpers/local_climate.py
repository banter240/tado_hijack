"""Set a linked HomeKit or Matter climate. The cloud call stays separate."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_HVAC_MODES,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACMode,
)
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant, State

from ..const import PROTECTION_MODE_TEMP
from .logging_utils import get_redacted_logger

_LOGGER = get_redacted_logger(__name__)
_SKIP = {STATE_UNAVAILABLE, STATE_UNKNOWN}


def climate_min_setpoint(state: State | None) -> float:
    """Minimum setpoint for a climate that has no off mode."""
    raw = state.attributes.get("min_temp") if state is not None else None
    if isinstance(raw, int | float):
        return float(raw)
    return float(PROTECTION_MODE_TEMP)


def climate_is_off(state: State | None) -> bool:
    """True when the climate is off, or held at its minimum setpoint."""
    if state is None or state.state in _SKIP:
        return False
    modes = state.attributes.get(ATTR_HVAC_MODES) or []
    if state.state == HVACMode.OFF:
        return True
    if HVACMode.OFF in modes:
        return False
    target = state.attributes.get(ATTR_TEMPERATURE)
    if not isinstance(target, int | float):
        return False
    return float(target) <= climate_min_setpoint(state) + 0.05


async def async_set_off(hass: HomeAssistant, entity_id: str, *, blocking: bool) -> None:
    """Turn one climate off. Without an off mode, set its minimum temperature."""
    state = hass.states.get(entity_id)
    modes = state.attributes.get(ATTR_HVAC_MODES) if state else None
    if HVACMode.OFF in (modes or []):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_HVAC_MODE,
            {ATTR_ENTITY_ID: entity_id, ATTR_HVAC_MODE: HVACMode.OFF},
            blocking=blocking,
        )
        return
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: entity_id, ATTR_TEMPERATURE: climate_min_setpoint(state)},
        blocking=blocking,
    )


async def async_set_temperature(
    hass: HomeAssistant,
    entity_id: str,
    temperature: float,
    *,
    blocking: bool,
    ensure_heat: bool = False,
) -> None:
    """Set one climate temperature. ``ensure_heat`` leaves off before the set."""
    if ensure_heat:
        state = hass.states.get(entity_id)
        modes = state.attributes.get(ATTR_HVAC_MODES) if state else None
        if (
            state is not None
            and state.state == HVACMode.OFF
            and HVACMode.HEAT in (modes or [])
        ):
            await hass.services.async_call(
                CLIMATE_DOMAIN,
                SERVICE_SET_HVAC_MODE,
                {ATTR_ENTITY_ID: entity_id, ATTR_HVAC_MODE: HVACMode.HEAT},
                blocking=blocking,
            )
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: entity_id, ATTR_TEMPERATURE: temperature},
        blocking=blocking,
    )


async def async_apply_available(
    hass: HomeAssistant,
    entity_ids: list[str],
    action: Callable[[str], Awaitable[None]],
    *,
    failure: str,
) -> None:
    """Run an action on climates that have a state. One failure does not stop the rest."""
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        if state is None or state.state in _SKIP:
            continue
        try:
            await action(entity_id)
        except Exception:
            _LOGGER.warning(failure, entity_id, exc_info=True)
