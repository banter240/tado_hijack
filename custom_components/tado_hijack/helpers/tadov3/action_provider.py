"""Tado Classic (v3) specific action provider."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...const import BOOST_MODE_TEMP, POWER_OFF, POWER_ON
from ...models import CommandType, TadoCommand
from ..action_provider_base import TadoActionProvider
from ..discovery import yield_zones
from ..logging_utils import get_redacted_logger
from ..overlay_builder import build_overlay_data
from ..state_patcher import patch_zone_overlay, patch_zone_resume

if TYPE_CHECKING:
    from ...coordinator import TadoDataUpdateCoordinator

_LOGGER = get_redacted_logger(__name__)


class TadoV3ActionProvider(TadoActionProvider):
    """Tado Classic (v3) implementation of action provider.

    Uses api_manager queue system for batching and merging.
    """

    def __init__(self, coordinator: TadoDataUpdateCoordinator) -> None:
        """Initialize v3 action provider."""
        self.coordinator = coordinator

    async def async_resume_all_schedules(self) -> None:
        """Resume schedule for all active zones (v3)."""
        active_zones = self.get_active_zone_ids(include_heating=True, include_ac=True)

        if not active_zones:
            _LOGGER.warning("No active zones to resume")
            return

        _LOGGER.info("Queued resume schedules for %d active zones", len(active_zones))

        for zone_id in active_zones:
            old_state = patch_zone_resume(
                self.coordinator.data.zone_states.get(str(zone_id))
            )

            self.coordinator.optimistic.set_zone(zone_id, False)

            self.coordinator.api_manager.queue_command(
                f"zone_{zone_id}",
                TadoCommand(
                    CommandType.RESUME_SCHEDULE,
                    zone_id=zone_id,
                    rollback_context=old_state,
                ),
            )

        self.coordinator.async_update_listeners()

    async def async_boost_all_zones(self) -> None:
        """Boost all active zones to 25°C (v3)."""
        self._apply_bulk_zone_overlay(
            command_key="boost_all",
            setting={"power": POWER_ON, "temperature": {"celsius": BOOST_MODE_TEMP}},
            action_name="boost",
        )

    async def async_turn_off_all_zones(self) -> None:
        """Turn off all active zones (v3)."""
        self._apply_bulk_zone_overlay(
            command_key="turn_off_all",
            setting={"power": POWER_OFF},
            action_name="turn off",
        )

    def _apply_bulk_zone_overlay(
        self,
        command_key: str,
        setting: dict[str, Any],
        action_name: str,
    ) -> None:
        """Apply same overlay setting to all active zones (DRY helper)."""
        zone_ids = self.get_active_zone_ids(include_heating=True, include_ac=True)

        if not zone_ids:
            _LOGGER.warning("No active zones to %s", action_name)
            return

        _LOGGER.info("Queued %s for %d active zones", action_name, len(zone_ids))

        for zone_id in zone_ids:
            data = build_overlay_data(
                zone_id=zone_id,
                zones_meta=self.coordinator.zones_meta,
                power=setting.get("power", POWER_ON),
                temperature=setting.get("temperature", {}).get("celsius"),
                overlay_type=setting.get("type"),
                supports_temp=self.coordinator.supports_temperature(zone_id),
            )

            old_state = patch_zone_overlay(
                self.coordinator.data.zone_states.get(str(zone_id)), data
            )

            self.coordinator.optimistic.apply_zone_state(
                zone_id,
                overlay=True,
                power=setting.get("power", POWER_ON),
                temperature=setting.get("temperature", {}).get("celsius"),
            )

            self.coordinator.api_manager.queue_command(
                f"zone_{zone_id}",
                TadoCommand(
                    CommandType.SET_OVERLAY,
                    zone_id=zone_id,
                    data=data,
                    rollback_context=old_state,
                ),
            )

        self.coordinator.async_update_listeners()

    def get_active_zone_ids(
        self,
        include_heating: bool = False,
        include_hot_water: bool = False,
        include_ac: bool = False,
    ) -> list[int]:
        """Get active zone IDs (v3 uses zone.id)."""
        return [
            zone.id
            for zone in yield_zones(
                self.coordinator,
                include_heating=include_heating,
                include_hot_water=include_hot_water,
                include_ac=include_ac,
            )
            if not self.coordinator.entity_resolver.is_zone_disabled(zone.id)
        ]

    def is_zone_in_schedule(self, zone_id: int) -> bool | None:
        """Check if zone is in schedule (v3)."""
        cache_state = self.coordinator.optimistic.get_zone(zone_id)
        return not cache_state.get("overlay_active", True) if cache_state else None

    def get_zone_power(self, zone_id: int) -> str | None:
        """Get zone power state (v3)."""
        cache_state = self.coordinator.optimistic.get_zone(zone_id)
        return cache_state.get("power") if cache_state else None

    def get_zone_temperature(self, zone_id: int) -> float | None:
        """Get zone target temperature (v3)."""
        cache_state = self.coordinator.optimistic.get_zone(zone_id)
        return cache_state.get("temperature") if cache_state else None

    async def async_set_ac_setting(self, zone_id: int, key: str, value: str) -> None:
        """Set an AC specific setting (v3) respecting hardware capabilities."""
        state = self.coordinator.data.zone_states.get(str(zone_id))
        if not state or not getattr(state, "setting", None):
            _LOGGER.error("Cannot set AC setting: No state for zone %d", zone_id)
            return

        from .parsers import get_overlay_type, resolve_ac_mode

        opt_mode = self.coordinator.optimistic.get_zone_ac_mode(zone_id)
        current_mode = resolve_ac_mode(opt_mode, state)
        if key == "mode":
            current_mode = value

        caps = await self.coordinator.async_get_capabilities(zone_id)
        mode_caps = getattr(caps, current_mode.lower(), None) if caps else None

        additional_fields: dict[str, Any] = {}
        temperature: float | None = None

        if mode_caps:
            temperature = self._build_ac_temperature(mode_caps, key, value, state)
            additional_fields |= self._build_ac_fan_settings(
                mode_caps, key, value, state
            )
            additional_fields |= self._build_ac_swing_settings(
                mode_caps, key, value, state, zone_id
            )

        data = build_overlay_data(
            zone_id,
            self.coordinator.zones_meta,
            power=POWER_ON,
            temperature=temperature,
            ac_mode=current_mode,
            overlay_type=get_overlay_type(state),
            supports_temp=True,
            additional_setting_fields=additional_fields,
        )

        old_state = patch_zone_overlay(
            self.coordinator.data.zone_states.get(str(zone_id)), data
        )

        self.coordinator.optimistic.apply_zone_state(
            zone_id,
            overlay=True,
            power=POWER_ON,
            ac_mode=current_mode,
            vertical_swing=value if key == "vertical_swing" else None,
            horizontal_swing=value if key == "horizontal_swing" else None,
        )
        self.coordinator.async_update_listeners()

        self.coordinator.api_manager.queue_command(
            f"zone_{zone_id}",
            TadoCommand(
                CommandType.SET_OVERLAY,
                zone_id=zone_id,
                data=data,
                rollback_context=old_state,
            ),
        )

    def _build_ac_temperature(
        self, mode_caps: Any, key: str, value: str, state: Any
    ) -> float | None:
        """Extract AC temperature based on capabilities and input."""
        if not getattr(mode_caps, "temperatures", None):
            return None
        if key == "temperature":
            return float(value)
        if getattr(state.setting, "temperature", None):
            return float(state.setting.temperature.celsius)
        return None

    def _build_ac_fan_settings(
        self, mode_caps: Any, key: str, value: str, state: Any
    ) -> dict[str, str]:
        """Extract AC fan settings based on capabilities and input."""
        fields: dict[str, str] = {}

        if fan_caps := getattr(mode_caps, "fan_speeds", None):
            val = (
                value
                if key == "fan_speed"
                else getattr(state.setting, "fan_speed", None)
            )
            if val:
                val = val.upper()
            fields["fanSpeed"] = str(val if val in fan_caps else fan_caps[0])

        if lvl_caps := getattr(mode_caps, "fan_level", None):
            val = (
                value
                if key in {"fan_level", "fan_speed"}
                else getattr(state.setting, "fan_level", None)
            )
            if val:
                val = val.upper()
            fields["fanLevel"] = str(val if val in lvl_caps else lvl_caps[0])
        elif val := getattr(state.setting, "fan_level", None):
            val = val.upper()
            fields["fanLevel"] = str(val)

        return fields

    def _build_ac_swing_settings(
        self, mode_caps: Any, key: str, value: str, state: Any, zone_id: int
    ) -> dict[str, str]:
        """Extract AC swing settings based on capabilities and input."""
        fields: dict[str, str] = {}
        swing_mappings = [
            ("vertical_swing", "verticalSwing", "vertical_swing"),
            ("horizontal_swing", "horizontalSwing", "horizontal_swing"),
            ("swing", "swing", "swing"),
        ]

        for cap_name, api_key, attr_name in swing_mappings:
            if cap_values := getattr(mode_caps, cap_name, None):
                opt_val = self.coordinator.optimistic.get_optimistic(
                    "zone", zone_id, attr_name
                ) or getattr(state.setting, attr_name, None)

                val = value if key == attr_name else opt_val
                if val:
                    val = val.upper()
                fields[api_key] = str(
                    val
                    if val in cap_values
                    else ("OFF" if "OFF" in cap_values else cap_values[0])
                )
            elif opt_val := self.coordinator.optimistic.get_optimistic(
                "zone", zone_id, attr_name
            ) or getattr(state.setting, attr_name, None):
                val = opt_val.upper()
                fields[api_key] = str(val)

        return fields

    async def async_set_temperature_offset(self, serial_no: str, offset: float) -> None:
        """Set temperature offset for a v3 device."""
        old_val = self.coordinator.data_manager.offsets_cache.get(serial_no)

        from tadoasync.models import TemperatureOffset

        self.coordinator.data_manager.offsets_cache[serial_no] = TemperatureOffset(
            celsius=offset,
            fahrenheit=0.0,
        )

        if old_val:
            import copy

            try:
                old_val = copy.deepcopy(old_val)
            except Exception:
                old_val = None

        from ...models import CommandType

        await self.coordinator.property_manager.async_set_device_property(
            serial_no,
            CommandType.SET_OFFSET,
            {"serial": serial_no, "offset": offset},
            self.coordinator.optimistic.set_offset,
            offset,
            rollback_context=old_val,
        )
