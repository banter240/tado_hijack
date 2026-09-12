"""Gateway to link Tado Hijack entities to local HomeKit / Matter devices."""

from __future__ import annotations

from collections.abc import Callable, Iterator

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from ..const import GEN_X
from .device_link import identifier_pairs
from .logging_utils import get_redacted_logger
from .tadov3.device_link import matches_serial as matches_homekit
from .tadox.device_link import matches_serial as matches_matter

_LOGGER = get_redacted_logger(__name__)

_cache_built = False
_cached_devices: list[dr.DeviceEntry] = []


def _iter_registry_devices(
    registry: dr.DeviceRegistry,
) -> Iterator[dr.DeviceEntry]:
    """Yield DeviceEntry; iteration may return ids."""
    for item in registry.devices:
        device = registry.async_get(item) if isinstance(item, str) else item
        if device is not None:
            yield device


def invalidate_cache() -> None:
    """Invalidate the device cache, forcing rebuild on next access."""
    global _cache_built
    _cache_built = False
    _cached_devices.clear()
    _LOGGER.debug("Device linker cache invalidated")


def _all_devices(hass: HomeAssistant) -> list[dr.DeviceEntry]:
    """Return cached registry devices."""
    global _cache_built
    if _cache_built:
        return _cached_devices

    registry = dr.async_get(hass)
    _cached_devices.clear()
    _cached_devices.extend(_iter_registry_devices(registry))
    _cache_built = True
    _LOGGER.debug("Device cache built with %d devices", len(_cached_devices))
    return _cached_devices


def _owned_by(device: dr.DeviceEntry, entry_id: str) -> bool:
    """Return True if the device belongs to this config entry."""
    if getattr(device, "config_entry_id", None) == entry_id:
        return True
    entries = getattr(device, "config_entries", None)
    return bool(entries and entry_id in entries)


def _matcher_for(generation: str) -> Callable[[dr.DeviceEntry, str], bool]:
    """Return the generation-specific serial matcher."""
    return matches_matter if generation == GEN_X else matches_homekit


def _matching_devices(
    hass: HomeAssistant,
    serial_no: str,
    generation: str,
    *,
    exclude_entry_id: str | None = None,
) -> Iterator[dr.DeviceEntry]:
    """Yield local protocol devices that carry the cloud serial."""
    if not serial_no or not serial_no.strip():
        return
    matches = _matcher_for(generation)
    for device in _all_devices(hass):
        if exclude_entry_id and _owned_by(device, exclude_entry_id):
            continue
        if matches(device, serial_no):
            yield device


def get_local_device(
    hass: HomeAssistant,
    serial_no: str,
    generation: str,
    *,
    exclude_entry_id: str | None = None,
) -> dr.DeviceEntry | None:
    """Return a local HomeKit/Matter device matching the cloud serial."""
    return next(
        _matching_devices(
            hass, serial_no, generation, exclude_entry_id=exclude_entry_id
        ),
        None,
    )


def get_linked_device_identifiers(
    hass: HomeAssistant,
    serial_no: str,
    generation: str,
    *,
    exclude_entry_id: str | None = None,
) -> set[tuple[str, str]]:
    """Return identifiers of a linked local device, or empty set."""
    device = get_local_device(
        hass, serial_no, generation, exclude_entry_id=exclude_entry_id
    )
    return set() if device is None else set(identifier_pairs(device.identifiers))


def get_local_device_identifiers(
    hass: HomeAssistant, serial_no: str, generation: str
) -> set[tuple[str, str]] | None:
    """Find identifiers of a local Tado device matching the serial number."""
    device = get_local_device(hass, serial_no, generation)
    return None if device is None else set(identifier_pairs(device.identifiers))


get_homekit_identifiers = get_local_device_identifiers


def get_climate_entity_id(
    hass: HomeAssistant, serial_no: str, generation: str
) -> str | None:
    """Find a climate entity ID for a Tado device serial."""
    e_registry = er.async_get(hass)
    for device in _matching_devices(hass, serial_no, generation):
        entries = er.async_entries_for_device(e_registry, device.id)
        climate_id = next(
            (str(entry.entity_id) for entry in entries if entry.domain == "climate"),
            None,
        )
        if climate_id is not None:
            return climate_id
    return None
