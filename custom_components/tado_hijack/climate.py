"""Platform for Tado climate entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .climate_entity import TadoAirConditioning
from .const import GEN_X, ZONE_TYPE_AIR_CONDITIONING
from .helpers.discovery import yield_zones

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import TadoDataUpdateCoordinator


def _setup_climate_entities_v3(
    coordinator: TadoDataUpdateCoordinator,
) -> list[TadoAirConditioning]:
    """Set up climate entities for v3 Classic (AC zones only).

    Hot water uses WaterHeaterEntity (water_heater.py), not ClimateEntity.
    """
    return [
        TadoAirConditioning(coordinator, zone.id, zone.name)
        for zone in yield_zones(coordinator, {ZONE_TYPE_AIR_CONDITIONING})
    ]


def _setup_climate_entities_tadox(
    coordinator: TadoDataUpdateCoordinator,
) -> list[TadoAirConditioning]:
    """Set up climate entities for Tado X (all rooms).

    Tado X rooms don't have a .type attribute (HopsRoomSnapshot).
    Matter integration controls room types, so we create entities for all rooms.
    """
    return []  # [TADO_X] Not yet supported


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tado climate entities."""
    coordinator: TadoDataUpdateCoordinator = entry.runtime_data

    entities = (
        _setup_climate_entities_tadox(coordinator)
        if coordinator.generation == GEN_X
        else _setup_climate_entities_v3(coordinator)
    )
    async_add_entities(entities)
