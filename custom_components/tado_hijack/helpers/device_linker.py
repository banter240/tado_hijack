"""Helper to link Tado Hijack entities to existing HomeKit devices."""

from __future__ import annotations

from typing import cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .logging_utils import get_redacted_logger

_LOGGER = get_redacted_logger(__name__)


def get_homekit_identifiers(
    hass: HomeAssistant, serial_no: str
) -> set[tuple[str, str]] | None:
    """Find a device in the registry matching the serial number and return its identifiers.

    This allows us to link our entities to the existing HomeKit device
    instead of creating a duplicate one.
    """
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
