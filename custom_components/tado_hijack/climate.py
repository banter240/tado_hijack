"""Platform for Tado climate entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .climate_entity import TadoAirConditioning, TadoWaterHeater
from .const import ZONE_TYPE_AIR_CONDITIONING, ZONE_TYPE_HOT_WATER

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import TadoDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tado climate entities."""
    coordinator: TadoDataUpdateCoordinator = entry.runtime_data

    entities: list[TadoWaterHeater | TadoAirConditioning] = []

    entities.extend(
        TadoWaterHeater(coordinator, zone.id, zone.name)
        for zone in coordinator.zones_meta.values()
        if zone.type == ZONE_TYPE_HOT_WATER
    )

    entities.extend(
        TadoAirConditioning(coordinator, zone.id, zone.name)
        for zone in coordinator.zones_meta.values()
        if zone.type == ZONE_TYPE_AIR_CONDITIONING
    )

    async_add_entities(entities)
