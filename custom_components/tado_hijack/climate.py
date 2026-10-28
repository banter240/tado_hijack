"""Platform for Tado climate entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .climate_entity import TadoAirConditioning, TadoHeating
from .const import GEN_X, ZONE_TYPE_AIR_CONDITIONING, ZONE_TYPE_HEATING
from .helpers.discovery import yield_zones

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import TadoDataUpdateCoordinator


def cloud_climate_entities(
    coordinator: TadoDataUpdateCoordinator,
) -> list[TadoHeating | TadoAirConditioning]:
    """Return cloud climate entities."""
    if coordinator.generation == GEN_X:
        if not coordinator.full_cloud_mode:
            return []
        return [
            TadoHeating(coordinator, zone.id, zone.name)
            for zone in yield_zones(coordinator)
        ]

    entities: list[TadoHeating | TadoAirConditioning] = [
        TadoAirConditioning(coordinator, zone.id, zone.name)
        for zone in yield_zones(coordinator, {ZONE_TYPE_AIR_CONDITIONING})
    ]
    if coordinator.full_cloud_mode:
        entities.extend(
            TadoHeating(coordinator, zone.id, zone.name)
            for zone in yield_zones(coordinator, {ZONE_TYPE_HEATING})
        )
    return entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tado climate entities."""
    coordinator: TadoDataUpdateCoordinator = entry.runtime_data
    async_add_entities(cloud_climate_entities(coordinator))
    coordinator.local_proxy.register("climate", async_add_entities)
