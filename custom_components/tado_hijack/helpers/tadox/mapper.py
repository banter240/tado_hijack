"""Mapper and Data Orchestrator for Tado X."""

from __future__ import annotations

from typing import Any

from ...const import GEN_X
from ...lib.tadox_api import TadoXApi
from ..logging_utils import get_redacted_logger
from ..models_unified import UnifiedTadoData

_LOGGER = get_redacted_logger(__name__)


class TadoXMapper:
    """Orchestrates Tado X data fetching and maps it to Unified models.

    This keeps the Coordinator generic.
    """

    def __init__(self, bridge: TadoXApi) -> None:
        """Initialize the Tado X mapper."""
        self.bridge = bridge
        self._last_presence: str = "HOME"

    async def async_fetch_unified_data(self) -> UnifiedTadoData:
        """Fetch all relevant Tado X data and return a UnifiedTadoData container."""
        _LOGGER.debug("Fetching unified Tado X data from Hops")

        # 1. Fetch data from both Hops entry points
        try:
            room_states = await self.bridge.async_get_room_states()
            snapshot = await self.bridge.async_get_rooms_and_devices()
        except Exception as e:
            _LOGGER.error(
                "Tado X unified data fetch FAILED: %s (type: %s)",
                e,
                type(e).__name__,
                exc_info=True,
            )
            room_states = []
            snapshot = None

        # 2. Initialize the unified container with defaults
        presence = "HOME"
        rooms = []
        other_devices = []
        if snapshot:
            # Extract presence from home field
            # Tado X API should always provide home.presence
            if snapshot.home:
                presence = snapshot.home.presence
            else:
                _LOGGER.warning(
                    "Tado X API returned snapshot without home field - using default presence"
                )
            rooms = snapshot.rooms
            other_devices = snapshot.other_devices

        unified_data = UnifiedTadoData(
            home_state=type("HomeState", (), {"presence": presence}),
            api_status="online",
            zones={room.room_id: room for room in rooms},
            limit=0,
            remaining=0,
            generation=GEN_X,
        )

        # 3. Map Rooms (Operational State)
        for state in room_states:
            unified_data.zone_states[str(state.room_id)] = state

        # 4. Map Devices (Hardware Metadata)
        all_hops_devices = other_devices + [
            dev for room in rooms for dev in room.devices
        ]
        for dev in all_hops_devices:
            unified_data.devices[dev.serial_no] = dev

        return unified_data

    async def async_fetch_zones(self) -> dict[str, Any]:
        """Fetch Tado X room states (fast poll)."""
        try:
            room_states = await self.bridge.async_get_room_states()
        except Exception as e:
            _LOGGER.error(
                "Tado X room states fetch FAILED: %s (type: %s)",
                e,
                type(e).__name__,
                exc_info=True,
            )
            return {}
        return {str(state.room_id): state for state in room_states}

    async def async_fetch_metadata(self) -> tuple[dict[int, Any], dict[str, Any]]:
        """Fetch Tado X metadata (slow poll): rooms, devices, and presence."""
        try:
            snapshot = await self.bridge.async_get_rooms_and_devices()
        except Exception as e:
            _LOGGER.error(
                "Tado X metadata fetch FAILED: %s (type: %s)",
                e,
                type(e).__name__,
                exc_info=True,
            )
            return {}, {}

        if snapshot and snapshot.home:
            self._last_presence = snapshot.home.presence
        else:
            _LOGGER.warning(
                "Tado X API returned snapshot without home field - using default presence"
            )

        rooms = snapshot.rooms if snapshot else []
        other_devices = snapshot.other_devices if snapshot else []

        zones_meta: dict[int, Any] = {room.room_id: room for room in rooms}
        all_devices = other_devices + [dev for room in rooms for dev in room.devices]
        devices_meta: dict[str, Any] = {dev.serial_no: dev for dev in all_devices}

        return zones_meta, devices_meta

    def get_last_presence(self) -> str:
        """Return presence from last metadata fetch."""
        return self._last_presence

    def is_feature_supported(self, feature: str) -> bool:
        """Check if a specific Hijack feature is supported by Tado X hardware."""
        unsupported = ("dazzle_mode", "early_start")
        return feature not in unsupported

    def is_device_compatible(self, device_type: str) -> bool:
        """Check if device is compatible with Tado X generation."""
        from ...const import DEVICE_SUFFIX_TADO_X, DEVICE_TYPE_IB02

        # X uses IB02 (Bridge X) and devices ending in "04"
        return (
            device_type == DEVICE_TYPE_IB02
            or device_type.endswith(DEVICE_SUFFIX_TADO_X)
            or "DUMMY" in device_type
        )

    def get_bridge_device_types(self) -> set[str]:
        """Get bridge device types for Tado X."""
        return {"IB02"}

    async def async_fetch_home_state(self) -> Any:
        """Not used for Tado X — presence is embedded in metadata."""
        return None

    async def async_fetch_capabilities(self, zone_id: int) -> Any:
        """Not used for Tado X — no separate capabilities endpoint."""
        return None

    async def async_fetch_away_config(self, zone_id: int) -> float | None:
        """Not used for Tado X — no away configuration endpoint."""
        return None

    async def async_set_temperature_offset(self, serial_no: str, offset: float) -> None:
        """Set temperature offset via Hops API."""
        await self.bridge.async_set_temperature_offset(serial_no, offset)
