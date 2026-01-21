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
        self.capabilities_cache: dict[int, Any] = {}
        self.offsets_cache: dict[str, TemperatureOffset] = {}
        self.away_cache: dict[int, float] = {}
        self._last_slow_poll: float = 0
        # Start timers at boot time to prevent immediate fetch
        self._last_offset_poll: float = time.monotonic()
        self._last_away_poll: float = time.monotonic()
        self._offset_invalidated: bool = False
        self._away_invalidated: bool = False

    async def fetch_full_update(self) -> dict[str, Any]:
        """Perform a data fetch using fast/slow track logic."""
        current_time = time.monotonic()

        # Batteries & Metadata
        if (
            not self.zones_meta
            or (current_time - self._last_slow_poll) > self._slow_poll_seconds
        ):
            _LOGGER.info("DataManager: Fetching slow-track metadata")
            zones = await self._tado.get_zones()
            devices = await self._tado.get_devices()
            self.zones_meta = {zone.id: zone for zone in zones}
            self.devices_meta = {dev.short_serial_no: dev for dev in devices}

            # Fetch capabilities for AC and Hot Water zones
            for zone in zones:
                if zone.type in ("AIR_CONDITIONING", "HOT_WATER"):
                    try:
                        self.capabilities_cache[
                            zone.id
                        ] = await self._tado.get_capabilities(zone.id)
                    except Exception as err:
                        _LOGGER.warning(
                            "Failed to fetch capabilities for zone %d: %s", zone.id, err
                        )

            # Find Internet Bridge devices for linking
            self.coordinator.bridges = [
                dev for dev in devices if dev.device_type.startswith("IB")
            ]

            self._last_slow_poll = current_time

        # Temperature offsets
        if self._offset_invalidated or (
            self._offset_poll_seconds > 0
            and (current_time - self._last_offset_poll) > self._offset_poll_seconds
        ):
            await self._fetch_offsets()
            self._last_offset_poll = current_time
            self._offset_invalidated = False

        # Away configurations
        if self._away_invalidated:
            await self._fetch_away_config()
            self._last_away_poll = current_time
            self._away_invalidated = False

        # States
        _LOGGER.debug("DataManager: Fetching fast-track states")
        home_state = await self._tado.get_home_state()
        zone_states = await self._tado.get_zone_states()

        return {
            "home_state": home_state,
            "zone_states": zone_states,
            "zones": list(self.zones_meta.values()),
            "devices": list(self.devices_meta.values()),
            "capabilities": self.capabilities_cache,
            "offsets": self.offsets_cache,
            "away_config": self.away_cache,
        }

    def invalidate_cache(self, refresh_type: str = "all") -> None:
        """Force specific cache refresh on next poll."""
        if refresh_type in {"all", "metadata"}:
            self.zones_meta = {}
        if refresh_type in {"all", "offsets"}:
            self._offset_invalidated = True
        if refresh_type in {"all", "away"}:
            self._away_invalidated = True

    async def _fetch_offsets(self) -> None:
        """Fetch temperature offsets for all devices with temp sensor capability."""
        if not self.devices_meta:
            _LOGGER.debug("DataManager: No devices cached, skipping offset fetch")
            return

        devices_with_temp = [
            dev
            for dev in self.devices_meta.values()
            if CAPABILITY_INSIDE_TEMP in (dev.characteristics.capabilities or [])
        ]

        if not devices_with_temp:
            return

        _LOGGER.info(
            "DataManager: Fetching offsets for %d devices", len(devices_with_temp)
        )

        for device in devices_with_temp:
            try:
                offset = await self.coordinator.client.get_device_info(
                    device.serial_no, TEMP_OFFSET_ATTR
                )
                if isinstance(offset, TemperatureOffset):
                    self.offsets_cache[device.serial_no] = offset
            except TadoConnectionError as err:
                _LOGGER.warning(
                    "DataManager: Failed to fetch offset for %s: %s",
                    device.short_serial_no,
                    err,
                )

    async def _fetch_away_config(self) -> None:
        """Fetch away configuration for all heating zones."""
        if not self.zones_meta:
            _LOGGER.debug("DataManager: No zones cached, skipping away fetch")
            return

        heating_zones = [
            z for z in self.zones_meta.values() if getattr(z, "type", "") == "HEATING"
        ]

        if not heating_zones:
            return

        _LOGGER.info(
            "DataManager: Fetching away config for %d zones", len(heating_zones)
        )

        for zone in heating_zones:
            try:
                config = await self.coordinator.client.get_away_configuration(zone.id)
                if "minimumAwayTemperature" in config:
                    temp = config["minimumAwayTemperature"].get("celsius")
                    if temp is not None:
                        self.away_cache[zone.id] = float(temp)
            except Exception as err:
                _LOGGER.warning(
                    "DataManager: Failed to fetch away config for zone %d: %s",
                    zone.id,
                    err,
                )
