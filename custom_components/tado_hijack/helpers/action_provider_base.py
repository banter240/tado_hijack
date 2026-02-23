"""Abstract base for generation-specific action providers."""

from __future__ import annotations

from abc import ABC, abstractmethod


class TadoActionProvider(ABC):
    """Abstract base class for generation-specific Tado actions.

    Isolates v3 vs Tado X differences to maximize maintainability.
    If Tado X bugs, v3 remains unaffected and vice versa.
    """

    @abstractmethod
    async def async_resume_all_schedules(self) -> None:
        """Resume schedule for all active heating zones."""

    @abstractmethod
    async def async_boost_all_zones(self) -> None:
        """Boost all active heating zones to 25°C."""

    @abstractmethod
    async def async_turn_off_all_zones(self) -> None:
        """Turn off all active heating zones."""

    @abstractmethod
    def get_active_zone_ids(
        self,
        include_heating: bool = False,
        include_hot_water: bool = False,
        include_ac: bool = False,
    ) -> list[int]:
        """Get list of active zone IDs.

        Handles id vs room_id internally based on generation.

        Args:
            include_heating: Include heating zones
            include_hot_water: Include hot water zones
            include_ac: Include AC zones

        Returns:
            List of zone IDs (int)

        """

    @abstractmethod
    def is_zone_in_schedule(self, zone_id: int) -> bool | None:
        """Check if zone is in schedule mode (no manual overlay).

        Args:
            zone_id: The zone ID to check

        Returns:
            True if in schedule, False if manual overlay active, None if unknown

        """

    @abstractmethod
    def get_zone_power(self, zone_id: int) -> str | None:
        """Get current power state of zone.

        Args:
            zone_id: The zone ID to check

        Returns:
            "ON", "OFF", or None if unknown

        """

    @abstractmethod
    def get_zone_temperature(self, zone_id: int) -> float | None:
        """Get current target temperature of zone.

        Args:
            zone_id: The zone ID to check

        Returns:
            Temperature in Celsius or None if unknown/not applicable

        """

    @abstractmethod
    async def async_set_ac_setting(self, zone_id: int, key: str, value: str) -> None:
        """Set an AC specific setting (fan speed, swing, temperature, etc.).

        Args:
            zone_id: The zone ID
            key: Setting key (e.g. 'fan_speed', 'mode')
            value: Setting value

        """
