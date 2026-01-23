"""Platform for Tado climate entities."""

from __future__ import annotations

from typing import TYPE_CHECKING


from .climate_entity import TadoWaterHeater

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
    """Set up Tado climate entities.

    We only create climate entities for zones where HomeKit doesn't provide one:
    - HOT_WATER: No HomeKit equivalent, so we provide a climate entity
    - HEATING: HomeKit already provides climate entities, we inject features instead
    - AC: Future enhancement (currently using select entities for fan/swing)
    """
    coordinator: TadoDataUpdateCoordinator = entry.runtime_data

    entities: list[TadoWaterHeater] = []

    # Hot Water Climate Entities (no HomeKit equivalent exists)
    entities.extend(
        TadoWaterHeater(coordinator, zone.id, zone.name)
        for zone in coordinator.zones_meta.values()
        if zone.type == "HOT_WATER"
    )

    async_add_entities(entities)
