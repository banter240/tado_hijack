"""Support for Tado temperature offset numbers."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any, cast

from homeassistant.components.number import (
    NumberEntity,
    NumberMode,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .entity import (
    TadoDefinitionMixin,
    TadoDeviceEntity,
    TadoOptimisticMixin,
    TadoZoneEntity,
)
from .helpers.entity_setup import async_setup_generic_platform
from .models import TadoEntityDefinition

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .coordinator import TadoDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Tado number platform."""
    await async_setup_generic_platform(
        hass,
        entry,
        async_add_entities,
        "number",
        {
            "device": TadoGenericDeviceNumber,
            "zone": TadoGenericZoneNumber,
        },
    )


class TadoOptimisticNumber(TadoOptimisticMixin, RestoreEntity, NumberEntity):
    """Base class for optimistic numbers with restore support."""

    _restored_value: float | None = None

    async def async_added_to_hass(self) -> None:
        """Restore previous state on startup."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state not in (None, "unknown", "unavailable"):
                with contextlib.suppress(ValueError, TypeError):
                    self._restored_value = float(last_state.state)

    @property
    def native_value(self) -> float | int | None:
        """Return the current value (optimistic > actual > restored)."""
        val = self._resolve_state()
        if val is None:
            val = self._restored_value

        if (
            val is not None
            and getattr(self, "_attr_suggested_display_precision", None) == 0
        ):
            return round(float(val))

        return float(val) if val is not None else None


class TadoGenericNumberMixin(TadoDefinitionMixin):
    """Mixin for generic number logic."""

    coordinator: TadoDataUpdateCoordinator
    _tado_entity_id: Any

    def __init__(self, definition: TadoEntityDefinition) -> None:
        """Initialize generic number properties."""
        TadoDefinitionMixin.__init__(self, definition)
        self._attr_mode = NumberMode.BOX
        self._attr_optimistic_key = definition.get("optimistic_key")
        self._attr_optimistic_scope = definition.get("optimistic_scope")

        if (min_val := definition.get("min_value")) is not None:
            self._attr_native_min_value = min_val
        if (max_val := definition.get("max_value")) is not None:
            self._attr_native_max_value = max_val
        if step := definition.get("step"):
            self._attr_native_step = step
        if (precision := definition.get("suggested_display_precision")) is not None:
            self._attr_suggested_display_precision = precision

    def _update_dynamic_ranges(self) -> None:
        """Update min/max/step if dynamic functions are provided."""
        ctx_id = self._tado_entity_id
        if min_fn := self._definition.get("min_fn"):
            self._attr_native_min_value = min_fn(self.coordinator, ctx_id)
        if max_fn := self._definition.get("max_fn"):
            self._attr_native_max_value = max_fn(self.coordinator, ctx_id)
        if step_fn := self._definition.get("step_fn"):
            self._attr_native_step = step_fn(self.coordinator, ctx_id)

    def _get_actual_value(self) -> float | None:
        """Get actual value via value_fn."""
        args = [self.coordinator]
        if (ctx_id := self._tado_entity_id) is not None:
            args.append(ctx_id)

        val = self._definition["value_fn"](*args)
        return float(val) if val is not None else None

    async def async_set_native_value(self, value: float) -> None:
        """Set native value via set_fn."""
        if set_fn := self._definition.get("set_fn"):
            args: list[Any] = [self.coordinator]
            if (ctx_id := self._tado_entity_id) is not None:
                args.append(ctx_id)
            args.append(value)
            await set_fn(*args)


class TadoGenericDeviceNumber(
    TadoGenericNumberMixin, TadoOptimisticNumber, TadoDeviceEntity
):
    """Generic number for Device scope."""

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        definition: TadoEntityDefinition,
        device: Any,
        zone_id: int,
    ) -> None:
        """Initialize the generic device number."""
        TadoOptimisticNumber.__init__(self)
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
        TadoGenericNumberMixin.__init__(self, definition)
        self._update_dynamic_ranges()


class TadoGenericZoneNumber(
    TadoGenericNumberMixin, TadoOptimisticNumber, TadoZoneEntity
):
    """Generic number for Zone scope."""

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        definition: TadoEntityDefinition,
        zone_id: int,
        zone_name: str,
    ) -> None:
        """Initialize the generic zone number."""
        TadoOptimisticNumber.__init__(self)
        TadoZoneEntity.__init__(
            self,
            coordinator,
            cast(str, definition["translation_key"]),
            zone_id,
            zone_name,
        )
        TadoGenericNumberMixin.__init__(self, definition)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_zone_{zone_id}_{self._get_unique_id_suffix()}"
        self._update_dynamic_ranges()

    async def async_added_to_hass(self) -> None:
        """Handle startup logic (restore + dynamic ranges)."""
        await TadoOptimisticNumber.async_added_to_hass(self)

        # Re-fetch ranges on startup if they might be dynamic
        if self._definition.get("min_fn") or self._definition.get("max_fn"):
            # Ensure capabilities are loaded for dynamic ranges (e.g. target_temp)
            await self.coordinator.async_get_capabilities(self._zone_id)
            self._update_dynamic_ranges()
            self.async_write_ha_state()
