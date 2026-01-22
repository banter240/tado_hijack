"""Helper to link Tado Hijack entities to existing HomeKit devices."""

from __future__ import annotations

from typing import cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .logging_utils import get_redacted_logger

_LOGGER = get_redacted_logger(__name__)


def get_homekit_identifiers(
    hass: HomeAssistant, serial_no: str
) -> set[tuple[str, str]] | None:
    """Find a device in the registry matching the serial number and return its identifiers."""
    registry = dr.async_get(hass)

    # Search for a device with matching manufacturer and serial number
    for device in registry.devices.values():
        if (
            device.manufacturer
            and "tado" in device.manufacturer.lower()
            and device.serial_number == serial_no
        ):
            _LOGGER.debug(
                "Found existing HomeKit/Tado device for serial %s: %s",
                serial_no,
                device.name,
            )
            return cast(set[tuple[str, str]], device.identifiers)

    return None


def get_climate_entity_id(hass: HomeAssistant, serial_no: str) -> str | None:
    """Find the climate entity ID associated with a Tado device serial via HomeKit."""
    d_registry = dr.async_get(hass)
    e_registry = er.async_get(hass)

    target_device = next(
        (
            device
            for device in d_registry.devices.values()
            if (
                device.manufacturer
                and "tado" in device.manufacturer.lower()
                and device.serial_number == serial_no
            )
        ),
        None,
    )
    if not target_device:
        return None

    # 2. Find the Climate Entity for this Device
    entries = er.async_entries_for_device(e_registry, target_device.id)
    return next(
        (str(entry.entity_id) for entry in entries if entry.domain == "climate"),
        None,
    )
