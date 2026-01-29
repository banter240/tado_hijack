"""Services for Tado Hijack."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError

from .const import (
    DOMAIN,
    OVERLAY_AUTO,
    OVERLAY_MANUAL,
    OVERLAY_NEXT_BLOCK,
    OVERLAY_PRESENCE,
    OVERLAY_TIMER,
    POWER_OFF,
    POWER_ON,
    SERVICE_BOOST_ALL_ZONES,
    SERVICE_MANUAL_POLL,
    SERVICE_RESUME_ALL_SCHEDULES,
    SERVICE_SET_MODE,
    SERVICE_SET_MODE_ALL,
    SERVICE_SET_WATER_HEATER_MODE,
    SERVICE_TURN_OFF_ALL_ZONES,
    ZONE_TYPE_HOT_WATER,
)

if TYPE_CHECKING:
    from .coordinator import TadoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


def _parse_and_get_overlay_mode(
    call: ServiceCall, duration_minutes: int | None
) -> str | None:
    """Parse and return the overlay mode from a service call."""
    overlay = call.data.get("overlay")
    if duration_minutes:
        return OVERLAY_TIMER
    if overlay in [
        "next_time_block",
        OVERLAY_AUTO,
        "next_schedule",
        OVERLAY_NEXT_BLOCK,
    ]:
        return OVERLAY_NEXT_BLOCK
    if overlay == OVERLAY_PRESENCE:
        return OVERLAY_PRESENCE
    return OVERLAY_MANUAL if overlay == OVERLAY_MANUAL else None


def _parse_service_call_data(call: ServiceCall) -> dict[str, Any]:
    """Parse common parameters from service call data."""
    duration = call.data.get("duration")
    duration_minutes = int(duration) if duration else None
    overlay_mode = _parse_and_get_overlay_mode(call, duration_minutes)

    return {
        "duration": duration_minutes,
        "overlay": overlay_mode,
        "operation_mode": call.data.get("hvac_mode") or call.data.get("operation_mode"),
        "temperature": call.data.get("temperature"),
        "refresh_after": call.data.get("refresh_after", False),
    }


def _validate_service_params(
    operation_mode: str | None,
    temperature: float | None,
    duration: int | None,
    overlay_mode: str | None,
    is_water_heater: bool = False,
) -> None:
    """Validate service parameters against the allowed matrix (DRY)."""
    # 1. 'auto' (Resume Schedule) must be clean
    if operation_mode == "auto":
        # Allow overlay_mode to be 'manual' (the UI default) but nothing else
        if (
            temperature is not None
            or duration is not None
            or (overlay_mode is not None and overlay_mode != "manual")
        ):
            raise ServiceValidationError(
                f"When setting {'water heater' if is_water_heater else 'mode'} to 'auto' (Resume Schedule), "
                "you cannot provide a temperature, duration, or a non-default overlay mode. "
                "The smart schedule will take full control."
            )
        return

    # 2. 'off' cannot have a temperature
    if operation_mode == POWER_OFF and temperature is not None:
        raise ServiceValidationError(
            f"When setting {'water heater' if is_water_heater else 'mode'} to 'off', "
            "you cannot provide a target temperature."
        )

    # 3. 'heat' must have a temperature
    if operation_mode == "heat" and temperature is None:
        range_str = "30 and 65°C" if is_water_heater else "5 and 30°C"
        raise ServiceValidationError(
            f"Temperature must be provided when setting {'water heater' if is_water_heater else 'mode'} to 'heat'. "
            f"Please specify a target temperature between {range_str}."
        )


async def async_setup_services(
    hass: HomeAssistant, coordinator: TadoDataUpdateCoordinator
) -> None:
    """Set up the services for Tado Hijack."""

    async def handle_manual_poll(call: ServiceCall) -> None:
        """Service to force refresh."""
        refresh_type = call.data.get("refresh_type", "all")
        _LOGGER.debug("Service call: manual_poll (type: %s)", refresh_type)
        await coordinator.async_manual_poll(refresh_type)

    async def handle_resume_schedules(call: ServiceCall) -> None:
        """Service to resume all schedules."""
        _LOGGER.debug("Service call: resume_all_schedules")
        await coordinator.async_resume_all_schedules()

    async def handle_turn_off_all(call: ServiceCall) -> None:
        """Service to turn off all zones."""
        _LOGGER.debug("Service call: turn_off_all_zones")
        await coordinator.async_turn_off_all_zones()

    async def handle_boost_all(call: ServiceCall) -> None:
        """Service to boost all zones."""
        _LOGGER.debug("Service call: boost_all_zones")
        await coordinator.async_boost_all_zones()

    async def handle_set_mode(call: ServiceCall) -> None:
        """Service to set a manual mode (batched)."""
        entity_ids = call.data.get("entity_id")
        if not entity_ids:
            return

        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]

        params = _parse_service_call_data(call)
        zone_ids: list[int] = []
        for entity_id in entity_ids:
            if (zone_id := coordinator.get_zone_id_from_entity(entity_id)) is not None:
                zone_ids.append(zone_id)
            else:
                _LOGGER.warning("Could not resolve Tado zone for entity %s", entity_id)

        if zone_ids:
            await _execute_set_mode(coordinator, zone_ids, params)

    async def handle_set_mode_all(call: ServiceCall) -> None:
        """Service to set a manual overlay for all heating/AC zones (batched)."""
        params = _parse_service_call_data(call)
        zone_ids = coordinator.get_active_zones(
            include_heating=call.data.get("include_heating", True),
            include_ac=call.data.get("include_ac", False),
        )

        if not zone_ids:
            _LOGGER.warning("No zones found for set_mode_all_zones")
            return

        await _execute_set_mode(coordinator, zone_ids, params)

    async def handle_set_water_heater_mode(call: ServiceCall) -> None:
        """Service to set a mode for water heater entities."""
        entity_id = call.data.get("entity_id")
        if not entity_id:
            return
        zone_id = coordinator.get_zone_id_from_entity(entity_id)
        if zone_id is None:
            _LOGGER.warning("Could not resolve Tado zone for entity %s", entity_id)
            return

        params = _parse_service_call_data(call)
        operation_mode = params["operation_mode"]
        temperature = params["temperature"]
        duration = params["duration"]
        overlay_mode = params["overlay"]
        refresh_after = params["refresh_after"]

        # Validate parameters (DRY)
        _validate_service_params(
            operation_mode, temperature, duration, overlay_mode, is_water_heater=True
        )

        if operation_mode == "auto":
            await coordinator.async_set_hot_water_auto(
                zone_id, refresh_after=refresh_after, ignore_global_config=True
            )
            return

        if operation_mode == POWER_OFF:
            await coordinator.async_set_hot_water_off(
                zone_id, refresh_after=refresh_after
            )
            return

        if operation_mode == "heat":
            # Round to integer for hot water (Tado requirement) - validation is now in coordinator
            final_temp = round(float(temperature)) if temperature is not None else None

            # Use overlay helper which supports duration/timer
            await coordinator.async_set_zone_overlay(
                zone_id=zone_id,
                power=POWER_ON,
                temperature=final_temp,
                duration=duration,
                overlay_type=ZONE_TYPE_HOT_WATER,
                overlay_mode=overlay_mode,
                refresh_after=refresh_after,
            )
            return

        _LOGGER.warning(
            "Unsupported operation_mode '%s' for water heater entity %s",
            operation_mode,
            entity_id,
        )

    hass.services.async_register(DOMAIN, SERVICE_MANUAL_POLL, handle_manual_poll)
    hass.services.async_register(
        DOMAIN, SERVICE_RESUME_ALL_SCHEDULES, handle_resume_schedules
    )
    hass.services.async_register(
        DOMAIN, SERVICE_TURN_OFF_ALL_ZONES, handle_turn_off_all
    )
    hass.services.async_register(DOMAIN, SERVICE_BOOST_ALL_ZONES, handle_boost_all)
    hass.services.async_register(DOMAIN, SERVICE_SET_MODE, handle_set_mode)
    hass.services.async_register(DOMAIN, SERVICE_SET_MODE_ALL, handle_set_mode_all)
    hass.services.async_register(
        DOMAIN, SERVICE_SET_WATER_HEATER_MODE, handle_set_water_heater_mode
    )


async def _execute_set_mode(
    coordinator: TadoDataUpdateCoordinator,
    zone_ids: list[int],
    params: dict[str, Any],
    overlay_type: str | None = None,
) -> None:
    """Execute set_mode logic via coordinator's overlay function."""
    operation_mode = params["operation_mode"]
    refresh_after = params.get("refresh_after", False)
    temperature = params["temperature"]
    duration = params["duration"]
    overlay_mode = params["overlay"]

    # Validate parameters (DRY)
    _validate_service_params(operation_mode, temperature, duration, overlay_mode)

    # Special case: 'auto' means resume schedule for all target zones
    if operation_mode == "auto":
        for zone_id in zone_ids:
            await coordinator.async_set_zone_auto(
                zone_id, refresh_after=refresh_after, ignore_global_config=True
            )
        return

    # Derive power from mode
    power = POWER_OFF if operation_mode == "off" else POWER_ON

    # Fallback to manual overlay if no duration or mode is given
    if not overlay_mode and not duration:
        overlay_mode = OVERLAY_MANUAL

    await coordinator.async_set_multiple_zone_overlays(
        zone_ids=zone_ids,
        power=power,
        temperature=temperature,
        duration=duration,
        overlay_mode=overlay_mode,
        overlay_type=overlay_type,
        refresh_after=refresh_after,
    )


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload Tado Hijack services."""
    hass.services.async_remove(DOMAIN, SERVICE_MANUAL_POLL)
    hass.services.async_remove(DOMAIN, SERVICE_RESUME_ALL_SCHEDULES)
    hass.services.async_remove(DOMAIN, SERVICE_TURN_OFF_ALL_ZONES)
    hass.services.async_remove(DOMAIN, SERVICE_BOOST_ALL_ZONES)
    hass.services.async_remove(DOMAIN, SERVICE_SET_MODE)
    hass.services.async_remove(DOMAIN, SERVICE_SET_MODE_ALL)
    hass.services.async_remove(DOMAIN, SERVICE_SET_WATER_HEATER_MODE)
