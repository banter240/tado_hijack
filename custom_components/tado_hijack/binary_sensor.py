"""Binary sensor platform for Tado Hijack (Battery, Connectivity)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import GEN_X
from .entity import (
    TadoBridgeEntity,
    TadoDeviceEntity,
    TadoGenericEntityMixin,
    TadoHomeEntity,
    TadoHotWaterZoneEntity,
    TadoZoneEntity,
)
from .helpers.entity_setup import async_setup_generic_platform
from .helpers.logging_utils import get_redacted_logger
from .models import TadoEntityDefinition
from .water_heater import tadox_hot_water_zones

if TYPE_CHECKING:
    from . import TadoConfigEntry
    from .coordinator import TadoDataUpdateCoordinator

_LOGGER = get_redacted_logger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TadoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tado binary sensors."""
    await async_setup_generic_platform(
        hass,
        entry,
        async_add_entities,
        "binary_sensor",
        {
            "home": TadoGenericHomeBinarySensor,
            "zone": TadoGenericZoneBinarySensor,
            "device": TadoGenericDeviceBinarySensor,
            "bridge": TadoGenericBridgeBinarySensor,
        },
    )
    coordinator: TadoDataUpdateCoordinator = entry.runtime_data
    if coordinator.generation == GEN_X:
        async_add_entities(
            TadoXHotWaterScheduleBinarySensor(coordinator, zone_id, zone_name)
            for zone_id, zone_name in tadox_hot_water_zones(coordinator)
        )


class TadoXHotWaterScheduleBinarySensor(TadoHotWaterZoneEntity, BinarySensorEntity):
    """Tado X hot water schedule (on/off)."""

    _attr_translation_key = "hot_water_schedule"
    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        zone_id: int,
        zone_name: str,
    ) -> None:
        super().__init__(coordinator, "hot_water_schedule", zone_id, zone_name)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_hot_water_schedule_{zone_id}"
        )

    def _schedule_on(self) -> bool | None:
        state = self.coordinator.data.zone_states.get(str(self._zone_id))
        return getattr(state, "schedule_on", None) if state is not None else None

    @property
    def available(self) -> bool:
        return super().available and self._schedule_on() is not None

    @property
    def is_on(self) -> bool:
        return self._schedule_on() is True


class TadoGenericHomeBinarySensor(
    TadoHomeEntity, TadoGenericEntityMixin, BinarySensorEntity
):
    """Generic binary sensor for Home scope."""

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        definition: TadoEntityDefinition,
    ) -> None:
        """Initialize the generic home binary sensor."""
        TadoHomeEntity.__init__(
            self, coordinator, cast(str, definition["translation_key"])
        )
        TadoGenericEntityMixin.__init__(self, definition)
        self._set_entity_id("binary_sensor", definition["key"])
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{self._get_unique_id_suffix()}"
        )


class TadoGenericZoneBinarySensor(
    TadoZoneEntity, TadoGenericEntityMixin, BinarySensorEntity
):
    """Generic binary sensor for Zone scope."""

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        definition: TadoEntityDefinition,
        zone_id: int,
        zone_name: str,
    ) -> None:
        """Initialize the generic zone binary sensor."""
        TadoZoneEntity.__init__(
            self,
            coordinator,
            cast(str, definition["translation_key"]),
            zone_id,
            zone_name,
        )
        TadoGenericEntityMixin.__init__(self, definition)


class TadoGenericDeviceBinarySensor(
    TadoDeviceEntity, TadoGenericEntityMixin, BinarySensorEntity
):
    """Generic binary sensor for Device scope."""

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        definition: TadoEntityDefinition,
        device: Any,
        zone_id: int,
    ) -> None:
        """Initialize the generic device binary sensor."""
        TadoDeviceEntity.__init__(
            self,
            coordinator,
            cast(str, definition["translation_key"]),
            device.serial_no,
            device.short_serial_no,
            device.device_type,
            zone_id,
            device.current_fw_version,
        )
        TadoGenericEntityMixin.__init__(self, definition)


class TadoGenericBridgeBinarySensor(
    TadoBridgeEntity, TadoGenericEntityMixin, BinarySensorEntity
):
    """Generic binary sensor for Bridge scope."""

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        definition: TadoEntityDefinition,
        bridge: Any,
    ) -> None:
        """Initialize the generic bridge binary sensor."""
        TadoBridgeEntity.__init__(
            self,
            coordinator,
            cast(str, definition["translation_key"]),
            bridge.serial_no,
        )
        TadoGenericEntityMixin.__init__(self, definition)
        self._set_entity_id("binary_sensor", definition["key"])
