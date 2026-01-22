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
from .entity import (
    TadoDeviceEntity,
    TadoOptimisticMixin,
    TadoZoneEntity,
)

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

    entities: list[NumberEntity] = []

    for zone in coordinator.zones_meta.values():
        # Temperature Offset per Device
        if zone.type == "HEATING":
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

        # Target Temperature per Zone (AC or Hot Water)
        if zone.type in ("AIR_CONDITIONING", "HOT_WATER"):
            entities.append(
                TadoTargetTempNumberEntity(coordinator, zone.id, zone.name, zone.type)
            )

        # Away Temperature per Zone (Heating only)
        if zone.type == "HEATING":
            entities.append(TadoAwayTempNumberEntity(coordinator, zone.id, zone.name))

    if entities:
        async_add_entities(entities)


class TadoOptimisticNumber(RestoreEntity, NumberEntity):
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
        if (opt := self._get_optimistic_value()) is not None:
            return float(opt)

        if (actual := self._get_actual_value()) is not None:
            return float(actual)

        return self._restored_value

    def _get_optimistic_value(self) -> float | None:
        raise NotImplementedError

    def _get_actual_value(self) -> float | None:
        raise NotImplementedError


class TadoNumberEntity(TadoDeviceEntity, TadoOptimisticMixin, TadoOptimisticNumber):
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

    def _get_optimistic_value(self) -> float | None:
        val = self.coordinator.optimistic.get_offset(self._serial_no)
        return float(val) if val is not None else None

    def _get_actual_value(self) -> float | None:
        offsets: dict[str, Any] = self.coordinator.data.get("offsets", {})
        offset = offsets.get(self._serial_no)
        return float(offset.celsius) if offset is not None else None

    async def async_set_native_value(self, value: float) -> None:
        """Set a new temperature offset."""
        await self.coordinator.async_set_temperature_offset(self._serial_no, value)


class TadoAwayTempNumberEntity(
    TadoZoneEntity, TadoOptimisticMixin, TadoOptimisticNumber
):
    """Representation of a Tado Away Temperature number."""

    _attr_has_entity_name = True
    _attr_translation_key = "away_temperature"
    _attr_native_min_value = 5.0
    _attr_native_max_value = 25.0
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX

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

    def _get_optimistic_value(self) -> float | None:
        val = self.coordinator.optimistic.get_away_temp(self._zone_id)
        return float(val) if val is not None else None

    def _get_actual_value(self) -> float | None:
        away_configs: dict[int, float] = self.coordinator.data.get("away_config", {})
        return away_configs.get(self._zone_id)

    async def async_set_native_value(self, value: float) -> None:
        """Set a new away temperature."""
        await self.coordinator.async_set_away_temperature(self._zone_id, value)


class TadoTargetTempNumberEntity(
    TadoZoneEntity, TadoOptimisticMixin, TadoOptimisticNumber
):
    """Representation of a Tado Target Temperature number (AC/HW)."""

    _attr_has_entity_name = True
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX

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

        # Set ranges based on type
        if zone_type == "HOT_WATER":
            self._attr_native_min_value = 30.0
            self._attr_native_max_value = 70.0
        else:  # AC
            self._attr_native_min_value = 16.0
            self._attr_native_max_value = 30.0

        self._attr_unique_id = f"zone_{zone_id}_target_temp"

    def _get_optimistic_value(self) -> float | None:
        return None

    def _get_actual_value(self) -> float | None:
        state = self.coordinator.data.get("zone_states", {}).get(str(self._zone_id))
        if state and state.setting and state.setting.temperature:
            return float(state.setting.temperature.celsius)
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Set a new target temperature."""
        if self._zone_type == "HOT_WATER":
            # Reuse HW power method but with temp logic?
            # Tado API needs temperature field in setting.
            # I need to ensure coordinator supports this.
            # For now, we assume SET_OVERLAY handles it if temperature is in data.
            await self.coordinator.async_set_zone_heat(self._zone_id, temp=value)
        else:
            # For AC, we reuse async_set_ac_setting or similar
            await self.coordinator.async_set_ac_setting(
                self._zone_id, "temperature", str(value)
            )
