"""Button platform for Tado Hijack."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import (
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
