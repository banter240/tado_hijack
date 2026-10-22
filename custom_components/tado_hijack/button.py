"""Button platform for Tado Hijack."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import TADOX_VIRTUAL_HOT_WATER_ZONE_ID
from .entity import (
    TadoDeviceEntity,
    TadoGenericEntityMixin,
    TadoHomeEntity,
    TadoHotWaterZoneEntity,
    TadoZoneEntity,
)
from .helpers.entity_setup import async_setup_generic_platform
from .helpers.logging_utils import get_redacted_logger
from .helpers.schedule import schedule_zone_names
from .models import TadoEntityDefinition

if TYPE_CHECKING:
    from . import TadoConfigEntry
    from .coordinator import TadoDataUpdateCoordinator

_LOGGER = get_redacted_logger(__name__)


async def async_setup_entry(
    hass: Any,
    entry: TadoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tado buttons based on a config entry."""
    await async_setup_generic_platform(
        hass,
        entry,
        async_add_entities,
        "button",
        {
            "home": TadoGenericHomeButton,
            "zone": TadoGenericZoneButton,
            "device": TadoGenericDeviceButton,
        },
    )
    coordinator: TadoDataUpdateCoordinator = entry.runtime_data
    zone_name = schedule_zone_names(coordinator).get(TADOX_VIRTUAL_HOT_WATER_ZONE_ID)
    if zone_name is not None:
        async_add_entities(
            [
                TadoXHotWaterPlanButton(
                    coordinator, TADOX_VIRTUAL_HOT_WATER_ZONE_ID, zone_name
                )
            ]
        )


class TadoXHotWaterPlanButton(TadoHotWaterZoneEntity, ButtonEntity):
    """Fetch the Tado X hot-water week. Same device as the water heater."""

    _attr_translation_key = "refresh_zone_plan"
    _attr_icon = "mdi:calendar-sync"

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        zone_id: int,
        zone_name: str,
    ) -> None:
        super().__init__(coordinator, "refresh_zone_plan", zone_id, zone_name)
        entry_id = coordinator.config_entry.entry_id if coordinator.config_entry else ""
        self._attr_unique_id = f"{entry_id}_refresh_zone_plan_{zone_id}"

    async def async_press(self) -> None:
        """Queue one debounced GET of the hot-water week."""
        await self.tado_coordinator.async_refresh_zone_plan(self._zone_id)


class TadoGenericHomeButton(TadoHomeEntity, TadoGenericEntityMixin, ButtonEntity):
    """Generic button for Home scope."""

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        definition: TadoEntityDefinition,
    ) -> None:
        """Initialize the generic home button."""
        TadoHomeEntity.__init__(
            self, coordinator, cast(str, definition["translation_key"])
        )
        TadoGenericEntityMixin.__init__(self, definition)
        self._set_entity_id("button", definition["key"])

    async def async_press(self) -> None:
        """Handle the button press."""
        await self._async_press()


class TadoGenericZoneButton(TadoZoneEntity, TadoGenericEntityMixin, ButtonEntity):
    """Generic button for Zone scope."""

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        definition: TadoEntityDefinition,
        zone_id: int,
        zone_name: str,
    ) -> None:
        """Initialize the generic zone button."""
        TadoZoneEntity.__init__(
            self,
            coordinator,
            cast(str, definition["translation_key"]),
            zone_id,
            zone_name,
        )
        TadoGenericEntityMixin.__init__(self, definition)

    async def async_press(self) -> None:
        """Handle the button press."""
        await self._async_press()


class TadoGenericDeviceButton(TadoDeviceEntity, TadoGenericEntityMixin, ButtonEntity):
    """Generic button for Device scope."""

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        definition: TadoEntityDefinition,
        device: Any,
        zone_id: int,
    ) -> None:
        """Initialize the generic device button."""
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

    async def async_press(self) -> None:
        """Handle the button press."""
        await self._async_press()
