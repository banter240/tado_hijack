"""Tado Classic (v3) specific action provider."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...const import BOOST_MODE_TEMP, POWER_OFF, POWER_ON, ZONE_TYPE_HEATING
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
        """Resume schedule for all active heating zones (v3)."""
        active_zones = self.get_active_zone_ids(include_heating=True)

        if not active_zones:
            _LOGGER.warning("No active heating zones to resume")
            return

        _LOGGER.info(
            "Queued resume schedules for %d active heating zones", len(active_zones)
        )

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
        """Boost all active heating zones to 25°C (v3)."""
        self._apply_bulk_zone_overlay(
            command_key="boost_all",
            setting={
                "power": POWER_ON,
                "type": ZONE_TYPE_HEATING,
                "temperature": {"celsius": BOOST_MODE_TEMP},
            },
            action_name="boost",
        )

    async def async_turn_off_all_zones(self) -> None:
        """Turn off all active heating zones (v3)."""
        self._apply_bulk_zone_overlay(
            command_key="turn_off_all",
            setting={"power": POWER_OFF, "type": ZONE_TYPE_HEATING},
            action_name="turn off",
        )

    def _apply_bulk_zone_overlay(
        self,
        command_key: str,
        setting: dict[str, Any],
        action_name: str,
    ) -> None:
        """Apply same overlay setting to all heating zones (DRY helper)."""
        zone_ids = self.get_active_zone_ids(include_heating=True)

        if not zone_ids:
            _LOGGER.warning("No active heating zones to %s", action_name)
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
