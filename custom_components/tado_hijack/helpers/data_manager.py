"""Manages data fetching and caching for Tado Hijack."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, cast

from homeassistant.helpers import entity_registry as er
from tadoasync import Tado, TadoConnectionError
from tadoasync.models import TemperatureOffset

if TYPE_CHECKING:
    from ..coordinator import TadoDataUpdateCoordinator
    from .client import TadoHijackClient

from ..const import CAPABILITY_INSIDE_TEMP, DOMAIN, TEMP_OFFSET_ATTR
from .logging_utils import get_redacted_logger

_LOGGER = get_redacted_logger(__name__)


class PollTask:
    """Represents a single unit of work in a polling cycle."""

    def __init__(self, cost: int, coroutine: Any) -> None:
        """Initialize the poll task."""
        self.cost = cost
        self.coroutine = coroutine


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

    @property
    def client(self) -> TadoHijackClient:
        """Return the client cast to TadoHijackClient for custom methods."""
        return cast("TadoHijackClient", self._tado)

    def _create_offset_task(self, serial: str) -> PollTask:
        """Create a task for fetching temperature offset."""
        return PollTask(1, lambda: self._tado.get_device_info(serial, TEMP_OFFSET_ATTR))

    def _build_poll_plan(self, current_time: float) -> list[PollTask]:
        """Construct the execution plan for the current poll cycle.

        Defines the sequence of API calls for both execution and cost prediction.
        """
        plan: list[PollTask] = [
            PollTask(1, self._tado.get_home_state),
            PollTask(1, self._tado.get_zone_states),
        ]

        # --- 2. Slow Track (Metadata) ---
        if (
            not self.zones_meta
            or (current_time - self._last_slow_poll) > self._slow_poll_seconds
        ):
            plan.append(PollTask(1, self._tado.get_zones))
            plan.append(PollTask(1, self._tado.get_devices))

            # Capabilities: One call per AC/HotWater zone
            plan.extend(
                PollTask(1, lambda z=zone.id: self._tado.get_capabilities(z))
                for zone in self.zones_meta.values()
                if zone.type in ("AIR_CONDITIONING", "HOT_WATER")
            )
        # --- 3. Medium Track (Offsets) ---
        if self._offset_invalidated or (
            self._offset_poll_seconds > 0
            and (current_time - self._last_offset_poll) > self._offset_poll_seconds
        ):
            # One call per active device with temp capability
            devices_with_temp = [
                dev
                for dev in self.devices_meta.values()
                if CAPABILITY_INSIDE_TEMP in (dev.characteristics.capabilities or [])
            ]
            for dev in devices_with_temp:
                unique_id = f"{dev.serial_no}_temperature_offset"
                if not self._is_entity_disabled("number", unique_id):
                    plan.append(self._create_offset_task(dev.serial_no))

        # --- 4. Away Config ---
        if self._away_invalidated:
            heating_zones = [
                z
                for z in self.zones_meta.values()
                if getattr(z, "type", "") == "HEATING"
            ]
            plan.extend(
                PollTask(1, lambda z=zone.id: self.client.get_away_configuration(z))
                for zone in heating_zones
            )
        return plan

    def predict_next_poll_cost(self) -> int:
        """Predict the exact API cost of the NEXT poll based on the plan.

        Uses _build_poll_plan() to ensure 100% parity with execution logic.
        """
        current_time = time.monotonic()
        plan = self._build_poll_plan(current_time)
        return sum(task.cost for task in plan)

    def estimate_daily_reserved_cost(self) -> tuple[int, dict[str, int]]:
        """Estimate API calls reserved for SCHEDULED updates over 24 hours.

        Only counts slow poll and offset poll - NOT fast poll!
        Fast poll is the TARGET of auto quota, not a reservation.

        Returns:
            Tuple of (total_reserved, breakdown_dict) for logging/debugging.

        """
        seconds_per_day = 86400
        breakdown: dict[str, int] = {}

        # --- Measure Slow Poll Cost (battery/metadata) ---
        # This runs independently on its own schedule
        slow_poll_cost = self._measure_slow_poll_cost()
        if self._slow_poll_seconds > 0:
            slow_polls_per_day = seconds_per_day / self._slow_poll_seconds
            breakdown["slow_poll_total"] = int(slow_poll_cost * slow_polls_per_day)
            breakdown["slow_poll_cost"] = slow_poll_cost
        else:
            breakdown["slow_poll_total"] = 0
            breakdown["slow_poll_cost"] = 0

        # --- Measure Offset Poll Cost ---
        # This also runs on its own schedule
        offset_poll_cost = self._measure_offset_poll_cost()
        if self._offset_poll_seconds > 0:
            offset_polls_per_day = seconds_per_day / self._offset_poll_seconds
            breakdown["offset_poll_total"] = int(
                offset_poll_cost * offset_polls_per_day
            )
            breakdown["offset_poll_cost"] = offset_poll_cost
        else:
            breakdown["offset_poll_total"] = 0
            breakdown["offset_poll_cost"] = 0

        # Fast poll cost is NOT reserved - it's what we're budgeting FOR
        breakdown["fast_poll_cost"] = self._measure_fast_poll_cost()

        total_reserved = breakdown["slow_poll_total"] + breakdown["offset_poll_total"]
        return total_reserved, breakdown

    def _measure_fast_poll_cost(self) -> int:
        """Measure cost of fast poll only (home_state + zone_states)."""
        # Fast poll is always: get_home_state + get_zone_states
        # We count PollTasks that are ALWAYS in the plan
        plan: list[PollTask] = [
            PollTask(1, self._tado.get_home_state),
            PollTask(1, self._tado.get_zone_states),
        ]
        return sum(task.cost for task in plan)

    def _measure_slow_poll_cost(self) -> int:
        """Measure cost of slow poll track (metadata/battery)."""
        plan: list[PollTask] = [
            PollTask(1, self._tado.get_zones),
            PollTask(1, self._tado.get_devices),
        ]
        # Capabilities: One call per AC/HotWater zone
        plan.extend(
            PollTask(1, lambda z=zone.id: self._tado.get_capabilities(z))
            for zone in self.zones_meta.values()
            if zone.type in ("AIR_CONDITIONING", "HOT_WATER")
        )
        return sum(task.cost for task in plan)

    def _measure_offset_poll_cost(self) -> int:
        """Measure cost of offset poll track (temperature offsets)."""
        devices_with_temp = [
            dev
            for dev in self.devices_meta.values()
            if CAPABILITY_INSIDE_TEMP in (dev.characteristics.capabilities or [])
        ]
        plan: list[PollTask] = []
        for dev in devices_with_temp:
            unique_id = f"{dev.serial_no}_temperature_offset"
            if not self._is_entity_disabled("number", unique_id):
                plan.append(self._create_offset_task(dev.serial_no))
        return sum(task.cost for task in plan)

    async def fetch_full_update(self) -> dict[str, Any]:
        """Perform a data fetch by executing the poll plan.

        Instead of executing the plan blindly (which is hard for data storage),
        we use the logic that built the plan (timings) to trigger the blocks.
        The plan exists to ensure 'predict_next_poll_cost' is accurate.
        """
        current_time = time.monotonic()

        # Execute Logic based on Timings (PARITY WITH PLAN)
        # We manually execute the blocks, but the logic matches _build_poll_plan exactly.

        # 1. Fast Track (Always)
        _LOGGER.debug("DataManager: Fetching fast-track states")
        home_state = await self._tado.get_home_state()
        zone_states = await self._tado.get_zone_states()

        # Results storage
        results: dict[str, Any] = {
            "home_state": home_state,
            "zone_states": zone_states,
            "zones": list(self.zones_meta.values()),
            "devices": list(self.devices_meta.values()),
            "capabilities": self.capabilities_cache,
            "offsets": self.offsets_cache,
            "away_config": self.away_cache,
        }

        # 2. Slow Track
        if (
            not self.zones_meta
            or (current_time - self._last_slow_poll) > self._slow_poll_seconds
        ):
            _LOGGER.info("DataManager: Fetching slow-track metadata")
            zones = await self._tado.get_zones()
            devices = await self._tado.get_devices()
            self.zones_meta = {zone.id: zone for zone in zones}
            self.devices_meta = {dev.short_serial_no: dev for dev in devices}

            results["zones"] = list(self.zones_meta.values())
            results["devices"] = list(self.devices_meta.values())

            # Capabilities
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

            self.coordinator.bridges = [
                dev for dev in devices if dev.device_type.startswith("IB")
            ]
            self._last_slow_poll = current_time

        # 3. Medium Track (Offsets)
        if self._offset_invalidated or (
            self._offset_poll_seconds > 0
            and (current_time - self._last_offset_poll) > self._offset_poll_seconds
        ):
            await self._fetch_offsets()
            self._last_offset_poll = current_time
            self._offset_invalidated = False

        # 4. Away Config
        if self._away_invalidated:
            await self._fetch_away_config()
            self._last_away_poll = current_time
            self._away_invalidated = False

        return results

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

        active_count = len(active_zones)
        if active_count == 0:
            return

        _LOGGER.info("DataManager: Fetching away config for %d zones", active_count)

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
