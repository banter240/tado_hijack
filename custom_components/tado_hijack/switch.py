"""Switch platform for Tado Hijack."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import (
    TadoDefinitionMixin,
    TadoDeviceEntity,
    TadoGenericEntityMixin,
    TadoHomeEntity,
    TadoOptimisticMixin,
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
    """Set up Tado switches based on a config entry."""
    await async_setup_generic_platform(
        hass,
        entry,
        async_add_entities,
        "switch",
        {
            "home": TadoGenericHomeSwitch,
            "zone": TadoGenericZoneSwitch,
            "device": TadoGenericDeviceSwitch,
        },
    )


class TadoGenericSwitchMixin(TadoGenericEntityMixin):
    """Mixin for generic switch logic."""

    def __init__(self, definition: TadoEntityDefinition) -> None:
        """Initialize generic switch properties."""
        TadoDefinitionMixin.__init__(self, definition)
        self._attr_optimistic_key = definition.get("optimistic_key")
        self._attr_optimistic_scope = definition.get("optimistic_scope")

    def _get_optimistic_value(self) -> bool | None:
        """Handle inverted optimistic values."""
        if (
            opt := TadoOptimisticMixin._get_optimistic_value(
                cast(TadoOptimisticMixin, self)
            )
        ) is not None:
            if mapping := self._definition.get("optimistic_value_map"):
                return mapping.get(opt, None)
            return not bool(opt) if self._definition.get("is_inverted") else bool(opt)
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn switch on via turn_on_fn."""
        if turn_on_fn := self._definition.get("turn_on_fn"):
            args = [self.coordinator]
            if (ctx_id := self._tado_entity_id) is not None:
                args.append(ctx_id)
            await turn_on_fn(*args)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn switch off via turn_off_fn."""
        if turn_off_fn := self._definition.get("turn_off_fn"):
            args = [self.coordinator]
            if (ctx_id := self._tado_entity_id) is not None:
                args.append(ctx_id)
            await turn_off_fn(*args)


class TadoGenericHomeSwitch(
    TadoGenericSwitchMixin, TadoOptimisticMixin, TadoHomeEntity, SwitchEntity
):
    """Generic switch for Home scope."""

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        definition: TadoEntityDefinition,
    ) -> None:
        """Initialize the generic home switch."""
        TadoHomeEntity.__init__(
            self, coordinator, cast(str, definition["translation_key"])
        )
        TadoGenericSwitchMixin.__init__(self, definition)
        self._set_entity_id("switch", definition["key"])
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{self._get_unique_id_suffix()}"
        )

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return bool(self._resolve_state())


class TadoGenericZoneSwitch(
    TadoGenericSwitchMixin, TadoOptimisticMixin, TadoZoneEntity, SwitchEntity
):
    """Generic switch for Zone scope."""

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        definition: TadoEntityDefinition,
        zone_id: int,
        zone_name: str,
    ) -> None:
        """Initialize the generic zone switch."""
        TadoZoneEntity.__init__(
            self,
            coordinator,
            cast(str, definition["translation_key"]),
            zone_id,
            zone_name,
        )
        TadoGenericSwitchMixin.__init__(self, definition)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_zone_{zone_id}_{self._get_unique_id_suffix()}"

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return bool(self._resolve_state())


class TadoGenericDeviceSwitch(
    TadoGenericSwitchMixin, TadoOptimisticMixin, TadoDeviceEntity, SwitchEntity
):
    """Generic switch for Device scope."""

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        definition: TadoEntityDefinition,
        device: Any,
        zone_id: int,
    ) -> None:
        """Initialize the generic device switch."""
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
        TadoGenericSwitchMixin.__init__(self, definition)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{self._get_unique_id_suffix()}"
        )

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return bool(self._resolve_state())
