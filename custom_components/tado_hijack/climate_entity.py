"""Climate entities for Tado Hijack (Hot Water only - no redundancy with HomeKit)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature

from .entity import TadoOptimisticMixin, TadoZoneEntity

if TYPE_CHECKING:
    from .coordinator import TadoDataUpdateCoordinator


class TadoWaterHeater(TadoZoneEntity, TadoOptimisticMixin, ClimateEntity):
    """Climate entity for Tado Hot Water zones.

    Provides operation modes for Hot Water control:
    - AUTO: Return to Smart Schedule
    - HEAT: Manual/Timer override (ON)
    - OFF: Turn off hot water
    """

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.AUTO]
    _attr_min_temp = 30.0
    _attr_max_temp = 80.0
    _attr_target_temperature_step = 0.1

    def __init__(
        self, coordinator: TadoDataUpdateCoordinator, zone_id: int, zone_name: str
    ) -> None:
        """Initialize hot water climate entity."""
        super().__init__(coordinator, "hot_water", zone_id, zone_name)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_climate_hw_{zone_id}"
        )

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current operation mode."""
        state = self._resolve_state()

        if state is None:
            return HVACMode.OFF

        # If we have an optimistic overlay mode, check it
        overlay = self.tado_coordinator.optimistic.get_zone_overlay(self._zone_id)
        if overlay is False:
            # False = No overlay = Schedule active = AUTO
            return HVACMode.AUTO

        # Check power state
        power = (
            state.get("power")
            if isinstance(state, dict)
            else getattr(state, "power", "OFF")
        )

        return HVACMode.HEAT if power == "ON" else HVACMode.OFF

    @property
    def current_temperature(self) -> float | None:
        """Return current temperature."""
        state = self.tado_coordinator.data.get("zone_states", {}).get(
            str(self._zone_id)
        )
        if state is None:
            return None

        # Hot water zones typically report sensor temperature
        if hasattr(state, "sensorDataPoints") and state.sensorDataPoints:
            if temp := getattr(state.sensorDataPoints, "insideTemperature", None):
                return float(getattr(temp, "celsius", 0))

        return None

    @property
    def target_temperature(self) -> float | None:
        """Return target temperature."""
        state = self.tado_coordinator.data.get("zone_states", {}).get(
            str(self._zone_id)
        )
        if state is None:
            return None

        # Get target temp from overlay or schedule
        if (
            hasattr(state, "setting")
            and state.setting
            and (hasattr(state.setting, "temperature") and state.setting.temperature)
        ):
            return float(getattr(state.setting.temperature, "celsius", 50.0))

        return 50.0  # Default hot water temp

    def _get_optimistic_value(self) -> dict[str, Any] | None:
        """Return optimistic state if set."""
        power = self.tado_coordinator.optimistic.get_zone_power(self._zone_id)
        return {"power": power} if power is not None else None

    def _get_actual_value(self) -> dict[str, Any]:
        """Return actual value from coordinator data."""
        state = self.tado_coordinator.data.get("zone_states", {}).get(
            str(self._zone_id)
        )

        if state is None:
            return {"power": "OFF"}

        power = getattr(state, "power", "OFF")
        return {"power": power}

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set operation mode."""
        if hvac_mode == HVACMode.AUTO:
            # AUTO = Return to schedule
            await self.tado_coordinator.async_resume_schedule(self._zone_id)

        elif hvac_mode == HVACMode.HEAT:
            # HEAT = Turn ON with manual override
            await self.tado_coordinator.async_set_hot_water_power(self._zone_id, True)

        elif hvac_mode == HVACMode.OFF:
            # OFF = Turn off
            await self.tado_coordinator.async_set_hot_water_power(self._zone_id, False)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature for hot water."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        # Set hot water with target temperature
        await self.tado_coordinator.async_set_multiple_zone_overlays(
            zone_ids=[self._zone_id],
            power="ON",
            temperature=float(temperature),
            overlay_mode="timer",  # Use timer mode with default duration
        )
