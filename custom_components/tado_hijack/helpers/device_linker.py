"""Gateway to link Tado Hijack entities to local HomeKit / Matter devices."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from ..const import DOMAIN, GEN_X, bridge_display_name, bridge_model_name
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


def _device_for_identifier(
    registry: dr.DeviceRegistry,
    identifier: tuple[str, str],
    entry_id: str,
) -> dr.DeviceEntry | None:
    """Look up one device. Identifiers are unique only inside a config entry."""
    scoped = getattr(registry, "async_get_device_by_identifier", None)
    if scoped is not None:
        found = scoped(identifier, entry_id)
        return found if isinstance(found, dr.DeviceEntry) else None
    return registry.async_get_device(identifiers={identifier})


def _owned_by(device: dr.DeviceEntry, entry_id: str) -> bool:
    if hasattr(device, "config_entry_id"):
        owner: str | None = getattr(device, "config_entry_id", None)
        return owner == entry_id
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


def detach_home_from_local_bridges(
    hass: HomeAssistant,
    *,
    entry_id: str,
    home_key: str,
    bridge_serials: list[str],
    generation: str,
) -> None:
    """Take bridge serials and HomeKit ids off the home device.

    The home device used to claim the Internet Bridge. While it still holds
    that serial or the HomeKit accessory id, bridge entities cannot attach
    to the real bridge and no bridge device shows up for this integration.
    """
    if not bridge_serials:
        return
    registry = dr.async_get(hass)
    home_identifier = (DOMAIN, home_key)
    home = _device_for_identifier(registry, home_identifier, entry_id)
    if home is None:
        return

    drop = {(DOMAIN, serial) for serial in bridge_serials}
    for serial in bridge_serials:
        local = get_local_device(hass, serial, generation, exclude_entry_id=entry_id)
        if local is not None:
            drop.update(identifier_pairs(local.identifiers))
    drop.discard(home_identifier)

    kept = set(identifier_pairs(home.identifiers)) - drop
    kept.add(home_identifier)
    serial_is_bridge = home.serial_number in set(bridge_serials)
    if kept == set(identifier_pairs(home.identifiers)) and not serial_is_bridge:
        return

    registry.async_update_device(
        home.id,
        new_identifiers=kept,
        serial_number=None if serial_is_bridge else home.serial_number,
    )
    _LOGGER.info(
        "Released %d bridge identifier(s) from the home device",
        len(drop),
    )


def retire_empty_home_device(
    hass: HomeAssistant,
    *,
    entry_id: str,
    home_key: str,
) -> None:
    if not home_key:
        return
    registry = dr.async_get(hass)
    home = _device_for_identifier(registry, (DOMAIN, home_key), entry_id)
    if home is None:
        return
    if er.async_entries_for_device(
        er.async_get(hass), home.id, include_disabled_entities=True
    ):
        return
    registry.async_remove_device(home.id)
    _LOGGER.debug("Removed empty home device %s", home_key)


def ensure_bridge_devices(
    hass: HomeAssistant,
    *,
    entry_id: str,
    bridges: list[Any],
) -> None:
    """Register each bridge-scoped device, even when HomeKit or Matter has one.

    The empty Hijack device is the proof the device was registered. Entities
    link onto the HomeKit or Matter device themselves when the serial matches.
    """
    registry = dr.async_get(hass)
    for bridge in bridges:
        serial = getattr(bridge, "serial_no", None)
        if not serial:
            continue
        serial = str(serial)
        short = getattr(bridge, "short_serial_no", None) or serial[-4:]
        device_type = getattr(bridge, "device_type", None)
        registry.async_get_or_create(
            config_entry_id=entry_id,
            identifiers={(DOMAIN, serial)},
            name=bridge_display_name(device_type, short),
            manufacturer="Tado",
            model=bridge_model_name(device_type),
            sw_version=getattr(bridge, "current_fw_version", None),
            serial_number=serial,
        )


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
