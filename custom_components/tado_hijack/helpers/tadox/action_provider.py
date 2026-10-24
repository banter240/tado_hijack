"""Tado X specific action provider."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...const import BOOST_MODE_TEMP, POWER_OFF, POWER_ON
from ...models import CommandType, TadoCommand
from ..action_provider_base import TadoActionProvider
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

    def _queue_quick_action(self, action: str) -> None:
        """Last house-wide quick action in the debounce window wins."""
        _LOGGER.info("Queued Tado X quick action '%s'", action)
        self.coordinator.api_manager.queue_command(
            "x_quick_action",
            TadoCommand(CommandType.QUICK_ACTION, data={"action": action}),
        )

    async def async_resume_all_schedules(self) -> None:
        """Resume schedule for all zones (Tado X bulk API)."""
        zone_ids = self.get_active_zone_ids(include_heating=True)
        for zone_id in zone_ids:
            self.coordinator.offline_fallback.remember_schedule(zone_id)
        self._queue_quick_action("resume_all")
        for zone_id in zone_ids:
            self.coordinator.recovery_queue.capture_resume(zone_id)

    async def async_boost_all_zones(self) -> None:
        """Boost all zones (Tado X bulk API)."""
        zone_ids = self.get_active_zone_ids(include_heating=True)
        for zone_id in zone_ids:
            self.coordinator.offline_fallback.remember_manual(
                zone_id, power=POWER_ON, temperature=BOOST_MODE_TEMP
            )
        self._queue_quick_action("boost_all")
        for zone_id in zone_ids:
            self.coordinator.recovery_queue.capture_overlay(
                zone_id, power=POWER_ON, temperature=BOOST_MODE_TEMP
            )

    async def async_turn_off_all_zones(self) -> None:
        """Turn off all zones (Tado X bulk API)."""
        zone_ids = self.get_active_zone_ids(include_heating=True)
        for zone_id in zone_ids:
            self.coordinator.offline_fallback.remember_manual(zone_id, power=POWER_OFF)
        self._queue_quick_action("all_off")
        for zone_id in zone_ids:
            self.coordinator.recovery_queue.capture_overlay(
                zone_id, power=POWER_OFF, temperature=None
            )

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
