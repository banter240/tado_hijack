"""Mapper and Data Orchestrator for Tado X."""

from __future__ import annotations

from typing import Any

from ...const import GEN_X, TADOX_VIRTUAL_HOT_WATER_ZONE_ID
from ...lib.tadox_api import TadoXApi
from ...lib.tadox_models import TadoXHotWaterState
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
        # None = not probed; True = installed; False = not installed (skip future calls)
        self._hot_water_available: bool | None = None

    async def async_fetch_unified_data(self) -> UnifiedTadoData:
        """Fetch all relevant Tado X data and return a UnifiedTadoData container."""
        _LOGGER.debug("Fetching unified Tado X data from Hops")

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

        home_state = await self.async_fetch_home_state()
        presence = getattr(home_state, "presence", "HOME")
        rooms = snapshot.rooms if snapshot else []
        other_devices = snapshot.other_devices if snapshot else []

        unified_data = UnifiedTadoData(
            home_state=type("HomeState", (), {"presence": presence}),
            api_status="online",
            zones={room.room_id: room for room in rooms},
            limit=0,
            remaining=0,
            generation=GEN_X,
        )

        for state in room_states:
            unified_data.zone_states[str(state.room_id)] = state

        await self._augment_with_hot_water(unified_data.zone_states)

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
        result: dict[str, Any] = {str(state.room_id): state for state in room_states}
        await self._augment_with_hot_water(result)
        return result

    async def async_fetch_metadata(self) -> tuple[dict[int, Any], dict[str, Any]]:
        """Fetch Tado X metadata (slow poll): rooms and devices."""
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

        rooms = snapshot.rooms if snapshot else []
        other_devices = snapshot.other_devices if snapshot else []

        zones_meta: dict[int, Any] = {room.room_id: room for room in rooms}
        all_devices = other_devices + [dev for room in rooms for dev in room.devices]
        devices_meta: dict[str, Any] = {dev.serial_no: dev for dev in all_devices}

        return zones_meta, devices_meta

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

    def get_rate_limit_source(self) -> TadoXApi:
        """Return the Hops API bridge as the rate limit data source."""
        return self.bridge

    async def async_fetch_home_state(self) -> Any:
        """Fetch presence/home state."""
        return await self.bridge.async_get_home_state()

    async def async_fetch_capabilities(self, zone_id: int) -> Any:
        """Not used for Tado X — no separate capabilities endpoint."""
        return None

    async def async_fetch_away_config(self, zone_id: int) -> float | None:
        """Not used for Tado X — no away configuration endpoint."""
        return None

    async def async_set_temperature_offset(self, serial_no: str, offset: float) -> None:
        """Set temperature offset via Hops API."""
        await self.bridge.async_set_temperature_offset(serial_no, offset)

    async def _fetch_hot_water_state_safe(self) -> TadoXHotWaterState | None:
        """Fetch hot water state with caching for unavailable/uncontrollable."""
        if self._hot_water_available is False:
            return None

        try:
            result = await self.bridge.async_get_hot_water_state()
        except Exception as e:
            _LOGGER.debug("Tado X hot water state fetch failed (transient): %s", e)
            return None

        if result is None or not result.is_controllable:
            if self._hot_water_available is not False:
                if result is None:
                    _LOGGER.debug(
                        "Tado X hot water programmer not detected (no hardware)"
                    )
                else:
                    _LOGGER.info(
                        "Tado X hot water not controllable via "
                        "programmer/domesticHotWater (state=%s); "
                        "skipping water_heater entity",
                        result.state,
                    )
                self._hot_water_available = False
            return None

        self._hot_water_available = True
        return result

    async def _augment_with_hot_water(self, zones: dict[str, Any]) -> None:
        """Inject Tado X hot water state from Hops (real hardware, synthetic ID)."""
        if (hw := await self._fetch_hot_water_state_safe()) is not None:
            zones[str(TADOX_VIRTUAL_HOT_WATER_ZONE_ID)] = hw
