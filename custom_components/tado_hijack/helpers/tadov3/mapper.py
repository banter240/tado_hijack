"""Mapper and Data Orchestrator for Tado V3 (Classic)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tadoasync.models import TemperatureOffset

from ..logging_utils import get_redacted_logger
from ..models_unified import UnifiedTadoData

if TYPE_CHECKING:
    from ..client import TadoHijackClient

_LOGGER = get_redacted_logger(__name__)


class TadoV3Mapper:
    """Orchestrates Tado V3 data fetching and maps it to Unified models.

    Acts as a wrapper around the legacy TadoHijackClient to satisfy the
    UnifiedDataProvider protocol.
    """

    def __init__(self, client: TadoHijackClient) -> None:
        """Initialize the Tado V3 mapper."""
        self.client = client

    async def async_fetch_unified_data(self) -> UnifiedTadoData:
        """Fetch full data snapshot (Legacy compat).

        Not used in the new granular polling architecture, but kept for protocol completeness.
        """
        # This would require fetching everything.
        # We rely on DataManager to call granular methods.
        raise NotImplementedError("Use granular fetch methods for V3")

    async def async_fetch_zones(self) -> dict[str, Any]:
        """Fetch zone states (Fast Poll)."""
        # Returns dict[int, ZoneState], we convert keys to str for consistency
        states = await self.client.get_zone_states()
        return {str(k): v for k, v in states.items()}

    async def async_fetch_metadata(self) -> tuple[dict[int, Any], dict[str, Any]]:
        """Fetch static metadata (Slow Poll)."""
        zones = await self.client.get_zones()
        devices = await self.client.get_devices()

        zones_meta = {z.id: z for z in zones}
        devices_meta = {d.short_serial_no: d for d in devices}

        return zones_meta, devices_meta

    async def async_fetch_home_state(self) -> Any:
        """Fetch presence/home state."""
        return await self.client.get_home_state()

    async def async_fetch_capabilities(self, zone_id: int) -> Any:
        """Fetch capabilities for a zone."""
        return await self.client.get_capabilities(zone_id)

    async def async_fetch_away_config(self, zone_id: int) -> float | None:
        """Fetch away configuration for a zone."""
        cfg = await self.client.get_away_configuration(zone_id)
        if (
            "minimumAwayTemperature" in cfg
            and (t := cfg["minimumAwayTemperature"].get("celsius")) is not None
        ):
            return float(t)
        return None

    async def async_fetch_offsets(self) -> dict[str, Any]:
        """Fetch temperature offsets.

        WARNING: This method signature implies fetching ALL offsets.
        Since V3 requires 1 API call per device, we should NOT use this blindly
        without throttling/filtering.

        Ideally, DataManager should call a specific method with a device list.
        But to satisfy protocol, we return empty here and handle logic in DataManager?
        Or we implement a helper `async_fetch_device_offset`.
        """
        return {}

    async def async_fetch_device_offset(self, serial: str) -> TemperatureOffset:
        """Fetch offset for a single device (V3 specific helper)."""
        off = await self.client.get_device_info(serial, "temperatureOffset")
        if isinstance(off, TemperatureOffset):
            return off
        raise ValueError(f"Invalid offset response for {serial}")

    def is_feature_supported(self, feature: str) -> bool:
        """Check if a specific Hijack feature is supported by Tado V3 hardware."""
        # V3 supports everything by default (legacy behavior)
        # Add items to blacklist if discovered otherwise
        unsupported: tuple[str, ...] = ()
        return feature not in unsupported

    def is_device_compatible(self, device_type: str) -> bool:
        """Check if device is compatible with Tado V3 generation."""
        # V3 supports everything NOT being IB02/X-specific?
        # Actually V3 supports almost everything.
        return True

    def get_bridge_device_types(self) -> set[str]:
        """Get bridge device types for Tado V3."""
        from ...const import DEVICE_TYPE_GW01, DEVICE_TYPE_IB01

        return {DEVICE_TYPE_IB01, DEVICE_TYPE_GW01}

    async def async_set_temperature_offset(self, serial_no: str, offset: float) -> None:
        """Set temperature offset via V3 API."""
        await self.client.set_temperature_offset(serial_no, offset)
