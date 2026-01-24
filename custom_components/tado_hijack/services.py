"""Services for Tado Hijack."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, ServiceCall

from .const import (
    DOMAIN,
    SERVICE_BOOST_ALL_ZONES,
    SERVICE_MANUAL_POLL,
    SERVICE_RESUME_ALL_SCHEDULES,
    SERVICE_SET_TIMER,
    SERVICE_SET_TIMER_ALL,
    SERVICE_TURN_OFF_ALL_ZONES,
)

if TYPE_CHECKING:
    from .coordinator import TadoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


def _parse_duration(call: ServiceCall) -> int | None:
    """Parse duration from service call data."""
    duration = call.data.get("duration")
    return int(duration) if duration else None


def _resolve_overlay_mode(
    call: ServiceCall, duration_minutes: int | None
) -> str | None:
    """Resolve overlay mode from service call data.

    If a duration is provided, it ALWAYS forces 'timer' mode.
    Otherwise, it respects the explicit 'overlay' parameter.
    """
    # 1. If we have a duration, it's a timer. Period.
    if duration_minutes:
        return "timer"

    # 2. Otherwise, check explicit overlay modes
    overlay = call.data.get("overlay")
    if overlay in ["next_time_block", "auto", "next_schedule", "next_block"]:
        return "next_block"
    if overlay == "presence":
        return "presence"
    return "manual" if overlay == "manual" else None


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

        duration_minutes = _parse_duration(call)
        overlay_mode = _resolve_overlay_mode(call, duration_minutes)
        power = call.data.get("power", "ON")
        temperature = call.data.get("temperature")

        zone_ids: list[int] = []
        for entity_id in entity_ids:
            if zone_id := coordinator.get_zone_id_from_entity(entity_id):
                zone_ids.append(zone_id)
            else:
                _LOGGER.warning("Could not resolve Tado zone for entity %s", entity_id)

        if not zone_ids:
            return

        await _execute_set_timer(
            coordinator, zone_ids, power, temperature, duration_minutes, overlay_mode
        )

    async def handle_set_timer_all(call: ServiceCall) -> None:
        """Service to set a manual overlay for all zones (batched)."""
        include_heating = bool(call.data.get("include_heating", True))
        include_ac = bool(call.data.get("include_ac", False))

        duration_minutes = _parse_duration(call)
        overlay_mode = _resolve_overlay_mode(call, duration_minutes)
        power = call.data.get("power", "ON")
        temperature = call.data.get("temperature")

        zone_ids: list[int] = []
        for zid, zone in coordinator.zones_meta.items():
            ztype = getattr(zone, "type", "HEATING")
            if (ztype == "HEATING" and include_heating) or (
                ztype == "AIR_CONDITIONING" and include_ac
            ):
                zone_ids.append(zid)

        if not zone_ids:
            _LOGGER.warning("No zones found for set_timer_all_zones")
            return

        await _execute_set_timer(
            coordinator, zone_ids, power, temperature, duration_minutes, overlay_mode
        )

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
    power: str,
    temperature: Any,
    duration_minutes: int | None,
    overlay_mode: str | None,
) -> None:
    """Execute set_timer logic with temperature capping."""
    if temperature is not None:
        for zone_id in zone_ids:
            capped_temp = coordinator.get_capped_temperature(zone_id, temperature)
            await coordinator.async_set_multiple_zone_overlays(
                zone_ids=[zone_id],
                power=power,
                temperature=capped_temp,
                duration=duration_minutes,
                overlay_mode=overlay_mode,
            )
    else:
        await coordinator.async_set_multiple_zone_overlays(
            zone_ids=zone_ids,
            power=power,
            temperature=None,
            duration=duration_minutes,
            overlay_mode=overlay_mode,
        )


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload Tado Hijack services."""
    hass.services.async_remove(DOMAIN, SERVICE_MANUAL_POLL)
    hass.services.async_remove(DOMAIN, SERVICE_RESUME_ALL_SCHEDULES)
    hass.services.async_remove(DOMAIN, SERVICE_TURN_OFF_ALL_ZONES)
    hass.services.async_remove(DOMAIN, SERVICE_BOOST_ALL_ZONES)
    hass.services.async_remove(DOMAIN, SERVICE_SET_TIMER)
    hass.services.async_remove(DOMAIN, SERVICE_SET_TIMER_ALL)
