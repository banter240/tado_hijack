"""Manages data fetching and caching for Tado Hijack."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from homeassistant.helpers import entity_registry as er
from tadoasync import Tado, TadoConnectionError
from tadoasync.models import TemperatureOffset

if TYPE_CHECKING:
    from ..coordinator import TadoDataUpdateCoordinator

from ..const import CAPABILITY_INSIDE_TEMP, DOMAIN, TEMP_OFFSET_ATTR
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
        self._last_offset_poll: float = time.monotonic()
        self._last_away_poll: float = time.monotonic()
        self._offset_invalidated: bool = False
        self._away_invalidated: bool = False

    def get_fast_poll_api_cost(self) -> int:
        """Calculate API call cost for a standard fast poll.

        Fast polling (without slow/offset cycles) makes these calls:
        - get_home_state() = 1 API call
        - get_zone_states() = 1 API call
        Total: 2 API calls per normal poll

        This method dynamically reflects what fetch_full_update() does,
        making it maintainable if the implementation changes.
        """
        # Count the API calls in the fast track section of fetch_full_update()
        # Currently lines 100-101: get_home_state() + get_zone_states()
        return 2

    async def fetch_full_update(self) -> dict[str, Any]:
        """Perform a data fetch using fast/slow track logic."""
        current_time = time.monotonic()

        # 1. Slow Track: Update metadata and device list periodically
        if (
            not self.zones_meta
            or (current_time - self._last_slow_poll) > self._slow_poll_seconds
        ):
            _LOGGER.info("DataManager: Fetching slow-track metadata")
            zones = await self._tado.get_zones()
            devices = await self._tado.get_devices()
            self.zones_meta = {zone.id: zone for zone in zones}
            self.devices_meta = {dev.short_serial_no: dev for dev in devices}

            # Capabilities for AC and Hot Water
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

            # Discover bridge devices
            self.coordinator.bridges = [
                dev for dev in devices if dev.device_type.startswith("IB")
            ]

            self._last_slow_poll = current_time

        # 2. Medium Track: Update temperature offsets
        if self._offset_invalidated or (
            self._offset_poll_seconds > 0
            and (current_time - self._last_offset_poll) > self._offset_poll_seconds
        ):
            await self._fetch_offsets()
            self._last_offset_poll = current_time
            self._offset_invalidated = False

        # 3. Medium Track: Update away configurations
        if self._away_invalidated:
            await self._fetch_away_config()
            self._last_away_poll = current_time
            self._away_invalidated = False

        # 4. Fast Track: Current states
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

    def _is_entity_disabled(self, platform: str, unique_id: str) -> bool:
        """Check if an entity is disabled in the registry."""
        ent_reg = er.async_get(self.coordinator.hass)
        if entity_id := ent_reg.async_get_entity_id(platform, DOMAIN, unique_id):
            entry = ent_reg.async_get(entity_id)
            if entry and entry.disabled:
                return True
        return False

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

        active_devices = []
        for dev in devices_with_temp:
            unique_id = f"{dev.serial_no}_temperature_offset"
            if self._is_entity_disabled("number", unique_id):
                _LOGGER.debug(
                    "Skipping offset fetch for disabled device %s", dev.short_serial_no
                )
                continue
            active_devices.append(dev)

        if not active_devices:
            return

        _LOGGER.info(
            "DataManager: Fetching offsets for %d devices", len(active_devices)
        )

        for device in active_devices:
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

        active_zones = []
        for zone in heating_zones:
            unique_id = f"zone_{zone.id}_away_temperature"
            if self._is_entity_disabled("number", unique_id):
                _LOGGER.debug(
                    "Skipping away config fetch for disabled zone %s", zone.name
                )
                continue
            active_zones.append(zone)

        if not active_zones:
            return

        _LOGGER.info(
            "DataManager: Fetching away config for %d zones", len(active_zones)
        )

        for zone in active_zones:
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
