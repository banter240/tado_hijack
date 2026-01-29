"""Support for Tado temperature offset numbers."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CAPABILITY_INSIDE_TEMP,
    TEMP_MAX_AC,
    TEMP_MAX_HOT_WATER_OVERRIDE,
    TEMP_MIN_AC,
    TEMP_MIN_HOT_WATER,
    ZONE_TYPE_AIR_CONDITIONING,
    ZONE_TYPE_HEATING,
)
from .entity import (
    TadoDeviceEntity,
    TadoOptimisticMixin,
    TadoZoneEntity,
)
from .helpers.discovery import yield_devices, yield_zones

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
    entities: list[NumberEntity] = [
        TadoNumberEntity(
            coordinator,
            device.serial_no,
            device.short_serial_no,
            device.device_type,
            zone_id,
            device.current_fw_version,
        )
        for device, zone_id in yield_devices(
            coordinator, {ZONE_TYPE_HEATING}, CAPABILITY_INSIDE_TEMP
        )
    ]
    # Zone Level Numbers
    for zone in yield_zones(
        coordinator, {ZONE_TYPE_HEATING, ZONE_TYPE_AIR_CONDITIONING}
    ):
        if zone.type == ZONE_TYPE_AIR_CONDITIONING:
            entities.append(
                TadoTargetTempNumberEntity(coordinator, zone.id, zone.name, zone.type)
            )
        elif zone.type == ZONE_TYPE_HEATING:
            entities.append(TadoAwayTempNumberEntity(coordinator, zone.id, zone.name))

    if entities:
        async_add_entities(entities)


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
    def native_value(self) -> float | None:
        """Return the current value (optimistic > actual > restored)."""
        if (val := self._resolve_state()) is not None:
            return float(val)

        return self._restored_value

    def _get_actual_value(self) -> float | None:
        raise NotImplementedError


class TadoNumberEntity(TadoDeviceEntity, TadoOptimisticNumber):
    """Representation of a Tado temperature offset number."""

    _attr_has_entity_name = True
    _attr_translation_key = "temperature_offset"
    _attr_native_min_value = -10.0
    _attr_native_max_value = 10.0
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX
    _attr_optimistic_key = "offset"
    _attr_optimistic_scope = "device"

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

    def _get_actual_value(self) -> float | None:
        offset = self.coordinator.data.offsets.get(self._serial_no)
        return float(offset.celsius) if offset is not None else None

    async def async_set_native_value(self, value: float) -> None:
        """Set a new temperature offset."""
        await self.coordinator.async_set_temperature_offset(self._serial_no, value)


class TadoAwayTempNumberEntity(TadoZoneEntity, TadoOptimisticNumber):
    """Representation of a Tado Away Temperature number."""

    _attr_has_entity_name = True
    _attr_translation_key = "away_temperature"
    _attr_native_min_value = 5.0
    _attr_native_max_value = 25.0
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX
    _attr_optimistic_key = "away_temp"
    _attr_optimistic_scope = "zone"

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        zone_id: int,
        zone_name: str,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, "away_temperature", zone_id, zone_name)
        self.entity_description = NumberEntityDescription(
            key="away_temperature",
            translation_key="away_temperature",
            native_min_value=5.0,
            native_max_value=25.0,
            native_step=0.1,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            mode=NumberMode.BOX,
        )
        self._attr_unique_id = f"zone_{zone_id}_away_temperature"

    def _get_actual_value(self) -> float | None:
        val = self.coordinator.data.away_config.get(self._zone_id)
        return float(val) if val is not None else None

    async def async_set_native_value(self, value: float) -> None:
        """Set a new away temperature."""
        await self.coordinator.async_set_away_temperature(self._zone_id, value)


class TadoTargetTempNumberEntity(TadoZoneEntity, TadoOptimisticNumber):
    """Representation of a Tado Target Temperature number (AC/HW)."""

    _attr_has_entity_name = True
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX
    _attr_optimistic_key = "temperature"
    _attr_optimistic_scope = "zone"

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        zone_id: int,
        zone_name: str,
        zone_type: str,
    ) -> None:
        """Initialize the target temperature entity."""
        key = "target_temperature"
        super().__init__(coordinator, key, zone_id, zone_name)
        self._zone_type = zone_type

        self._attr_native_min_value = (
            TEMP_MIN_HOT_WATER if zone_type == "HOT_WATER" else TEMP_MIN_AC
        )
        self._attr_native_max_value = (
            TEMP_MAX_HOT_WATER_OVERRIDE if zone_type == "HOT_WATER" else TEMP_MAX_AC
        )

        capabilities = coordinator.data.capabilities.get(zone_id)
        if capabilities and capabilities.temperatures:
            self._attr_native_min_value = float(capabilities.temperatures.celsius.min)
            self._attr_native_max_value = float(capabilities.temperatures.celsius.max)
            self._attr_native_step = float(capabilities.temperatures.celsius.step)

        self._attr_unique_id = f"zone_{zone_id}_target_temp"

    async def async_added_to_hass(self) -> None:
        """Fetch capabilities on startup if not cached."""
        await super().async_added_to_hass()
        if capabilities := await self.coordinator.async_get_capabilities(self._zone_id):
            if capabilities.temperatures:
                self._attr_native_min_value = float(
                    capabilities.temperatures.celsius.min
                )
                self._attr_native_max_value = float(
                    capabilities.temperatures.celsius.max
                )
                self._attr_native_step = float(capabilities.temperatures.celsius.step)
                self.async_write_ha_state()

    def _get_actual_value(self) -> float | None:
        state = self.coordinator.data.zone_states.get(str(self._zone_id))
        if state and state.setting and state.setting.temperature:
            return float(state.setting.temperature.celsius)
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Set a new target temperature."""
        if self._zone_type == "HOT_WATER":
            # Use optimistic_value=True (Manual Overlay active) -> Schedule Switch shows OFF
            await self.coordinator.async_set_zone_overlay(
                self._zone_id,
                power="ON",
                temperature=value,
                overlay_type="HOT_WATER",
                optimistic_value=True,
            )
        else:
            await self.coordinator.async_set_ac_setting(
                self._zone_id, "temperature", str(value)
            )
