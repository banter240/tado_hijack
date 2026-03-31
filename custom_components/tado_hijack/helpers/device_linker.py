"""Helper to link Tado Hijack entities to existing HomeKit devices."""

from __future__ import annotations

from typing import cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .logging_utils import get_redacted_logger

_LOGGER = get_redacted_logger(__name__)

# Cache for device lookups (serial_no -> identifiers)
_device_cache: dict[str, set[tuple[str, str]] | None] = {}
_cache_built = False


def invalidate_cache() -> None:
    """Invalidate the device cache, forcing rebuild on next access."""
    global _cache_built
    _cache_built = False
    _device_cache.clear()
    _LOGGER.debug("Device linker cache invalidated")


def _build_device_cache(hass: HomeAssistant, force: bool = False) -> None:
    """Build device cache from registry."""
    global _cache_built
    if _cache_built and not force:
        return

    registry = dr.async_get(hass)
    _device_cache.clear()

    for device in registry.devices.values():
        if (
            device.manufacturer
            and "tado" in device.manufacturer.lower()
            and device.serial_number
        ):
            _device_cache[device.serial_number] = cast(
                set[tuple[str, str]], device.identifiers
            )

    _cache_built = True
    _LOGGER.debug("Device cache built with %d Tado devices", len(_device_cache))


def get_linked_device_identifiers(
    hass: HomeAssistant,
    serial_no: str,
    generation: str,
) -> set[tuple[str, str]]:
    """Get linked device identifiers for v3 (HomeKit) only.

    Tado X uses Matter which does not expose serial numbers — linking is not possible.
    """
    from ..const import GEN_X

    if generation == GEN_X:
        return set()

    ids = get_homekit_identifiers(hass, serial_no)
    return ids if ids is not None else set()


def get_homekit_identifiers(
    hass: HomeAssistant, serial_no: str
) -> set[tuple[str, str]] | None:
    """Find a HomeKit device in the registry matching the serial number.

    Uses a cache to avoid O(n*m) complexity during setup.
    """
    _build_device_cache(hass)
    return _device_cache.get(serial_no)


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

    entries = er.async_entries_for_device(e_registry, target_device.id)
    return next(
        (str(entry.entity_id) for entry in entries if entry.domain == "climate"),
        None,
    )
