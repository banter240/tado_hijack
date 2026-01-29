"""Water heater platform for Tado Hijack."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    TEMP_MAX_HOT_WATER,
    TEMP_MIN_HOT_WATER,
    TEMP_STEP_HOT_WATER,
    ZONE_TYPE_HOT_WATER,
)
from .entity import TadoHotWaterZoneEntity, TadoOptimisticMixin
from .helpers.discovery import yield_zones
from .helpers.logging_utils import get_redacted_logger

if TYPE_CHECKING:
    from . import TadoConfigEntry
    from .coordinator import TadoDataUpdateCoordinator

_LOGGER = get_redacted_logger(__name__)

# Tado hot water operation modes
OPERATION_MODE_AUTO = "auto"
OPERATION_MODE_HEAT = "heat"
OPERATION_MODE_OFF = "off"

OPERATION_MODES = [OPERATION_MODE_AUTO, OPERATION_MODE_HEAT, OPERATION_MODE_OFF]


async def async_setup_entry(
    hass: Any,
    entry: TadoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tado hot water based on a config entry."""
    coordinator: TadoDataUpdateCoordinator = entry.runtime_data
    if entities := [
        TadoHotWater(coordinator, zone.id, zone.name)
        for zone in yield_zones(coordinator, {ZONE_TYPE_HOT_WATER})
    ]:
        async_add_entities(entities)
    else:
        _LOGGER.debug("No hot water zones found")


class TadoHotWater(
    TadoHotWaterZoneEntity, TadoOptimisticMixin, WaterHeaterEntity, RestoreEntity
):
    """Representation of a Tado hot water zone."""

    _attr_supported_features = (
        WaterHeaterEntityFeature.OPERATION_MODE
        | WaterHeaterEntityFeature.TARGET_TEMPERATURE
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_operation_list = OPERATION_MODES
    _attr_min_temp = TEMP_MIN_HOT_WATER
    _attr_max_temp = TEMP_MAX_HOT_WATER
    _attr_target_temperature_step = TEMP_STEP_HOT_WATER
    _attr_optimistic_key = "operation_mode"
    _attr_optimistic_scope = "zone"

    _attr_name = None

    def __init__(
        self, coordinator: TadoDataUpdateCoordinator, zone_id: int, zone_name: str
    ) -> None:
        """Initialize Tado hot water."""
        super().__init__(coordinator, "hot_water", zone_id, zone_name)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_water_heater_{zone_id}"
        )
        self._last_target_temp: float | None = None

    async def async_added_to_hass(self) -> None:
        """Handle entity being added to Home Assistant."""
        await super().async_added_to_hass()

        if not self.tado_coordinator.supports_temperature(self._zone_id):
            self._attr_supported_features = WaterHeaterEntityFeature.OPERATION_MODE
            self.async_write_ha_state()
            return

        # Restore last known temperature from HA state machine
        if last_state := await self.async_get_last_state():
            if "last_target_temperature" in last_state.attributes:
                self._last_target_temp = float(
                    last_state.attributes["last_target_temperature"]
                )
                _LOGGER.debug(
                    "Hot Water Zone %d: Restored last_target_temp: %s",
                    self._zone_id,
                    self._last_target_temp,
                )

        capabilities = await self.tado_coordinator.async_get_capabilities(self._zone_id)
        if capabilities and capabilities.temperatures:
            self._attr_min_temp = float(capabilities.temperatures.celsius.min)
            self._attr_max_temp = float(capabilities.temperatures.celsius.max)
            if capabilities.temperatures.celsius.step:
                self._attr_target_temperature_step = float(
                    capabilities.temperatures.celsius.step
                )
            self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        return {
            "last_target_temperature": self._last_target_temp,
        }

    @property
    def current_operation(self) -> str:
        """Return current operation mode."""
        return str(self._resolve_state())

    def _get_actual_value(self) -> str:
        """Return actual operation mode from coordinator data."""
        state = self.coordinator.data.zone_states.get(str(self._zone_id))
        if state is None:
            return OPERATION_MODE_AUTO

        # Check if there's an overlay (manual mode)
        if getattr(state, "overlay_active", False):
            if setting := getattr(state, "setting", None):
                power = getattr(setting, "power", "ON")
                return OPERATION_MODE_OFF if power == "OFF" else OPERATION_MODE_HEAT
        return OPERATION_MODE_AUTO

    @property
    def current_temperature(self) -> float | None:
        """Return the current water temperature if available."""
        # Tado hot water zones do not expose a dedicated water temperature sensor.
        # Returning the inside air temperature here would be misleading.
        return None

    @property
    def target_temperature(self) -> float | None:
        """Return the target water temperature."""
        if self.current_operation == OPERATION_MODE_OFF:
            return None

        # 1. Check Optimistic Temperature
        if (
            opt_temp := self.tado_coordinator.optimistic.get_zone_temperature(
                self._zone_id
            )
        ) is not None:
            return float(opt_temp)

        # 2. Real API State
        state = self.tado_coordinator.data.zone_states.get(str(self._zone_id))
        if state is None:
            return None

        if setting := getattr(state, "setting", None):
            if temp := getattr(setting, "temperature", None):
                return getattr(temp, "celsius", None)

        return None

    @property
    def is_on(self) -> bool:
        """Return true if hot water is on."""
        return self.current_operation != OPERATION_MODE_OFF

    @property
    def is_away_mode_on(self) -> bool:
        """Return true if away mode is on."""
        home_state = self.tado_coordinator.data.home_state
        if home_state is None:
            return False
        return str(getattr(home_state, "presence", "")) == "AWAY"

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set new operation mode."""
        if operation_mode == OPERATION_MODE_OFF:
            if current := self.target_temperature:
                self._last_target_temp = current
            await self.tado_coordinator.async_set_hot_water_off(self._zone_id)
        elif operation_mode == OPERATION_MODE_AUTO:
            if current := self.target_temperature:
                self._last_target_temp = current
            await self.tado_coordinator.async_set_hot_water_auto(self._zone_id)
        elif operation_mode == OPERATION_MODE_HEAT:
            await self.tado_coordinator.async_set_hot_water_heat(
                self._zone_id, temperature=self._last_target_temp
            )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn hot water on (resume schedule)."""
        await self.async_set_operation_mode(OPERATION_MODE_AUTO)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn hot water off (manual overlay)."""
        await self.async_set_operation_mode(OPERATION_MODE_OFF)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        if not self.tado_coordinator.supports_temperature(self._zone_id):
            _LOGGER.warning(
                "Hot water zone %d does not support temperature control",
                self._zone_id,
            )
            return

        # Round to integer for hot water (Tado requirement)
        rounded_temp = round(float(temperature))
        self._last_target_temp = float(rounded_temp)

        await self.tado_coordinator.async_set_zone_overlay(
            self._zone_id,
            power="ON",
            temperature=rounded_temp,
            overlay_type="HOT_WATER",
        )
