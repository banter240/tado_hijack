"""Unified Data Container for Tado Hijack.

This layer provides a flat container for data objects from different Tado generations.
Entities use Duck Typing to access attributes, allowing for a seamless hybrid mode.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..const import GEN_CLASSIC
from ..models import RateLimit


@runtime_checkable
class UnifiedDataProvider(Protocol):
    """Protocol for a generation-specific data and action provider."""

    async def async_fetch_unified_data(self) -> UnifiedTadoData:
        """Fetch full data snapshot."""
        ...

    def is_feature_supported(self, feature: str) -> bool:
        """Check if a specific feature is supported by this generation."""
        ...

    async def async_set_temperature_offset(self, serial_no: str, offset: float) -> None:
        """Set temperature offset for a device."""
        ...

    def is_device_compatible(self, device_type: str) -> bool:
        """Check if device type is compatible with this generation.

        Args:
            device_type: Device type string (e.g., "IB01", "IB02", "GW01")

        Returns:
            True if device is compatible with this generation

        """
        ...

    def get_bridge_device_types(self) -> set[str]:
        """Get set of bridge device types for this generation.

        Returns:
            Set of device type strings that are bridges for this generation

        """
        ...

    async def async_fetch_zones(self) -> dict[str, Any]:
        """Fetch zone/room states (fast poll)."""
        ...

    async def async_fetch_metadata(self) -> tuple[dict[int, Any], dict[str, Any]]:
        """Fetch metadata: zones and devices (slow poll)."""
        ...

    async def async_fetch_home_state(self) -> Any:
        """Fetch presence/home state (v3 only; Tado X embeds it in metadata)."""
        ...

    async def async_fetch_capabilities(self, zone_id: int) -> Any:
        """Fetch capabilities for a zone (v3 only)."""
        ...

    async def async_fetch_away_config(self, zone_id: int) -> float | None:
        """Fetch away configuration for a zone (v3 only)."""
        ...


@dataclass
class UnifiedTadoData:
    """The central data container used by the Coordinator.

    Attributes match the original Tado Hijack TadoData structure.
    Holds either tadoasync models (v3) or Hops models (X).
    """

    api_status: str = "online"
    home_state: Any = None
    zone_states: dict[str, Any] = field(default_factory=dict)
    zones: dict[int, Any] = field(default_factory=dict)
    devices: dict[str, Any] = field(default_factory=dict)
    capabilities: dict[int, Any] = field(default_factory=dict)
    offsets: dict[str, Any] = field(default_factory=dict)
    away_config: dict[int, float] = field(default_factory=dict)
    generation: str = GEN_CLASSIC
    rate_limit: RateLimit = field(default_factory=lambda: RateLimit(0, 0))
    limit: int = 0
    remaining: int = 0
