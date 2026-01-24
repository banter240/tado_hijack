"""Climate entities for Tado Hijack."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature

from .const import (
    OVERLAY_MANUAL,
    POWER_OFF,
    POWER_ON,
    TEMP_DEFAULT_AC,
    TEMP_DEFAULT_HOT_WATER,
    TEMP_MAX_AC,
    TEMP_MAX_HOT_WATER,
    TEMP_MIN_AC,
    TEMP_MIN_HOT_WATER,
    TEMP_STEP_AC,
    TEMP_STEP_HOT_WATER,
)
from .entity import TadoOptimisticMixin, TadoZoneEntity
from .helpers.parsers import get_ac_capabilities

if TYPE_CHECKING:
    from .coordinator import TadoDataUpdateCoordinator


class TadoClimateEntity(TadoZoneEntity, TadoOptimisticMixin, ClimateEntity):
    """Base class for Tado climate entities (Hot Water / AC)."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        translation_key: str,
        zone_id: int,
        zone_name: str,
        default_temp: float,
        min_temp: float,
    ) -> None:
        """Initialize climate entity."""
        super().__init__(coordinator, translation_key, zone_id, zone_name)
        self._default_temp = default_temp
        self._min_temp_limit = min_temp
        self._last_target_temp: float | None = None

    async def async_added_to_hass(self) -> None:
        """Fetch capabilities on startup if not cached."""
        await super().async_added_to_hass()
        await self._async_update_capabilities()

    async def _async_update_capabilities(self) -> None:
        """Fetch and refresh capabilities."""
        if capabilities := await self.tado_coordinator.async_get_capabilities(
            self._zone_id
        ):
            if capabilities.temperatures:
                self._attr_min_temp = float(capabilities.temperatures.celsius.min)
                self._attr_max_temp = float(capabilities.temperatures.celsius.max)
                self._attr_target_temperature_step = float(
                    capabilities.temperatures.celsius.step
                )
            self.async_write_ha_state()

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current operation mode."""
        state = self._resolve_state()
        if state is None:
            return HVACMode.OFF

        overlay = self.tado_coordinator.optimistic.get_zone_overlay(self._zone_id)
        if overlay is False:
            return HVACMode.AUTO

        power = (
            state.get("power")
            if isinstance(state, dict)
            else getattr(state, "power", POWER_OFF)
        )

        return HVACMode.OFF if power == POWER_OFF else self._get_active_hvac_mode()

    @property
    def _current_state(self) -> Any:
        """Return actual state from coordinator data."""
        return self.tado_coordinator.data.zone_states.get(str(self._zone_id))

    def _get_active_hvac_mode(self) -> HVACMode:
        """Return the HVAC mode to show when power is ON. Subclasses must implement."""
        raise NotImplementedError

    @property
    def hvac_action(self) -> HVACAction:
        """Return current activity."""
        state = self._current_state
        if state is None or getattr(state, "power", POWER_OFF) == POWER_OFF:
            return HVACAction.OFF

        return (
            self._get_active_hvac_action()
            if self._is_active(state)
            else HVACAction.IDLE
        )

    def _is_active(self, state: Any) -> bool:
        """Check if the device is currently active (heating/cooling). Subclasses must implement."""
        raise NotImplementedError

    def _get_active_hvac_action(self) -> HVACAction:
        """Return the action to show when active. Subclasses must implement."""
        raise NotImplementedError

    @property
    def current_temperature(self) -> float | None:
        """Return current temperature."""
        state = self._current_state
        if state and state.sensor_data_points:
            if temp := getattr(
                state.sensor_data_points.inside_temperature, "celsius", None
            ):
                return float(temp)

        return None

    @property
    def target_temperature(self) -> float | None:
        """Return target temperature."""
        state = self._current_state
        if state and state.setting and state.setting.temperature:
            if temp := getattr(state.setting.temperature, "celsius", None):
                return float(temp)

        return self._default_temp

    def _get_optimistic_value(self) -> dict[str, Any] | None:
        """Return optimistic state if set."""
        power = self.tado_coordinator.optimistic.get_zone_power(self._zone_id)
        return {"power": power} if power is not None else None

    def _get_actual_value(self) -> dict[str, Any]:
        """Return actual value from coordinator data."""
        state = self._current_state
        if state is None:
            return {"power": POWER_OFF}
        return {"power": getattr(state, "power", POWER_OFF)}

    async def async_turn_on(self) -> None:
        """Turn on entity."""
        await self.async_set_hvac_mode(self._get_active_hvac_mode())

    async def async_turn_off(self) -> None:
        """Turn off entity."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set operation mode."""
        if hvac_mode == HVACMode.AUTO:
            await self.tado_coordinator.async_set_zone_auto(self._zone_id)
            return

        if hvac_mode == HVACMode.OFF:
            if current := self.target_temperature:
                if current > self._min_temp_limit:
                    self._last_target_temp = current

            await self.tado_coordinator.async_set_multiple_zone_overlays(
                zone_ids=[self._zone_id],
                power=POWER_OFF,
                overlay_mode=OVERLAY_MANUAL,
            )
            return

        # Handle turning ON (HEAT/COOL)
        if self._last_target_temp:
            use_temp = self._last_target_temp
        else:
            api_temp = self.target_temperature
            if api_temp and api_temp > self._min_temp_limit:
                use_temp = api_temp
                self._last_target_temp = api_temp
            else:
                use_temp = self._default_temp

        await self.tado_coordinator.async_set_multiple_zone_overlays(
            zone_ids=[self._zone_id],
            power=POWER_ON,
            temperature=round(use_temp),
            overlay_mode=OVERLAY_MANUAL,
        )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        rounded_temp = round(float(temperature))
        self._last_target_temp = float(rounded_temp)

        await self.tado_coordinator.async_set_multiple_zone_overlays(
            zone_ids=[self._zone_id],
            power=POWER_ON,
            temperature=rounded_temp,
            overlay_mode=OVERLAY_MANUAL,
        )


class TadoWaterHeater(TadoClimateEntity):
    """Climate entity for Hot Water control."""

    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.AUTO]
    _attr_min_temp = TEMP_MIN_HOT_WATER
    _attr_max_temp = TEMP_MAX_HOT_WATER
    _attr_target_temperature_step = TEMP_STEP_HOT_WATER

    def __init__(
        self, coordinator: TadoDataUpdateCoordinator, zone_id: int, zone_name: str
    ) -> None:
        """Initialize hot water climate entity."""
        super().__init__(
            coordinator,
            "hot_water",
            zone_id,
            zone_name,
            TEMP_DEFAULT_HOT_WATER,
            TEMP_MIN_HOT_WATER,
        )
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_climate_hw_{zone_id}"
        )

    def _get_active_hvac_mode(self) -> HVACMode:
        return HVACMode.HEAT

    def _is_active(self, state: Any) -> bool:
        if (
            hasattr(state, "activity_data_points")
            and state.activity_data_points
            and hasattr(state.activity_data_points, "heating_power")
            and state.activity_data_points.heating_power
        ):
            return (
                getattr(state.activity_data_points.heating_power, "percentage", 0) > 0
            )
        return False

    def _get_active_hvac_action(self) -> HVACAction:
        return HVACAction.HEATING


class TadoAirConditioning(TadoClimateEntity):
    """Climate entity for Air Conditioning control."""

    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.SWING_MODE
    )
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.AUTO]
    _attr_min_temp = TEMP_MIN_AC
    _attr_max_temp = TEMP_MAX_AC
    _attr_target_temperature_step = TEMP_STEP_AC

    def __init__(
        self, coordinator: TadoDataUpdateCoordinator, zone_id: int, zone_name: str
    ) -> None:
        """Initialize air conditioning climate entity."""
        super().__init__(
            coordinator,
            "air_conditioning",
            zone_id,
            zone_name,
            TEMP_DEFAULT_AC,
            TEMP_MIN_AC,
        )
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_climate_ac_{zone_id}"
        )

    def _get_active_hvac_mode(self) -> HVACMode:
        return HVACMode.COOL

    def _is_active(self, state: Any) -> bool:
        if (
            hasattr(state, "activity_data_points")
            and state.activity_data_points
            and hasattr(state.activity_data_points, "ac_power")
            and state.activity_data_points.ac_power
        ):
            return (
                getattr(state.activity_data_points.ac_power, "value", POWER_OFF)
                == POWER_ON
            )
        return False

    def _get_active_hvac_action(self) -> HVACAction:
        return HVACAction.COOLING

    @property
    def fan_mode(self) -> str | None:
        """Return current fan mode."""
        state = self._current_state
        if state and state.setting:
            return getattr(state.setting, "fan_level", None) or getattr(
                state.setting, "fan_speed", None
            )
        return None

    @property
    def fan_modes(self) -> list[str] | None:
        """Return supported fan modes (cached)."""
        capabilities = self.tado_coordinator.data.capabilities.get(self._zone_id)
        if not capabilities:
            # We trigger an async update but return None for now
            # HA will call this again when we call async_write_ha_state
            self.hass.async_create_task(self._async_update_capabilities())
            return None

        modes = get_ac_capabilities(capabilities)["fan_speeds"]
        return sorted(modes) if modes else None

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new fan mode."""
        await self.tado_coordinator.async_set_ac_setting(
            self._zone_id, "fan_speed", fan_mode
        )

    @property
    def swing_mode(self) -> str | None:
        """Return current swing mode."""
        state = self._current_state
        if state and state.setting:
            return getattr(state.setting, "vertical_swing", None) or getattr(
                state.setting, "swing", None
            )
        return None

    @property
    def swing_modes(self) -> list[str] | None:
        """Return supported swing modes (cached)."""
        capabilities = self.tado_coordinator.data.capabilities.get(self._zone_id)
        if not capabilities:
            self.hass.async_create_task(self._async_update_capabilities())
            return None

        modes = get_ac_capabilities(capabilities)["vertical_swing"]
        return sorted(modes) if modes else None

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set new swing mode."""
        await self.tado_coordinator.async_set_ac_setting(
            self._zone_id, "vertical_swing", swing_mode
        )
