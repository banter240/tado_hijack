"""Services for Tado Hijack."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, ServiceCall

from .const import (
    DOMAIN,
    SERVICE_ADD_METER_READING,
    SERVICE_BOOST_ALL_ZONES,
    SERVICE_MANUAL_POLL,
    SERVICE_RESUME_ALL_SCHEDULES,
    SERVICE_SET_TIMER,
    SERVICE_TURN_OFF_ALL_ZONES,
)

if TYPE_CHECKING:
    from .coordinator import TadoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


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
        """Service to set a manual overlay with duration (batched).

        Supports both duration (minutes) and time_period (HH:MM:SS) formats.
        """
        entity_ids = call.data.get("entity_id")
        if not entity_ids:
            return

        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]

        # Parse duration: Support both 'duration' (int, minutes) and 'time_period' (str, HH:MM:SS)
        duration_minutes: int | None = None
        if time_period := call.data.get("time_period"):
            # Parse HH:MM:SS format
            try:
                parts = time_period.split(":")
                if len(parts) == 3:
                    hours, minutes, seconds = map(int, parts)
                    duration_minutes = hours * 60 + minutes + (seconds // 60)
                elif len(parts) == 2:
                    hours, minutes = map(int, parts)
                    duration_minutes = hours * 60 + minutes
                else:
                    _LOGGER.warning("Invalid time_period format: %s (expected HH:MM:SS)", time_period)
                    duration_minutes = 30
            except (ValueError, AttributeError):
                _LOGGER.warning("Failed to parse time_period: %s, using default 30min", time_period)
                duration_minutes = 30
        elif duration := call.data.get("duration"):
            # Fallback to 'duration' for backwards compatibility
            duration_minutes = int(duration)
        else:
            # Neither provided, use default
            duration_minutes = 30

        power = call.data.get("power", "ON")
        temperature = call.data.get("temperature")
        overlay = call.data.get("overlay")  # "manual", "timer", or "auto" (next_time_block)

        # Resolve overlay_mode
        overlay_mode = None
        if overlay == "next_time_block" or overlay == "auto":
            overlay_mode = "auto"
        elif overlay == "timer" or duration_minutes:
            overlay_mode = "timer"
        elif overlay == "manual":
            overlay_mode = "manual"

        # Resolve all zone IDs first
        zone_ids: list[int] = []
        for entity_id in entity_ids:
            if zone_id := coordinator.get_zone_id_from_entity(entity_id):
                zone_ids.append(zone_id)
            else:
                _LOGGER.warning("Could not resolve Tado zone for entity %s", entity_id)

        if not zone_ids:
            return

        # Batch operation - The coordinator and ApiManager handle the fusion
        await coordinator.async_set_multiple_zone_overlays(
            zone_ids=zone_ids,
            power=power,
            temperature=temperature,
            duration=duration_minutes,
            overlay_mode=overlay_mode,
        )

    async def handle_add_meter_reading(call: ServiceCall) -> None:
        """Service to add an energy meter reading for Energy IQ tracking."""
        reading = call.data.get("reading")
        if reading is None:
            _LOGGER.error("Meter reading value is required")
            return

        date = call.data.get("date")  # Optional: YYYY-MM-DD format

        try:
            await coordinator.client.add_meter_reading(int(reading), date)
            _LOGGER.info(
                "Successfully added meter reading: %d (date: %s)",
                reading,
                date or "today",
            )
        except Exception as err:
            _LOGGER.error("Failed to add meter reading: %s", err)

    hass.services.async_register(DOMAIN, SERVICE_MANUAL_POLL, handle_manual_poll)
    hass.services.async_register(
        DOMAIN, SERVICE_RESUME_ALL_SCHEDULES, handle_resume_schedules
    )
    hass.services.async_register(
        DOMAIN, SERVICE_TURN_OFF_ALL_ZONES, handle_turn_off_all
    )
    hass.services.async_register(DOMAIN, SERVICE_BOOST_ALL_ZONES, handle_boost_all)
    hass.services.async_register(DOMAIN, SERVICE_SET_TIMER, handle_set_timer)
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_METER_READING, handle_add_meter_reading
    )


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload Tado Hijack services."""
    hass.services.async_remove(DOMAIN, SERVICE_MANUAL_POLL)
    hass.services.async_remove(DOMAIN, SERVICE_RESUME_ALL_SCHEDULES)
    hass.services.async_remove(DOMAIN, SERVICE_TURN_OFF_ALL_ZONES)
    hass.services.async_remove(DOMAIN, SERVICE_BOOST_ALL_ZONES)
    hass.services.async_remove(DOMAIN, SERVICE_SET_TIMER)
