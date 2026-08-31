"""Helper to link Tado Hijack entities to existing local devices (HomeKit / Matter)."""

from __future__ import annotations

from typing import cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .logging_utils import get_redacted_logger

_LOGGER = get_redacted_logger(__name__)

_device_cache: dict[str, set[tuple[str, str]] | None] = {}
_cache_built = False


def _is_tado_device(device: dr.DeviceEntry) -> bool:
    """Return True if device.manufacturer identifies a Tado device."""
    return (
        isinstance(device.manufacturer, str) and "tado" in device.manufacturer.lower()
    )


def invalidate_cache() -> None:
    """Invalidate the device cache, forcing rebuild on next access."""
    global _cache_built
    _cache_built = False
    _device_cache.clear()
    _LOGGER.debug("Device linker cache invalidated")


def _build_device_cache(hass: HomeAssistant, force: bool = False) -> None:
    """Build device cache from registry by serial_number."""
    global _cache_built
    if _cache_built and not force:
        return

    registry = dr.async_get(hass)
    _device_cache.clear()

    for device in registry.devices.values():
        if _is_tado_device(device) and device.serial_number:
            _device_cache[device.serial_number] = cast(
                set[tuple[str, str]], device.identifiers
            )

    _cache_built = True
    _LOGGER.debug("Device cache built with %d Tado devices", len(_device_cache))


def get_linked_device_identifiers(
    hass: HomeAssistant,
    serial_no: str,
    _generation: str,
) -> set[tuple[str, str]]:
    """Return HA device identifiers matching a cloud serial, or empty set."""
    ids = get_local_device_identifiers(hass, serial_no)
    return ids if ids is not None else set()


def get_local_device_identifiers(
    hass: HomeAssistant, serial_no: str
) -> set[tuple[str, str]] | None:
    """Find a local Tado device in the registry matching the serial number."""
    _build_device_cache(hass)
    return _device_cache.get(serial_no)


get_homekit_identifiers = get_local_device_identifiers


def get_climate_entity_id(hass: HomeAssistant, serial_no: str) -> str | None:
    """Find a climate entity ID for a Tado device serial."""
    d_registry = dr.async_get(hass)
    e_registry = er.async_get(hass)

    target_device = next(
        (
            device
            for device in d_registry.devices.values()
            if _is_tado_device(device) and device.serial_number == serial_no
        ),
        None,
    )
    if not target_device:
        return None

    entries = er.async_entries_for_device(e_registry, target_device.id)
    return next(
        (str(entry.entity_id) for entry in entries if entry.domain == "climate"),
        None,
    )
