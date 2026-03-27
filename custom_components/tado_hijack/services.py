"""Services for Tado Hijack."""

from __future__ import annotations

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
    SERVICE_ADD_METER_READING,
    SERVICE_BOOST_ALL_ZONES,
    SERVICE_MANUAL_POLL,
    SERVICE_RESUME_ALL_SCHEDULES,
    SERVICE_SET_MODE,
    SERVICE_SET_MODE_ALL,
    SERVICE_SET_WATER_HEATER_MODE,
    SERVICE_TURN_OFF_ALL_ZONES,
    ZONE_TYPE_HOT_WATER,
)
from .helpers.logging_utils import get_redacted_logger

if TYPE_CHECKING:
    from .coordinator import TadoDataUpdateCoordinator

_LOGGER = get_redacted_logger(__name__)


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

    operation_mode = call.data.get("hvac_mode") or call.data.get("operation_mode")
    if operation_mode:
        operation_mode = operation_mode.lower()

    return {
        "duration": duration_minutes,
        "overlay": overlay_mode,
        "operation_mode": operation_mode,
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
    # 1. 'auto' (Resume Schedule) validation
    if operation_mode == "auto":
        # Block temperature for auto, but ignore duration/overlay (redundant in UI)
        if temperature is not None:
            raise ServiceValidationError(
                f"When setting {'water heater' if is_water_heater else 'mode'} to 'auto' (Resume Schedule), "
                "you cannot provide a target temperature. The smart schedule will take full control."
            )
        return

    # 2. 'off' validation
    if operation_mode == "off":
        # Block temperature for off, but ignore duration/overlay
        if temperature is not None:
            raise ServiceValidationError(
                f"When setting {'water heater' if is_water_heater else 'mode'} to 'off', "
                "you cannot provide a target temperature."
            )
        return

    # 3. 'heat' validation
    # No mandatory temperature check here because the coordinator handles fallbacks.
    return


def _get_all_coordinators(hass: HomeAssistant) -> list[TadoDataUpdateCoordinator]:
    """Return all active TadoDataUpdateCoordinators."""
    return [
        entry.runtime_data
        for entry in hass.config_entries.async_entries(DOMAIN)
        if hasattr(entry, "runtime_data") and entry.runtime_data is not None
    ]


def _get_coordinators_for_call(
    hass: HomeAssistant, call: ServiceCall
) -> list[TadoDataUpdateCoordinator]:
    """Get targeted coordinators from service call."""
    if not (config_entry_id := call.data.get("config_entry")):
        return _get_all_coordinators(hass)
    if isinstance(config_entry_id, list):
        coords = []
        for entry_id in config_entry_id:
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry and hasattr(entry, "runtime_data") and entry.runtime_data:
                coords.append(entry.runtime_data)
        return coords
    else:
        entry = hass.config_entries.async_get_entry(config_entry_id)
        if entry and hasattr(entry, "runtime_data") and entry.runtime_data:
            return [entry.runtime_data]
    return []


async def async_setup_services(hass: HomeAssistant) -> None:  # noqa: C901
    """Set up the services for Tado Hijack."""
    if hass.data.get(f"{DOMAIN}_services_registered"):
        return
    hass.data[f"{DOMAIN}_services_registered"] = True

    async def handle_manual_poll(call: ServiceCall) -> None:
        """Service to force refresh."""
        refresh_type = call.data.get("refresh_type", "all")
        entity_id = call.data.get("entity_id")

        if entity_id:
            for coord in _get_all_coordinators(hass):
                if coord.get_zone_id_from_entity(entity_id) is not None:
                    _LOGGER.debug(
                        "Service call: manual_poll (type: %s, entity: %s)",
                        refresh_type,
                        entity_id,
                    )
                    await coord.async_targeted_fetch(refresh_type, entity_id)
                    return
            _LOGGER.warning("Could not resolve Tado zone for entity %s", entity_id)
        else:
            _LOGGER.debug("Service call: manual_poll (type: %s)", refresh_type)
            for coord in _get_coordinators_for_call(hass, call):
                await coord.async_manual_poll(refresh_type)

    async def handle_resume_schedules(call: ServiceCall) -> None:
        """Service to resume all schedules."""
        _LOGGER.debug("Service call: resume_all_schedules")
        for coord in _get_coordinators_for_call(hass, call):
            await coord.async_resume_all_schedules()

    async def handle_turn_off_all(call: ServiceCall) -> None:
        """Service to turn off all zones."""
        _LOGGER.debug("Service call: turn_off_all_zones")
        for coord in _get_coordinators_for_call(hass, call):
            await coord.async_turn_off_all_zones()

    async def handle_boost_all(call: ServiceCall) -> None:
        """Service to boost all zones."""
        _LOGGER.debug("Service call: boost_all_zones")
        for coord in _get_coordinators_for_call(hass, call):
            await coord.async_boost_all_zones()

    async def handle_set_mode(call: ServiceCall) -> None:
        """Service to set a manual mode (batched)."""
        entity_ids = call.data.get("entity_id")
        if not entity_ids:
            return

        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]

        params = _parse_service_call_data(call)

        coord_map: dict[TadoDataUpdateCoordinator, list[int]] = {}
        for entity_id in entity_ids:
            resolved = False
            for coord in _get_all_coordinators(hass):
                if (zone_id := coord.get_zone_id_from_entity(entity_id)) is not None:
                    if coord not in coord_map:
                        coord_map[coord] = []
                    coord_map[coord].append(zone_id)
                    resolved = True
                    break
            if not resolved:
                _LOGGER.warning("Could not resolve Tado zone for entity %s", entity_id)

        for coord, zone_ids in coord_map.items():
            if zone_ids:
                await _execute_set_mode(coord, zone_ids, params)

    async def handle_set_mode_all(call: ServiceCall) -> None:
        """Service to set a manual overlay for all heating/AC zones (batched)."""
        params = _parse_service_call_data(call)
        for coord in _get_coordinators_for_call(hass, call):
            zone_ids = coord.get_active_zones(
                include_heating=call.data.get("include_heating", True),
                include_ac=call.data.get("include_ac", False),
            )
            if not zone_ids:
                _LOGGER.warning(
                    "No zones found for set_mode_all_zones in home %s", coord.home_name
                )
                continue
            await _execute_set_mode(coord, zone_ids, params)

    async def handle_set_water_heater_mode(call: ServiceCall) -> None:
        """Service to set a mode for water heater entities."""
        entity_ids = call.data.get("entity_id")
        if not entity_ids:
            return

        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]

        params = _parse_service_call_data(call)
        operation_mode = params["operation_mode"]
        temperature = params["temperature"]
        duration = params["duration"]
        overlay_mode = params["overlay"]
        refresh_after = params["refresh_after"]

        _validate_service_params(
            operation_mode, temperature, duration, overlay_mode, is_water_heater=True
        )

        coord_map: dict[TadoDataUpdateCoordinator, list[int]] = {}
        for entity_id in entity_ids:
            resolved = False
            for coord in _get_all_coordinators(hass):
                if (zone_id := coord.get_zone_id_from_entity(entity_id)) is not None:
                    if coord not in coord_map:
                        coord_map[coord] = []
                    coord_map[coord].append(zone_id)
                    resolved = True
                    break
            if not resolved:
                _LOGGER.warning("Could not resolve Tado zone for entity %s", entity_id)

        for coord, zone_ids in coord_map.items():
            for zone_id in zone_ids:
                if operation_mode == "auto":
                    await coord.async_set_hot_water_auto(
                        zone_id, refresh_after=refresh_after, ignore_global_config=True
                    )
                    continue

                if operation_mode == "off":
                    await coord.async_set_zone_overlay(
                        zone_id=zone_id,
                        power=POWER_OFF,
                        duration=duration,
                        overlay_type=ZONE_TYPE_HOT_WATER,
                        overlay_mode=overlay_mode,
                        refresh_after=refresh_after,
                    )
                    continue

                if operation_mode == "heat":
                    final_temp = (
                        round(float(temperature)) if temperature is not None else None
                    )
                    await coord.async_set_zone_overlay(
                        zone_id=zone_id,
                        power=POWER_ON,
                        temperature=final_temp,
                        duration=duration,
                        overlay_type=ZONE_TYPE_HOT_WATER,
                        overlay_mode=overlay_mode,
                        refresh_after=refresh_after,
                    )

    async def handle_add_meter_reading(call: ServiceCall) -> None:
        """Service to add a meter reading."""
        reading = call.data.get("reading")
        if reading is None:
            return

        coordinators = _get_coordinators_for_call(hass, call)
        if not coordinators:
            _LOGGER.warning("No Tado config entry specified for add_meter_reading")
            return

        _LOGGER.debug("Service call: add_meter_reading (%s)", reading)
        for coord in coordinators:
            await coord.async_add_meter_reading(reading)

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
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_METER_READING, handle_add_meter_reading
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

    _validate_service_params(operation_mode, temperature, duration, overlay_mode)

    if operation_mode == "auto":
        for zone_id in zone_ids:
            await coordinator.async_set_zone_auto(
                zone_id, refresh_after=refresh_after, ignore_global_config=True
            )
        return

    power = POWER_OFF if operation_mode == "off" else POWER_ON

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
    """Unload Tado Hijack services if no active entries remain."""
    if any(
        hasattr(e, "runtime_data") and e.runtime_data is not None
        for e in hass.config_entries.async_entries(DOMAIN)
    ):
        return

    hass.services.async_remove(DOMAIN, SERVICE_MANUAL_POLL)
    hass.services.async_remove(DOMAIN, SERVICE_RESUME_ALL_SCHEDULES)
    hass.services.async_remove(DOMAIN, SERVICE_TURN_OFF_ALL_ZONES)
    hass.services.async_remove(DOMAIN, SERVICE_BOOST_ALL_ZONES)
    hass.services.async_remove(DOMAIN, SERVICE_SET_MODE)
    hass.services.async_remove(DOMAIN, SERVICE_SET_MODE_ALL)
    hass.services.async_remove(DOMAIN, SERVICE_SET_WATER_HEATER_MODE)
    hass.services.async_remove(DOMAIN, SERVICE_ADD_METER_READING)
    hass.data.pop(f"{DOMAIN}_services_registered", None)
