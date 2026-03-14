"""Tado X specific action provider."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..action_provider_base import TadoActionProvider
from ..discovery import yield_zones
from ..logging_utils import get_redacted_logger

if TYPE_CHECKING:
    from ...coordinator import TadoDataUpdateCoordinator

_LOGGER = get_redacted_logger(__name__)


class TadoXActionProvider(TadoActionProvider):
    """Tado X implementation of action provider.

    Uses direct tadox_bridge API calls (bulk quickActions).
    """

    def __init__(self, coordinator: TadoDataUpdateCoordinator) -> None:
        """Initialize Tado X action provider."""
        self.coordinator = coordinator
        self.bridge = coordinator.tadox_bridge

    async def async_resume_all_schedules(self) -> None:
        """Resume schedule for all zones (Tado X bulk API)."""
        _LOGGER.debug("Resume all schedules triggered (Tado X)")
        await self.bridge.async_resume_all_schedules()
        self.coordinator.async_update_listeners()

    async def async_boost_all_zones(self) -> None:
        """Boost all zones (Tado X bulk API)."""
        _LOGGER.debug("Boost all zones triggered (Tado X)")
        await self.bridge.async_boost_all()
        self.coordinator.async_update_listeners()

    async def async_turn_off_all_zones(self) -> None:
        """Turn off all zones (Tado X bulk API)."""
        _LOGGER.debug("Turn off all zones triggered (Tado X)")
        await self.bridge.async_turn_off_all_zones()
        self.coordinator.async_update_listeners()

    def get_active_zone_ids(
        self,
        include_heating: bool = False,
        include_hot_water: bool = False,
        include_ac: bool = False,
    ) -> list[int]:
        """Get active zone IDs."""
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
        """Check if zone is in schedule (Tado X)."""
        cache_state = self.coordinator.optimistic.get_zone(zone_id)
        return not cache_state.get("overlay_active", True) if cache_state else None

    def get_zone_power(self, zone_id: int) -> str | None:
        """Get zone power state (Tado X)."""
        cache_state = self.coordinator.optimistic.get_zone(zone_id)
        return cache_state.get("power") if cache_state else None

    def get_zone_temperature(self, zone_id: int) -> float | None:
        """Get zone target temperature (Tado X)."""
        cache_state = self.coordinator.optimistic.get_zone(zone_id)
        return cache_state.get("temperature") if cache_state else None

    async def async_set_ac_setting(self, zone_id: int, key: str, value: str) -> None:
        """Set an AC specific setting (Tado X).

        Tado X (Hops API) currently manages AC via Matter or different API structures.
        This provides a basic compatibility stub.
        """
        pass

    async def async_set_temperature_offset(self, serial_no: str, offset: float) -> None:
        """Set temperature offset for a Tado X device."""
        if dev := self.coordinator.data_manager.devices_meta.get(serial_no):
            dev.temperature_offset = offset
        self.coordinator.async_update_listeners()
        if self.coordinator.provider:
            await self.coordinator.provider.async_set_temperature_offset(
                serial_no, offset
            )
