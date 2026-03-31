"""Climate entities for Tado Hijack."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, ClassVar

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature

from .const import (
    GEN_X,
    OVERLAY_MANUAL,
    POWER_OFF,
    POWER_ON,
    TEMP_DEFAULT_AC,
    TEMP_MAX_AC,
    TEMP_MIN_AC,
    TEMP_STEP_AC,
)
from .dummy.const import DUMMY_ZONE_ID_AC, DUMMY_ZONE_ID_HOT_WATER
from .entity import TadoOptimisticMixin, TadoStateMemoryMixin, TadoZoneEntity
from .helpers.logging_utils import get_redacted_logger
from .helpers.parsers import (
    get_ac_capabilities,
    parse_schedule_temperature,
)

if TYPE_CHECKING:
    from .coordinator import TadoDataUpdateCoordinator

_LOGGER = get_redacted_logger(__name__)

_AC_MODE_MAP: dict[str, HVACMode] = {
    "cool": HVACMode.COOL,
    "heat": HVACMode.HEAT,
    "dry": HVACMode.DRY,
    "fan": HVACMode.FAN_ONLY,
}


def _ac_mode_to_hvac(mode_str: str) -> HVACMode | None:
    """Convert a Tado AC mode string to an HVACMode (None if unrecognised)."""
    return _AC_MODE_MAP.get(mode_str.lower())


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
        self._store_last_state("target_temperature", None)

    async def async_added_to_hass(self) -> None:
        """Handle entity being added to Home Assistant."""
        await super().async_added_to_hass()
        await self._async_update_capabilities()

    async def _async_update_capabilities(self) -> None:
        """Fetch and refresh capabilities."""
        if self.tado_coordinator.generation == "x":
            # Tado X (Static Defaults)
            self._attr_min_temp = 5.0
            self._attr_max_temp = 30.0
            self._attr_target_temperature_step = 0.5
            if isinstance(self, TadoAirConditioning):
                self._attr_hvac_modes = [
                    HVACMode.OFF,
                    HVACMode.COOL,
                    HVACMode.HEAT,
                    HVACMode.DRY,
                    HVACMode.FAN_ONLY,
                    HVACMode.AUTO,
                ]
            self.async_write_ha_state()
            return

        # v3 Classic (API Fetch)
        if not (
            capabilities := await self.tado_coordinator.async_get_capabilities(
                self._zone_id
            )
        ):
            return

        if capabilities.temperatures:
            new_min = float(capabilities.temperatures.celsius.min)
            new_max = float(capabilities.temperatures.celsius.max)
            new_step = float(capabilities.temperatures.celsius.step)

            if new_min < new_max and new_step > 0:
                self._attr_min_temp = new_min
                self._attr_max_temp = new_max
                self._attr_target_temperature_step = new_step

        if isinstance(self, TadoAirConditioning):
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

    @property
    def current_humidity(self) -> int | None:
        """Return current humidity."""
        state = self._current_state
        if (
            state
            and hasattr(state, "sensor_data_points")
            and state.sensor_data_points
            and hasattr(state.sensor_data_points, "humidity")
            and state.sensor_data_points.humidity
        ):
            return int(state.sensor_data_points.humidity.percentage)
        return None

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
                # Only log for real zones, skip dummy zones (998, 999)
                if self._zone_id not in (DUMMY_ZONE_ID_AC, DUMMY_ZONE_ID_HOT_WATER):
                    _LOGGER.debug(
                        "Zone %d current_temperature: %s (from inside_temperature)",
                        self._zone_id,
                        result,
                    )
                return result

        if self._zone_id not in (DUMMY_ZONE_ID_AC, DUMMY_ZONE_ID_HOT_WATER):
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
                # Only log for real zones, skip dummy zones (998, 999)
                if self._zone_id not in (DUMMY_ZONE_ID_AC, DUMMY_ZONE_ID_HOT_WATER):
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
        if self._zone_id not in (DUMMY_ZONE_ID_AC, DUMMY_ZONE_ID_HOT_WATER):
            _LOGGER.debug(
                "Zone %d target_temperature: %s (default/fallback)",
                self._zone_id,
                default,
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

        # Special handling for FAN mode - requires fanLevel field
        if isinstance(self, TadoAirConditioning) and hvac_mode == HVACMode.FAN_ONLY:
            await self._async_set_fan_only_mode()
            return

        use_temp: float | None = None
        ac_mode: str | None = None

        if hvac_mode not in (HVACMode.OFF, HVACMode.AUTO):
            # Temperature is only required for HEAT, COOL, and DRY modes
            # FAN mode does NOT need temperature
            if hvac_mode in (HVACMode.HEAT, HVACMode.COOL, HVACMode.DRY):
                use_temp = (
                    self._get_last_state("target_temperature")
                    or self.target_temperature
                    or self._default_temp
                )
            # For AIR_CONDITIONING zones, always set explicit mode
            # For HEATING zones, mode is optional (defaults to HEAT)
            if isinstance(self, TadoAirConditioning):
                ac_mode = str(hvac_mode).upper()
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
        # [TADO_X] Use heating-compatible defaults for Tado X (Unified entity)
        if coordinator.generation == GEN_X:
            default_temp, min_temp = self._get_defaults_tadox()
        else:
            default_temp, min_temp = self._get_defaults_v3()

        super().__init__(
            coordinator,
            "air_conditioning",
            zone_id,
            zone_name,
            default_temp,
            min_temp,
        )
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_climate_ac_{zone_id}"
        )
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.AUTO]
        self._store_last_state("vertical_swing", "OFF")
        self._store_last_state("horizontal_swing", "OFF")

    def _get_defaults_tadox(self) -> tuple[float, float]:
        """Get defaults for Tado X (Heating-compatible)."""
        # Tado X zones act as heating zones by default (min 5.0)
        # We use this entity for ALL Tado X rooms
        return 21.0, 5.0

    def _get_defaults_v3(self) -> tuple[float, float]:
        """Get defaults for v3 Classic (AC specific)."""
        return TEMP_DEFAULT_AC, TEMP_MIN_AC

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

    def _get_active_hvac_mode(self) -> HVACMode:
        """Return hvac mode when power is ON based on current state."""
        if (
            opt_mode := self.tado_coordinator.optimistic.get_zone_ac_mode(self._zone_id)
        ) is not None:
            if hvac_mode := _ac_mode_to_hvac(opt_mode):
                return hvac_mode

        # v3 Classic: mode exists in Setting (Tado X does not expose it here)
        if self.tado_coordinator.generation != GEN_X:
            state = self._current_state
            if state and state.setting:
                if hvac_mode := _ac_mode_to_hvac(str(state.setting.mode)):
                    return hvac_mode

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

        # Check activity data points if available (safe for both v3 and Tado X)
        if hasattr(state, "activity_data_points") and state.activity_data_points:
            # AC power check (primarily for v3 AC zones)
            if ac_p := getattr(state.activity_data_points, "ac_power", None):
                if hasattr(ac_p, "value"):
                    return str(ac_p.value) == POWER_ON
            # Heating power check (both v3 and Tado X)
            if h_p := getattr(state.activity_data_points, "heating_power", None):
                if hasattr(h_p, "percentage"):
                    return float(h_p.percentage) > 0

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

    async def _async_set_fan_only_mode(self) -> None:
        """Set FAN mode with required fan settings."""
        state = self._current_state
        capabilities = await self.tado_coordinator.async_get_capabilities(self._zone_id)

        if not capabilities or not (
            fan_mode_caps := getattr(capabilities, "fan", None)
        ):
            _LOGGER.error(
                "Cannot set FAN mode for zone %d: No FAN capabilities", self._zone_id
            )
            return

        additional_fields: dict[str, Any] = {}

        if fan_speeds := getattr(fan_mode_caps, "fan_speeds", None):
            current = getattr(state.setting, "fan_speed", None) if state else None
            fan_value = current if current in fan_speeds else fan_speeds[0]
            additional_fields["fanSpeed"] = str(fan_value).upper()

        if fan_levels := getattr(fan_mode_caps, "fan_level", None):
            current = getattr(state.setting, "fan_level", None) if state else None
            fan_value = current if current in fan_levels else fan_levels[0]
            additional_fields["fanLevel"] = str(fan_value).upper()

        # Build swing settings (carry over from current state or use defaults)
        for cap_attr, api_key, state_attr in [
            ("vertical_swing", "verticalSwing", "vertical_swing"),
            ("horizontal_swing", "horizontalSwing", "horizontal_swing"),
            ("swing", "swing", "swing"),
        ]:
            if swing_caps := getattr(fan_mode_caps, cap_attr, None):
                current = getattr(state.setting, state_attr, None) if state else None
                swing_value = (
                    current
                    if current in swing_caps
                    else ("OFF" if "OFF" in swing_caps else swing_caps[0])
                )
                additional_fields[api_key] = str(swing_value).upper()

        await self.tado_coordinator.async_set_zone_overlay(
            zone_id=self._zone_id,
            power=POWER_ON,
            temperature=None,
            overlay_mode=OVERLAY_MANUAL,
            ac_mode="FAN",
            additional_setting_fields=additional_fields,
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

        modes = get_ac_capabilities(capabilities)["vertical_swings"]
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

            if ac_caps["vertical_swings"]:
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

            if ac_caps["vertical_swings"]:
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


class TadoHeating(TadoClimateEntity):
    """Climate entity for Heating zones (V2 - cloud polling)."""

    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_min_temp = 5.0
    _attr_max_temp = 25.0
    _attr_target_temperature_step = 0.5
    _attr_hvac_modes: ClassVar[list[HVACMode]] = [  # type: ignore[misc]
        HVACMode.OFF,
        HVACMode.HEAT,
        HVACMode.AUTO,
    ]

    def __init__(
        self, coordinator: TadoDataUpdateCoordinator, zone_id: int, zone_name: str
    ) -> None:
        """Initialize heating climate entity."""
        super().__init__(
            coordinator,
            "heating",
            zone_id,
            zone_name,
            default_temp=21.0,
            min_temp=5.0,
        )
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_climate_heating_{zone_id}"
        )

    def _get_active_hvac_mode(self) -> HVACMode:
        """Return HVAC mode when power is ON."""
        return HVACMode.HEAT

    def _is_active(self, state: Any) -> bool:
        """Check if heating is active."""
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

        # Optimistic state
        opt = self.tado_coordinator.optimistic
        is_optimistic = (
            opt.get_zone_temperature(self._zone_id) is not None
            or opt.get_zone_overlay(self._zone_id) is not None
        )

        if is_optimistic and current_temp is not None and target_temp is not None:
            return current_temp < target_temp

        # Heating power from API
        if hasattr(state, "activity_data_points") and state.activity_data_points:
            if h_p := getattr(state.activity_data_points, "heating_power", None):
                if hasattr(h_p, "percentage"):
                    return float(h_p.percentage) > 0

        if current_temp is None or target_temp is None:
            return False

        return current_temp < target_temp

    def _get_active_hvac_action(self) -> HVACAction:
        """Return current action."""
        return HVACAction.HEATING
