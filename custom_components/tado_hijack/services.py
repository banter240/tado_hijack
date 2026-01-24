"""Services for Tado Hijack."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, ServiceCall

from .const import (
    DOMAIN,
    OVERLAY_AUTO,
    OVERLAY_MANUAL,
    OVERLAY_NEXT_BLOCK,
    OVERLAY_PRESENCE,
    OVERLAY_TIMER,
    POWER_ON,
    SERVICE_BOOST_ALL_ZONES,
    SERVICE_MANUAL_POLL,
    SERVICE_RESUME_ALL_SCHEDULES,
    SERVICE_SET_TIMER,
    SERVICE_SET_TIMER_ALL,
    SERVICE_TURN_OFF_ALL_ZONES,
    ZONE_TYPE_AIR_CONDITIONING,
    ZONE_TYPE_HEATING,
    ZONE_TYPE_HOT_WATER,
)

if TYPE_CHECKING:
    from .coordinator import TadoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


def _round_hotwater_temp(temperature: float) -> int:
    """Round temperature for hot water (0.5+ rounds up, below 0.5 rounds down)."""
    return math.floor(temperature + 0.5)


def _parse_service_call_data(call: ServiceCall) -> dict[str, Any]:
    """Parse common parameters from service call data."""
    duration = call.data.get("duration")
    duration_minutes = int(duration) if duration else None

    # Resolve overlay mode
    overlay = call.data.get("overlay")
    overlay_mode = None
    if duration_minutes:
        overlay_mode = OVERLAY_TIMER
    elif overlay in [
        "next_time_block",
        OVERLAY_AUTO,
        "next_schedule",
        OVERLAY_NEXT_BLOCK,
    ]:
        overlay_mode = OVERLAY_NEXT_BLOCK
    elif overlay == OVERLAY_PRESENCE:
        overlay_mode = OVERLAY_PRESENCE
    elif overlay == OVERLAY_MANUAL:
        overlay_mode = OVERLAY_MANUAL

    return {
        "duration": duration_minutes,
        "overlay": overlay_mode,
        "power": call.data.get("power", POWER_ON),
        "temperature": call.data.get("temperature"),
    }


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

    async def handle_set_timer(call: ServiceCall) -> None:
        """Service to set a manual overlay with duration (batched)."""
        entity_ids = call.data.get("entity_id")
        if not entity_ids:
            return

        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]

        params = _parse_service_call_data(call)
        zone_ids: list[int] = []
        for entity_id in entity_ids:
            if zone_id := coordinator.get_zone_id_from_entity(entity_id):
                zone_ids.append(zone_id)
            else:
                _LOGGER.warning("Could not resolve Tado zone for entity %s", entity_id)

        if zone_ids:
            await _execute_set_timer(coordinator, zone_ids, params)

    async def handle_set_timer_all(call: ServiceCall) -> None:
        """Service to set a manual overlay for all zones (batched)."""
        include_heating = bool(call.data.get("include_heating", True))
        include_ac = bool(call.data.get("include_ac", False))

        params = _parse_service_call_data(call)
        zone_ids: list[int] = []
        for zid, zone in coordinator.zones_meta.items():
            ztype = getattr(zone, "type", ZONE_TYPE_HEATING)
            if (ztype == ZONE_TYPE_HEATING and include_heating) or (
                ztype == ZONE_TYPE_AIR_CONDITIONING and include_ac
            ):
                zone_ids.append(zid)

        if not zone_ids:
            _LOGGER.warning("No zones found for set_timer_all_zones")
            return

        await _execute_set_timer(coordinator, zone_ids, params)

    hass.services.async_register(DOMAIN, SERVICE_MANUAL_POLL, handle_manual_poll)
    hass.services.async_register(
        DOMAIN, SERVICE_RESUME_ALL_SCHEDULES, handle_resume_schedules
    )
    hass.services.async_register(
        DOMAIN, SERVICE_TURN_OFF_ALL_ZONES, handle_turn_off_all
    )
    hass.services.async_register(DOMAIN, SERVICE_BOOST_ALL_ZONES, handle_boost_all)
    hass.services.async_register(DOMAIN, SERVICE_SET_TIMER, handle_set_timer)
    hass.services.async_register(DOMAIN, SERVICE_SET_TIMER_ALL, handle_set_timer_all)


async def _execute_set_timer(
    coordinator: TadoDataUpdateCoordinator,
    zone_ids: list[int],
    params: dict[str, Any],
) -> None:
    """Execute set_timer logic with temperature capping and proper rounding for hot water."""
    power = params["power"]
    temperature = params["temperature"]
    duration = params["duration"]
    overlay = params["overlay"]

    if temperature is not None:
        for zone_id in zone_ids:
            zone = coordinator.zones_meta.get(zone_id)
            ztype = (
                getattr(zone, "type", ZONE_TYPE_HEATING) if zone else ZONE_TYPE_HEATING
            )

            # Apply proper rounding for hot water
            temp_value: float
            if ztype == ZONE_TYPE_HOT_WATER:
                temp_value = float(_round_hotwater_temp(float(temperature)))
            else:
                temp_value = float(temperature)

            capped_temp = coordinator.get_capped_temperature(zone_id, temp_value)
            await coordinator.async_set_multiple_zone_overlays(
                zone_ids=[zone_id],
                power=power,
                temperature=capped_temp,
                duration=duration,
                overlay_mode=overlay,
            )
    else:
        await coordinator.async_set_multiple_zone_overlays(
            zone_ids=zone_ids,
            power=power,
            temperature=None,
            duration=duration,
            overlay_mode=overlay,
        )


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload Tado Hijack services."""
    hass.services.async_remove(DOMAIN, SERVICE_MANUAL_POLL)
    hass.services.async_remove(DOMAIN, SERVICE_RESUME_ALL_SCHEDULES)
    hass.services.async_remove(DOMAIN, SERVICE_TURN_OFF_ALL_ZONES)
    hass.services.async_remove(DOMAIN, SERVICE_BOOST_ALL_ZONES)
    hass.services.async_remove(DOMAIN, SERVICE_SET_TIMER)
    hass.services.async_remove(DOMAIN, SERVICE_SET_TIMER_ALL)
