"""Helper for setting up Tado generic entities."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ..const import (
    ZONE_TYPE_AIR_CONDITIONING,
    ZONE_TYPE_HEATING,
    ZONE_TYPE_HOT_WATER,
)
from ..definitions import ENTITY_DEFINITIONS
from .discovery import yield_devices, yield_zones
from .logging_utils import get_redacted_logger

if TYPE_CHECKING:
    from .. import TadoConfigEntry
    from ..coordinator import TadoDataUpdateCoordinator
    from ..models import TadoEntityDefinition

_LOGGER = get_redacted_logger(__name__)

# Default supported zone types if not specified
ALL_ZONE_TYPES = {
    ZONE_TYPE_HEATING,
    ZONE_TYPE_AIR_CONDITIONING,
    ZONE_TYPE_HOT_WATER,
}

# Zone types not yet supported on Tado X - entities limited to these are skipped.
# Remove a type from this set once it is implemented for Tado X.
_TADOX_UNSUPPORTED_ZONE_TYPES = {ZONE_TYPE_HOT_WATER, ZONE_TYPE_AIR_CONDITIONING}


async def async_setup_generic_platform(
    hass: HomeAssistant,
    entry: TadoConfigEntry,
    async_add_entities: AddEntitiesCallback,
    platform: str,
    entity_classes: dict[str, Any],  # scope -> class
) -> None:
    """Set up generic Tado entities for a specific platform."""
    coordinator: TadoDataUpdateCoordinator = entry.runtime_data
    entities: list[Any] = []

    for d in ENTITY_DEFINITIONS:
        if d["platform"] != platform:
            continue

        if (
            gens := d.get("supported_generations")
        ) and coordinator.generation not in gens:
            continue

        scope = d["scope"]
        cls = entity_classes.get(scope)
        if not cls:
            continue

        if scope == "home":
            _process_home_scope(coordinator, d, cls, entities)
        elif scope == "zone":
            _process_zone_scope(coordinator, d, cls, entities)
        elif scope == "device":
            _process_device_scope(coordinator, d, cls, entities)
        elif scope == "bridge":
            _process_bridge_scope(coordinator, d, cls, entities)

    if entities:
        _LOGGER.debug(
            "Adding %d entities for platform %s",
            len(entities),
            platform,
        )
        async_add_entities(entities)


def _process_home_scope(
    coordinator: TadoDataUpdateCoordinator,
    definition: TadoEntityDefinition,
    cls: Any,
    entities: list[Any],
) -> None:
    """Process entities with Home scope."""
    if (is_supported := definition.get("is_supported_fn")) and not is_supported(
        coordinator
    ):
        return
    entities.append(cls(coordinator, definition))


def _process_zone_scope(
    coordinator: TadoDataUpdateCoordinator,
    definition: TadoEntityDefinition,
    cls: Any,
    entities: list[Any],
) -> None:
    """Process entities with Zone scope - generation-aware dispatcher."""
    from ..const import GEN_X

    if coordinator.generation == GEN_X:
        _process_zone_scope_tadox(coordinator, definition, cls, entities)
    else:
        _process_zone_scope_v3(coordinator, definition, cls, entities)


def _process_zone_scope_v3(
    coordinator: TadoDataUpdateCoordinator,
    definition: TadoEntityDefinition,
    cls: Any,
    entities: list[Any],
) -> None:
    """Process zone entities for v3 Classic (filtered by zone type, uses zone.id/zone.name)."""
    supported_types = definition.get("supported_zone_types") or ALL_ZONE_TYPES
    for zone in yield_zones(coordinator, supported_types):
        if (is_supported := definition.get("is_supported_fn")) and not is_supported(
            coordinator, zone.id
        ):
            continue
        entities.append(cls(coordinator, definition, zone.id, zone.name))


def _process_zone_scope_tadox(
    coordinator: TadoDataUpdateCoordinator,
    definition: TadoEntityDefinition,
    cls: Any,
    entities: list[Any],
) -> None:
    """Process zone entities for Tado X (all rooms, uses room.room_id/room.room_name).

    Entities limited to HOT_WATER or AIR_CONDITIONING zone types are skipped
    until those zone types are implemented for Tado X.
    """
    supported_types = definition.get("supported_zone_types")
    if supported_types and supported_types.issubset(_TADOX_UNSUPPORTED_ZONE_TYPES):
        # Not yet implemented for Tado X (e.g. HOT_WATER-only, AC-only).
        return

    for room in yield_zones(coordinator):
        if (is_supported := definition.get("is_supported_fn")) and not is_supported(
            coordinator, room.room_id
        ):
            continue
        entities.append(cls(coordinator, definition, room.room_id, room.room_name))


def _process_device_scope(
    coordinator: TadoDataUpdateCoordinator,
    definition: TadoEntityDefinition,
    cls: Any,
    entities: list[Any],
) -> None:
    """Process entities with Device scope."""
    required_caps = definition.get("required_device_capabilities")
    caps_args = required_caps or []

    # Process devices across all zone types
    for device, zone_id in yield_devices(coordinator, ALL_ZONE_TYPES, *caps_args):
        if (is_supported := definition.get("is_supported_fn")) and not is_supported(
            coordinator, device.serial_no
        ):
            continue
        entities.append(cls(coordinator, definition, device, zone_id))


def _process_bridge_scope(
    coordinator: TadoDataUpdateCoordinator,
    definition: TadoEntityDefinition,
    cls: Any,
    entities: list[Any],
) -> None:
    """Process entities with Bridge scope."""
    for bridge in coordinator.bridges:
        if (is_supported := definition.get("is_supported_fn")) and not is_supported(
            coordinator, bridge.serial_no
        ):
            continue
        entities.append(cls(coordinator, definition, bridge))
