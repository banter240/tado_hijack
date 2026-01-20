"""Manages data fetching and caching for Tado Hijack."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from tadoasync import Tado, TadoConnectionError
from tadoasync.models import TemperatureOffset

if TYPE_CHECKING:
    from ..coordinator import TadoDataUpdateCoordinator

from ..const import CAPABILITY_INSIDE_TEMP, TEMP_OFFSET_ATTR
from .logging_utils import get_redacted_logger

_LOGGER = get_redacted_logger(__name__)


class TadoDataManager:
    """Handles fast/slow polling tracks and metadata caching."""

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        client: Tado,
        slow_poll_seconds: int,
        offset_poll_seconds: int = 0,
    ) -> None:
        """Initialize Tado data manager."""
        self.coordinator = coordinator
        self._tado = client
        self._slow_poll_seconds = slow_poll_seconds
        self._offset_poll_seconds = offset_poll_seconds

        # Caches
        self.zones_meta: dict[int, Any] = {}
        self.devices_meta: dict[str, Any] = {}
        self.offsets_cache: dict[str, TemperatureOffset] = {}
        self._last_slow_poll: float = 0
        # Start offset timer at boot time to prevent immediate fetch
        self._last_offset_poll: float = time.monotonic()
        self._offset_invalidated: bool = False

    async def fetch_full_update(self) -> dict[str, Any]:
        """Perform a data fetch using fast/slow track logic."""
        current_time = time.monotonic()

        # 1. SLOW TRACK: Batteries & Metadata
        if (
            not self.zones_meta
            or (current_time - self._last_slow_poll) > self._slow_poll_seconds
        ):
            _LOGGER.info("DataManager: Fetching slow-track metadata")
            zones = await self._tado.get_zones()
            devices = await self._tado.get_devices()
            self.zones_meta = {zone.id: zone for zone in zones}
            self.devices_meta = {dev.short_serial_no: dev for dev in devices}

            # Find Internet Bridge devices for linking
            self.coordinator.bridges = [
                dev for dev in devices if dev.device_type.startswith("IB")
            ]

            self._last_slow_poll = current_time

        # 2. OFFSET TRACK: Temperature offsets (separate timer, not on boot)
        should_fetch_offsets = False
        if self._offset_invalidated:
            # Manual poll triggered
            should_fetch_offsets = True
            self._offset_invalidated = False
        elif self._offset_poll_seconds > 0:
            # Scheduled polling enabled - check if timer elapsed
            if (current_time - self._last_offset_poll) > self._offset_poll_seconds:
                should_fetch_offsets = True

        if should_fetch_offsets:
            await self._fetch_offsets()
            self._last_offset_poll = current_time

        # 3. FAST TRACK: States
        _LOGGER.debug("DataManager: Fetching fast-track states")
        home_state = await self._tado.get_home_state()
        zone_states = await self._tado.get_zone_states()

        return {
            "home_state": home_state,
            "zone_states": zone_states,
            "zones": list(self.zones_meta.values()),
            "devices": list(self.devices_meta.values()),
            "offsets": self.offsets_cache,
        }

    def invalidate_cache(self) -> None:
        """Force metadata and offset refresh on next poll."""
        self.zones_meta = {}
        self._offset_invalidated = True

    async def _fetch_offsets(self) -> None:
        """Fetch temperature offsets for all devices with temp sensor capability.

        Costs 1 API call per device with INSIDE_TEMPERATURE_MEASUREMENT capability.
        """
        if not self.devices_meta:
            _LOGGER.debug("DataManager: No devices cached, skipping offset fetch")
            return

        devices_with_temp = [
            dev
            for dev in self.devices_meta.values()
            if CAPABILITY_INSIDE_TEMP in (dev.characteristics.capabilities or [])
        ]

        if not devices_with_temp:
            _LOGGER.debug("DataManager: No devices with temp capability found")
            return

        _LOGGER.info(
            "DataManager: Fetching offsets for %d devices (1 API call each)",
            len(devices_with_temp),
        )

        for device in devices_with_temp:
            try:
                offset = await self._tado.get_device_info(
                    device.serial_no, TEMP_OFFSET_ATTR
                )
                if isinstance(offset, TemperatureOffset):
                    self.offsets_cache[device.serial_no] = offset
                    _LOGGER.debug(
                        "DataManager: Offset for %s: %.1f°C",
                        device.short_serial_no,
                        offset.celsius,
                    )
            except TadoConnectionError as err:
                _LOGGER.warning(
                    "DataManager: Failed to fetch offset for %s: %s",
                    device.short_serial_no,
                    err,
                )
