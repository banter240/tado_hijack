"""Climate entities for Tado Hijack."""

from __future__ import annotations

import asyncio
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
    TEMP_MAX_AC,
    TEMP_MIN_AC,
    TEMP_STEP_AC,
)
from .entity import TadoOptimisticMixin, TadoStateMemoryMixin, TadoZoneEntity
from .helpers.logging_utils import get_redacted_logger
from .helpers.parsers import (
    get_ac_capabilities,
    parse_schedule_temperature,
)

if TYPE_CHECKING:
    from .coordinator import TadoDataUpdateCoordinator

_LOGGER = get_redacted_logger(__name__)


class TadoClimateEntity(
    TadoStateMemoryMixin,
    TadoZoneEntity,
    TadoOptimisticMixin,
    ClimateEntity,
):
    """Base class for Tado climate entities (Hot Water / AC)."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_optimistic_key = "power"
    _attr_optimistic_scope = "zone"

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
        # Register memory keys
        self._store_last_state("target_temperature", None)

    async def async_added_to_hass(self) -> None:
        """Handle entity being added to Home Assistant."""
        await super().async_added_to_hass()
        await self._async_update_capabilities()

    async def _async_update_capabilities(self) -> None:
        """Fetch and refresh capabilities."""
        if capabilities := await self.tado_coordinator.async_get_capabilities(
            self._zone_id
        ):
            if capabilities.temperatures:
                new_min = float(capabilities.temperatures.celsius.min)
                new_max = float(capabilities.temperatures.celsius.max)
                new_step = float(capabilities.temperatures.celsius.step)

                # Only update if values are sane (prevent min == max)
                if new_min < new_max and new_step > 0:
                    self._attr_min_temp = new_min
                    self._attr_max_temp = new_max
                    self._attr_target_temperature_step = new_step
                else:
                    _LOGGER.warning(
                        "Invalid capabilities for zone %d (min=%s, max=%s, step=%s), keeping defaults",
                        self._zone_id,
                        new_min,
                        new_max,
                        new_step,
                    )
            self.async_write_ha_state()

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current operation mode."""
        opt_overlay = self.tado_coordinator.optimistic.get_zone_overlay(self._zone_id)

        if opt_overlay is False:
            return HVACMode.AUTO

        is_manual_intent = opt_overlay is True

        resolved_state = self._resolve_state()
        power = (
            resolved_state.get("power")
            if isinstance(resolved_state, dict)
            else str(resolved_state)
        )

        state = self._current_state
        api_has_overlay = bool(state and getattr(state, "overlay_active", False))

        if not api_has_overlay and not is_manual_intent:
            return HVACMode.AUTO

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
        # Use resolved state (Optimistic > Actual) for the basic ON/OFF check
        resolved_state = self._resolve_state()
        power = (
            resolved_state.get("power")
            if isinstance(resolved_state, dict)
            else str(resolved_state)
        )

        if state is None or power == POWER_OFF:
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
                result = float(temp)
                _LOGGER.debug(
                    "Zone %d current_temperature: %s (from inside_temperature)",
                    self._zone_id,
                    result,
                )
                return result

        _LOGGER.debug("Zone %d current_temperature: None", self._zone_id)
        return None

    @property
    def target_temperature(self) -> float | None:
        """Return target temperature."""
        if self.hvac_mode in (HVACMode.OFF, HVACMode.FAN_ONLY):
            return None

        if (
            opt_temp := self.tado_coordinator.optimistic.get_zone_temperature(
                self._zone_id
            )
        ) is not None:
            return float(opt_temp)

        state = self._current_state
        if state and state.setting and state.setting.temperature:
            if temp := getattr(state.setting.temperature, "celsius", None):
                result = float(temp)
                _LOGGER.debug(
                    "Zone %d target_temperature: %s (min=%s, max=%s, step=%s)",
                    self._zone_id,
                    result,
                    self._attr_min_temp,
                    self._attr_max_temp,
                    self._attr_target_temperature_step,
                )
                return result

        if (last_temp := self._get_last_state("target_temperature")) is not None:
            return float(last_temp)

        default = self._default_temp if self.hvac_mode == HVACMode.AUTO else None
        _LOGGER.debug(
            "Zone %d target_temperature: %s (default/fallback)", self._zone_id, default
        )
        return default

    def _get_actual_value(self) -> str:
        """Return actual power value from coordinator data."""
        state = self._current_state
        if state and state.setting:
            return str(getattr(state.setting, "power", POWER_OFF))
        return POWER_OFF

    async def async_turn_on(self) -> None:
        """Turn on entity."""
        await self.async_set_hvac_mode(self._get_active_hvac_mode())

    async def async_turn_off(self) -> None:
        """Turn off entity."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set operation mode."""
        # Handle turning OFF (Store last target temp for restoration)
        if hvac_mode == HVACMode.OFF:
            if current := self.target_temperature:
                if current > self._min_temp_limit:
                    self._store_last_state("target_temperature", current)

        # Use restored temp if turning ON, else None
        use_temp: float | None = None
        # Use explicit mode string for AC if not OFF/AUTO
        ac_mode: str | None = None

        if hvac_mode not in (HVACMode.OFF, HVACMode.AUTO):
            use_temp = (
                self._get_last_state("target_temperature")
                or self.target_temperature
                or self._default_temp
            )
            # Map HA HVACMode to Tado Mode string (e.g. "cool" -> "COOL")
            # Tado modes are usually uppercase
            if (
                hvac_mode != HVACMode.HEAT
            ):  # Heating is default for HEATING zones, but AC needs mode
                ac_mode = (
                    "FAN" if hvac_mode == HVACMode.FAN_ONLY else str(hvac_mode).upper()
                )
            # Special case: If it's a TadoAirConditioning entity, we might need to be specific
            # even for HEAT if the AC supports it.
            if isinstance(self, TadoAirConditioning):
                ac_mode = (
                    "FAN" if hvac_mode == HVACMode.FAN_ONLY else str(hvac_mode).upper()
                )
        await self.tado_coordinator.async_set_zone_hvac_mode(
            zone_id=self._zone_id,
            hvac_mode=hvac_mode,
            temperature=use_temp,
            overlay_mode=OVERLAY_MANUAL,
            ac_mode=ac_mode,
        )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        rounded_temp = round(float(temperature))
        self._store_last_state("target_temperature", float(rounded_temp))

        # For AC zones, we must pass the current mode to avoid validation errors
        ac_mode: str | None = None
        if isinstance(self, TadoAirConditioning):
            ac_mode = self._get_active_hvac_mode().value.upper()
            if ac_mode == "FAN_ONLY":
                ac_mode = "FAN"

        await self.tado_coordinator.async_set_multiple_zone_overlays(
            zone_ids=[self._zone_id],
            power=POWER_ON,
            temperature=rounded_temp,
            overlay_mode=OVERLAY_MANUAL,
            ac_mode=ac_mode,
        )


class TadoAirConditioning(TadoClimateEntity):
    """Climate entity for Air Conditioning control."""

    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.SWING_MODE
    )
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
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.AUTO]
        # Register memory keys
        self._store_last_state("vertical_swing", "OFF")
        self._store_last_state("horizontal_swing", "OFF")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes including memory."""
        attrs = super().extra_state_attributes

        # Recovery of the target temperature of the planning in AUTO mode
        if self.hvac_mode == HVACMode.AUTO:
            state = self._current_state
            temp = parse_schedule_temperature(state)
            attrs["auto_target_temperature"] = float(temp) if temp is not None else None

        return attrs

    async def _async_update_capabilities(self) -> None:
        """Fetch and refresh capabilities."""
        if not (
            capabilities := await self.tado_coordinator.async_get_capabilities(
                self._zone_id
            )
        ):
            return
        # Update Temperature Limits
        if capabilities.temperatures:
            new_min = float(capabilities.temperatures.celsius.min)
            new_max = float(capabilities.temperatures.celsius.max)
            new_step = float(capabilities.temperatures.celsius.step)

            if new_min < new_max and new_step > 0:
                self._attr_min_temp = new_min
                self._attr_max_temp = new_max
                self._attr_target_temperature_step = new_step

        # Update Supported HVAC Modes dynamically
        modes = [HVACMode.OFF, HVACMode.AUTO]
        if getattr(capabilities, "cool", None):
            modes.append(HVACMode.COOL)
        if getattr(capabilities, "heat", None):
            modes.append(HVACMode.HEAT)
        if getattr(capabilities, "dry", None):
            modes.append(HVACMode.DRY)
        if getattr(capabilities, "fan", None):
            modes.append(HVACMode.FAN_ONLY)

        self._attr_hvac_modes = modes
        self.async_write_ha_state()

    def _get_active_hvac_mode(self) -> HVACMode:
        """Return hvac mode when power is ON based on current state."""
        if (
            opt_mode := self.tado_coordinator.optimistic.get_zone_ac_mode(self._zone_id)
        ) is not None:
            mode = opt_mode.lower()
            if mode == "cool":
                return HVACMode.COOL
            if mode == "heat":
                return HVACMode.HEAT
            if mode == "dry":
                return HVACMode.DRY
            if mode == "fan":
                return HVACMode.FAN_ONLY

        state = self._current_state
        if state and state.setting and state.setting.mode:
            mode = str(state.setting.mode).lower()
            if mode == "cool":
                return HVACMode.COOL
            if mode == "heat":
                return HVACMode.HEAT
            if mode == "dry":
                return HVACMode.DRY
            if mode == "fan":
                return HVACMode.FAN_ONLY
        return HVACMode.COOL

    def _is_active(self, state: Any) -> bool:
        """Check if the device is currently active (heating/cooling)."""
        resolved_state = self._resolve_state()
        power = (
            resolved_state.get("power")
            if isinstance(resolved_state, dict)
            else str(resolved_state)
        )

        if state is None or power == POWER_OFF:
            return False

        current_temp = self.current_temperature
        target_temp = self.target_temperature
        mode = self.hvac_mode

        opt = self.tado_coordinator.optimistic
        is_optimistic = (
            opt.get_zone_temperature(self._zone_id) is not None
            or opt.get_zone_overlay(self._zone_id) is not None
        )

        if is_optimistic and current_temp is not None and target_temp is not None:
            if mode == HVACMode.HEAT:
                return current_temp < target_temp
            if mode in (HVACMode.COOL, HVACMode.DRY):
                return current_temp > target_temp

        if hasattr(state, "activity_data_points") and state.activity_data_points:
            if ac_p := getattr(state.activity_data_points, "ac_power", None):
                return str(ac_p.value) == POWER_ON
            if h_p := getattr(state.activity_data_points, "heating_power", None):
                return float(getattr(h_p, "percentage", 0)) > 0

        if current_temp is None or target_temp is None:
            return False

        if mode == HVACMode.HEAT:
            return current_temp < target_temp
        return current_temp > target_temp if mode == HVACMode.COOL else True

    def _get_active_hvac_action(self) -> HVACAction:
        """Return the action based on current mode."""
        mode = self.hvac_mode
        if mode == HVACMode.HEAT:
            return HVACAction.HEATING
        if mode == HVACMode.COOL:
            return HVACAction.COOLING
        if mode == HVACMode.DRY:
            return HVACAction.DRYING
        return HVACAction.FAN if mode == HVACMode.FAN_ONLY else HVACAction.IDLE

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
        v_swing = self.tado_coordinator.optimistic.get_vertical_swing(self._zone_id)
        h_swing = self.tado_coordinator.optimistic.get_horizontal_swing(self._zone_id)

        if v_swing and v_swing != "OFF":
            self._store_last_state("vertical_swing", v_swing)
        if h_swing and h_swing != "OFF":
            self._store_last_state("horizontal_swing", h_swing)

        if v_swing is not None:
            return v_swing
        if h_swing is not None:
            return h_swing

        state = self._current_state
        if state and state.setting:
            v_val = getattr(state.setting, "vertical_swing", "OFF")
            h_val = getattr(state.setting, "horizontal_swing", "OFF")

            if v_val != "OFF":
                self._store_last_state("vertical_swing", v_val)
            if h_val != "OFF":
                self._store_last_state("horizontal_swing", h_val)

            return v_val if v_val != "OFF" else h_val
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
        capabilities = self.tado_coordinator.data.capabilities.get(self._zone_id)
        if not capabilities:
            await self.tado_coordinator.async_set_ac_setting(
                self._zone_id, "vertical_swing", swing_mode
            )
            return

        ac_caps = get_ac_capabilities(capabilities)
        tasks = []

        if swing_mode == "OFF":
            # Store current states before turning OFF
            state = self._current_state
            if state and state.setting:
                self._store_last_state(
                    "vertical_swing",
                    self.tado_coordinator.optimistic.get_vertical_swing(self._zone_id)
                    or getattr(state.setting, "vertical_swing", "OFF"),
                )
                self._store_last_state(
                    "horizontal_swing",
                    self.tado_coordinator.optimistic.get_horizontal_swing(self._zone_id)
                    or getattr(state.setting, "horizontal_swing", "OFF"),
                )

            # Turn everything OFF
            if ac_caps["vertical_swing"]:
                tasks.append(
                    self.tado_coordinator.async_set_ac_setting(
                        self._zone_id, "vertical_swing", "OFF"
                    )
                )
            if ac_caps["horizontal_swings"]:
                tasks.append(
                    self.tado_coordinator.async_set_ac_setting(
                        self._zone_id, "horizontal_swing", "OFF"
                    )
                )
        else:
            # Turning ON: Restore last known configuration
            # Default to ON if no last state recorded
            v_target = self._get_last_state("vertical_swing", "OFF")
            h_target = self._get_last_state("horizontal_swing", "OFF")

            if v_target == "OFF" and h_target == "OFF":
                v_target = "ON"  # Default fallback

            if ac_caps["vertical_swing"]:
                tasks.append(
                    self.tado_coordinator.async_set_ac_setting(
                        self._zone_id, "vertical_swing", v_target
                    )
                )
            if ac_caps["horizontal_swings"]:
                tasks.append(
                    self.tado_coordinator.async_set_ac_setting(
                        self._zone_id, "horizontal_swing", h_target
                    )
                )

        if tasks:
            await asyncio.gather(*tasks)
