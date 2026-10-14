"""Abstract base for generation-specific action providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from .discovery import yield_zones

if TYPE_CHECKING:
    from ..coordinator import TadoDataUpdateCoordinator


class TadoActionProvider(ABC):
    """Abstract base class for generation-specific Tado actions.

    Isolates v3 vs Tado X differences to maximize maintainability.
    If Tado X bugs, v3 remains unaffected and vice versa.
    """

    coordinator: TadoDataUpdateCoordinator

    @abstractmethod
    async def async_resume_all_schedules(self) -> None:
        """Resume schedule for all active heating zones."""

    @abstractmethod
    async def async_boost_all_zones(self) -> None:
        """Boost all active heating zones to 25°C."""

    @abstractmethod
    async def async_turn_off_all_zones(self) -> None:
        """Turn off all active heating zones."""

    def get_active_zone_ids(
        self,
        include_heating: bool = False,
        include_hot_water: bool = False,
        include_ac: bool = False,
    ) -> list[int]:
        """Zone ids that are not disabled. yield_zones hides id vs room_id."""
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
        """True when the optimistic cache has no manual overlay."""
        cache_state = self.coordinator.optimistic.get_zone(zone_id)
        return not cache_state.get("overlay_active", True) if cache_state else None

    def get_zone_power(self, zone_id: int) -> str | None:
        """Optimistic power, or None when the zone is not cached."""
        cache_state = self.coordinator.optimistic.get_zone(zone_id)
        return cache_state.get("power") if cache_state else None

    def get_zone_temperature(self, zone_id: int) -> float | None:
        """Optimistic target temperature, or None when the zone is not cached."""
        cache_state = self.coordinator.optimistic.get_zone(zone_id)
        return cache_state.get("temperature") if cache_state else None

    @abstractmethod
    async def async_set_ac_setting(self, zone_id: int, key: str, value: str) -> None:
        """Set an AC specific setting (fan speed, swing, temperature, etc.).

        Args:
            zone_id: The zone ID
            key: Setting key (e.g. 'fan_speed', 'mode')
            value: Setting value

        """

    @abstractmethod
    async def async_set_temperature_offset(self, serial_no: str, offset: float) -> None:
        """Set temperature offset for a device.

        Args:
            serial_no: The device serial number
            offset: The offset value in Celsius

        """
