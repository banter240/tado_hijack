"""Support for Tado temperature offset numbers."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CAPABILITY_INSIDE_TEMP
from .entity import TadoDeviceEntity

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
    """Set up the Tado number platform."""
    coordinator: TadoDataUpdateCoordinator = entry.runtime_data

    entities: list[TadoNumberEntity] = []

    for zone in coordinator.zones_meta.values():
        if zone.type != "HEATING":
            continue
        entities.extend(
            TadoNumberEntity(
                coordinator,
                device.serial_no,
                device.short_serial_no,
                device.device_type,
                zone.id,
                device.current_fw_version,
            )
            for device in zone.devices
            if CAPABILITY_INSIDE_TEMP in (device.characteristics.capabilities or [])
        )
    if entities:
        async_add_entities(entities)


class TadoNumberEntity(TadoDeviceEntity, RestoreEntity, NumberEntity):
    """Representation of a Tado temperature offset number."""

    _attr_has_entity_name = True
    _attr_translation_key = "temperature_offset"
    _attr_native_min_value = -10.0
    _attr_native_max_value = 10.0
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        serial_no: str,
        short_serial: str,
        device_type: str,
        zone_id: int,
        fw_version: str | None = None,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(
            coordinator,
            "temperature_offset",
            serial_no,
            short_serial,
            device_type,
            zone_id,
            fw_version,
        )
        self.entity_description = NumberEntityDescription(
            key="temperature_offset",
            translation_key="temperature_offset",
            native_min_value=-10.0,
            native_max_value=10.0,
            native_step=0.1,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            mode=NumberMode.BOX,
        )
        self._attr_unique_id = f"{serial_no}_temperature_offset"
        self._restored_value: float | None = None

    async def async_added_to_hass(self) -> None:
        """Restore previous state on startup."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state not in (None, "unknown", "unavailable"):
                with contextlib.suppress(ValueError, TypeError):
                    self._restored_value = float(last_state.state)

    @property
    def native_value(self) -> float | None:
        """Return the temperature offset value."""
        if (
            opt_offset := self.coordinator.optimistic.get_offset(self._serial_no)
        ) is not None:
            return float(opt_offset)

        offsets: dict[str, Any] = self.coordinator.data.get("offsets", {})
        offset = offsets.get(self._serial_no)
        return float(offset.celsius) if offset is not None else self._restored_value

    async def async_set_native_value(self, value: float) -> None:
        """Set a new temperature offset."""
        await self.coordinator.async_set_temperature_offset(self._serial_no, value)
