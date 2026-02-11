"""Sensor platform for Tado Hijack."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from homeassistant.components.sensor import (
    SensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ZONE_TYPE_HOT_WATER,
)
from .entity import (
    TadoGenericEntityMixin,
    TadoHomeEntity,
    TadoZoneEntity,
)
from .helpers.entity_setup import async_setup_generic_platform
from .helpers.logging_utils import get_redacted_logger
from .models import TadoEntityDefinition

if TYPE_CHECKING:
    from . import TadoConfigEntry
    from .coordinator import TadoDataUpdateCoordinator

_LOGGER = get_redacted_logger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TadoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tado sensors based on a config entry."""
    await async_setup_generic_platform(
        hass,
        entry,
        async_add_entities,
        "sensor",
        {
            "home": TadoGenericHomeSensor,
            "zone": TadoGenericZoneSensor,
        },
    )


class TadoGenericHomeSensor(TadoHomeEntity, TadoGenericEntityMixin, SensorEntity):
    """Generic sensor for Home scope."""

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        definition: TadoEntityDefinition,
    ) -> None:
        """Initialize the generic home sensor."""
        # TadoHomeEntity sets the entity_id based on the key
        TadoHomeEntity.__init__(
            self, coordinator, cast(str, definition["translation_key"])
        )
        TadoGenericEntityMixin.__init__(self, definition)
        self._set_entity_id("sensor", definition["key"])
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{self._get_unique_id_suffix()}"
        )


class TadoGenericZoneSensor(TadoZoneEntity, TadoGenericEntityMixin, SensorEntity):
    """Generic sensor for Zone scope."""

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        definition: TadoEntityDefinition,
        zone_id: int,
        zone_name: str,
    ) -> None:
        """Initialize the generic zone sensor."""
        trans_key = cast(str, definition["translation_key"])

        # Special handling for heating_power label
        if definition["key"] == "heating_power":
            zone = coordinator.zones_meta.get(zone_id)
            if zone and zone.type == ZONE_TYPE_HOT_WATER:
                trans_key = "hot_water_power"

        TadoZoneEntity.__init__(self, coordinator, trans_key, zone_id, zone_name)
        TadoGenericEntityMixin.__init__(self, definition)
