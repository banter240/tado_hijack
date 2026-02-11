"""Binary sensor platform for Tado Hijack (Battery, Connectivity)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import (
    TadoBridgeEntity,
    TadoDeviceEntity,
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
