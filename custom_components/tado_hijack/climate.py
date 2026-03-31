"""Platform for Tado climate entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .climate_entity import TadoAirConditioning, TadoHeating
from .const import ZONE_TYPE_AIR_CONDITIONING, ZONE_TYPE_HEATING
from .helpers.discovery import yield_zones

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
    entities: list[TadoHeating | TadoAirConditioning] = []

    if coordinator.generation == "x":
        if coordinator.full_cloud_mode:
            entities.extend(
                TadoAirConditioning(coordinator, zone.id, zone.name)
                for zone in yield_zones(coordinator)
            )
    else:
        # v3 Classic
        entities.extend(
            TadoAirConditioning(coordinator, zone.id, zone.name)
            for zone in yield_zones(coordinator, {ZONE_TYPE_AIR_CONDITIONING})
        )
        if coordinator.full_cloud_mode:
            entities.extend(
                TadoHeating(coordinator, zone.id, zone.name)
                for zone in yield_zones(coordinator, {ZONE_TYPE_HEATING})
            )

    async_add_entities(entities)
