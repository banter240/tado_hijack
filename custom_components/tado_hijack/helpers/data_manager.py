"""Manages data fetching and caching for Tado Hijack."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, cast

from homeassistant.helpers import entity_registry as er
from tadoasync import Tado, TadoConnectionError
from tadoasync.models import TemperatureOffset

if TYPE_CHECKING:
    from ..coordinator import TadoDataUpdateCoordinator
    from .client import TadoHijackClient

from ..const import (
    CAPABILITY_INSIDE_TEMP,
    DEFAULT_PRESENCE_POLL_INTERVAL,
    DOMAIN,
    SLOW_POLL_CYCLE_S,
    TEMP_OFFSET_ATTR,
)
from ..models import TadoData
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
        presence_poll_seconds: int = DEFAULT_PRESENCE_POLL_INTERVAL,
    ) -> None:
        """Initialize Tado data manager."""
        self.coordinator = coordinator
        self._tado = client
        self._slow_poll_seconds = slow_poll_seconds
        self._offset_poll_seconds = offset_poll_seconds
        self._presence_poll_seconds = presence_poll_seconds

        # Caches
        self.zones_meta: dict[int, Any] = {}
        self.devices_meta: dict[str, Any] = {}
        self.capabilities_cache: dict[int, Any] = {}
        self.offsets_cache: dict[str, TemperatureOffset] = {}
        self.away_cache: dict[int, float] = {}
        self._capability_locks: dict[int, asyncio.Lock] = {}
        self._last_slow_poll: float = 0
        self._last_offset_poll: float = 0
        self._last_away_poll: float = 0
        self._last_presence_poll: float = 0
        self._last_zones_poll: float = 0
        self._offset_invalidated_at: float = 0
        self._away_invalidated_at: float = 0
        self._presence_invalidated_at: float = 0
        self._zones_invalidated_at: float = 0

        # Initialization flags for independent bootstrapping
        self._metadata_init = False
        self._zones_init = False
        self._presence_init = False

    @property
    def client(self) -> TadoHijackClient:
        """Return the client cast to TadoHijackClient."""
        return cast("TadoHijackClient", self._tado)

    def _build_poll_plan(self, current_time: float) -> list[PollTask]:
        """Construct the execution plan for the current poll cycle."""
        plan: list[PollTask] = []
        self._add_fast_track_to_plan(plan, current_time)
        self._add_presence_track_to_plan(plan, current_time)
        self._add_slow_track_to_plan(plan, current_time)
        self._add_medium_track_to_plan(plan, current_time)
        self._add_away_track_to_plan(plan, current_time)
        return plan

    def _add_fast_track_to_plan(self, plan: list[PollTask], now: float) -> None:
        interval = (
            self.coordinator.update_interval.total_seconds()
            if self.coordinator.update_interval
            else 0
        )
        if not self._zones_init or (
            self._zones_invalidated_at > self._last_zones_poll
            or (interval > 0 and (now - self._last_zones_poll) >= (interval - 1))
        ):
            plan.append(PollTask(1, self._tado.get_zone_states))

    def _add_presence_track_to_plan(self, plan: list[PollTask], now: float) -> None:
        if not self._presence_init or (
            self._presence_invalidated_at > self._last_presence_poll
            or (
                self._presence_poll_seconds > 0
                and (now - self._last_presence_poll)
                >= (self._presence_poll_seconds - 1)
            )
        ):
            plan.append(PollTask(1, self._tado.get_home_state))

    def _add_slow_track_to_plan(self, plan: list[PollTask], now: float) -> None:
        if (
            not self._metadata_init
            or (now - self._last_slow_poll) > self._slow_poll_seconds
        ):
            plan.append(PollTask(1, self._tado.get_zones))

    def _add_medium_track_to_plan(self, plan: list[PollTask], now: float) -> None:
        if (self._offset_invalidated_at > self._last_offset_poll) or (
            self._offset_poll_seconds > 0
            and (now - self._last_offset_poll) > self._offset_poll_seconds
        ):
            plan.append(PollTask(1, self._fetch_offsets))

    def _add_away_track_to_plan(self, plan: list[PollTask], now: float) -> None:
        if self._away_invalidated_at > self._last_away_poll:
            plan.append(PollTask(1, self._fetch_away_config))

    def _measure_presence_poll_cost(self) -> int:
        """Measure cost of home_state poll."""
        return 1

    def _measure_zones_poll_cost(self) -> int:
        """Measure cost of zone_states poll."""
        return 1

    def estimate_daily_reserved_cost(self) -> tuple[int, dict[str, int]]:
        """Estimate API calls reserved for scheduled updates."""
        sec_day = SLOW_POLL_CYCLE_S
        p_cost = 1
        s_cost = 2 + sum(
            z.type in ("AIR_CONDITIONING", "HOT_WATER")
            for z in self.zones_meta.values()
        )
        o_cost = sum(
            CAPABILITY_INSIDE_TEMP in (d.characteristics.capabilities or [])
            and not self._is_entity_disabled(
                "number", f"{d.serial_no}_temperature_offset"
            )
            for d in self.devices_meta.values()
        )

        breakdown = {
            "presence_poll_total": int(p_cost * (sec_day / self._presence_poll_seconds))
            if self._presence_poll_seconds > 0
            else 0,
            "slow_poll_total": int(s_cost * (sec_day / self._slow_poll_seconds))
            if self._slow_poll_seconds > 0
            else 0,
            "offset_poll_total": int(o_cost * (sec_day / self._offset_poll_seconds))
            if self._offset_poll_seconds > 0
            else 0,
            "zones_poll_cost": 1,
        }
        total = (
            breakdown["presence_poll_total"]
            + breakdown["slow_poll_total"]
            + breakdown["offset_poll_total"]
        )
        return total, breakdown

    async def fetch_full_update(self) -> TadoData:
        """Execute a data fetch based on the built plan."""
        now = time.monotonic()
        plan = self._build_poll_plan(now)

        # Local storage for results to handle the cold-start (init) phase
        is_init = self.coordinator.data is None
        home_state = getattr(self.coordinator.data, "home_state", None)
        zone_states = getattr(self.coordinator.data, "zone_states", {})

        for task in plan:
            if task.coroutine == self._tado.get_home_state:
                home_state = await self._fetch_presence(now)
            elif task.coroutine == self._tado.get_zone_states:
                zone_states = await self._fetch_zones(now)
            elif task.coroutine == self._tado.get_zones:
                await self._fetch_metadata(now)
            elif task.coroutine == self._fetch_away_config:
                await self._fetch_away_config()
                self._last_away_poll = now
            elif task.coroutine == self._fetch_offsets:
                await self._fetch_offsets()
                self._last_offset_poll = now

        # Use freshly fetched data if we are in init phase, otherwise rely on coordinator sync
        return TadoData(
            home_state=home_state
            if is_init
            else getattr(self.coordinator.data, "home_state", home_state),
            zone_states=zone_states
            if is_init
            else getattr(self.coordinator.data, "zone_states", zone_states),
            zones=self.zones_meta,
            devices=self.devices_meta,
            capabilities=self.capabilities_cache,
            offsets=self.offsets_cache,
            away_config=self.away_cache,
        )

    async def _fetch_presence(self, now: float) -> Any:
        state = await self._tado.get_home_state()
        self._last_presence_poll = now
        self._presence_init = True
        if self.coordinator.data:
            # Selective merge for presence
            from .api_manager import TadoApiManager

            pending_keys = self.coordinator.api_manager.pending_keys
            if "presence" not in pending_keys:
                # No pending command - full update
                self.coordinator.data.home_state = state
            else:
                if existing_state := self.coordinator.data.home_state:
                    # Get protected fields for presence command
                    protected = TadoApiManager.get_protected_fields_for_key("presence")

                    # Update all fields EXCEPT protected ones
                    for field in vars(state):
                        if field not in protected and not field.startswith("_"):
                            setattr(existing_state, field, getattr(state, field))
                else:
                    # No existing state - use new state fully
                    self.coordinator.data.home_state = state
        return state

    async def _fetch_zones(self, now: float) -> dict:
        states = await self._tado.get_zone_states()

        # [DUMMY_HOOK]
        if h := self.coordinator.dummy_handler:
            h.inject_states(states)

        self._last_zones_poll = now
        self._zones_init = True
        if self.coordinator.data:
            # Selective merge: protect specific fields based on command type
            from .api_manager import TadoApiManager

            pending_keys = self.coordinator.api_manager.pending_keys
            for zone_id, new_state in states.items():
                zone_key = f"zone_{zone_id}"
                if zone_key not in pending_keys:
                    # No pending command - full update
                    self.coordinator.data.zone_states[zone_id] = new_state
                else:
                    if existing_state := self.coordinator.data.zone_states.get(zone_id):
                        # Get which fields are protected for this command
                        protected = TadoApiManager.get_protected_fields_for_key(
                            zone_key
                        )

                        # Update all fields EXCEPT protected ones
                        for field in vars(new_state):
                            if field not in protected and not field.startswith("_"):
                                setattr(
                                    existing_state, field, getattr(new_state, field)
                                )
                    else:
                        # No existing state - use new state fully
                        self.coordinator.data.zone_states[zone_id] = new_state
        return states

    async def _fetch_metadata(self, now: float) -> None:
        zones = await self._tado.get_zones()
        devices = await self._tado.get_devices()
        self.zones_meta = {z.id: z for z in zones}
        self.devices_meta = {d.short_serial_no: d for d in devices}

        # [DUMMY_HOOK]
        if h := self.coordinator.dummy_handler:
            h.inject_metadata(
                self.zones_meta, self.devices_meta, self.capabilities_cache
            )

        # Lazy refresh: Update capabilities for relevant zones if missing
        for z in zones:
            if (
                z.type in ("AIR_CONDITIONING", "HOT_WATER")
                and z.id not in self.capabilities_cache
            ):
                await self._fetch_capabilities(z.id)

        self._metadata_init = True
        self.coordinator.bridges = [
            d for d in devices if d.device_type.startswith("IB")
        ]
        self._last_slow_poll = now

    async def _fetch_capabilities(self, zone_id: int) -> None:
        """Fetch and cache capabilities for a zone."""
        try:
            self.capabilities_cache[zone_id] = await self._tado.get_capabilities(
                zone_id
            )
        except Exception as e:
            _LOGGER.warning("Capabilities fail for zone %d: %s", zone_id, e)

    def invalidate_cache(self, refresh_type: str = "all") -> None:
        """Force specific cache refresh."""
        now = time.monotonic()
        if refresh_type in {"all", "metadata"}:
            self._metadata_init = False
        if refresh_type in {"all", "offsets"}:
            self._offset_invalidated_at = now
        if refresh_type in {"all", "away"}:
            self._away_invalidated_at = now
        if refresh_type in {"all", "presence"}:
            self._presence_invalidated_at = now
            self._presence_init = False
        if refresh_type in {"all", "zone"}:
            self._zones_invalidated_at = now
            self._zones_init = False

    def _is_entity_disabled(self, platform: str, unique_id: str) -> bool:
        """Check if an entity is disabled."""
        reg = er.async_get(self.coordinator.hass)
        if eid := reg.async_get_entity_id(platform, DOMAIN, unique_id):
            entry = reg.async_get(eid)
            return bool(entry and entry.disabled)
        return False

    async def _fetch_offsets(self) -> None:
        """Fetch temperature offsets."""
        active = [
            d
            for d in self.devices_meta.values()
            if CAPABILITY_INSIDE_TEMP in (d.characteristics.capabilities or [])
            and not self._is_entity_disabled(
                "number", f"{d.serial_no}_temperature_offset"
            )
        ]
        if not active:
            return
        _LOGGER.info("DataManager: Fetching offsets for %d devices", len(active))
        for d in active:
            try:
                off = await self.coordinator.client.get_device_info(
                    d.serial_no, TEMP_OFFSET_ATTR
                )
                if isinstance(off, TemperatureOffset):
                    self.offsets_cache[d.serial_no] = off
            except TadoConnectionError as e:
                _LOGGER.warning("Offset fail for %s: %s", d.short_serial_no, e)

    async def _fetch_away_config(self) -> None:
        """Fetch away configuration."""
        active = [
            z
            for z in self.zones_meta.values()
            if getattr(z, "type", "") == "HEATING"
            and not self._is_entity_disabled("number", f"zone_{z.id}_away_temperature")
        ]
        if not active:
            return
        _LOGGER.info("DataManager: Fetching away config for %d zones", len(active))
        for z in active:
            try:
                # [DUMMY_HOOK]
                h = self.coordinator.dummy_handler
                if h and h.is_dummy_zone(z.id):
                    cfg = h.get_away_configuration(z.id)
                else:
                    cfg = await self.coordinator.client.get_away_configuration(z.id)

                if (
                    "minimumAwayTemperature" in cfg
                    and (t := cfg["minimumAwayTemperature"].get("celsius")) is not None
                ):
                    self.away_cache[z.id] = float(t)
            except Exception as e:
                _LOGGER.warning("Away config fail for zone %d: %s", z.id, e)

    async def async_get_capabilities(self, zone_id: int) -> Any:
        """Get capabilities (thread-safe)."""
        if zone_id not in self.capabilities_cache:
            if zone_id not in self._capability_locks:
                self._capability_locks[zone_id] = asyncio.Lock()
            async with self._capability_locks[zone_id]:
                if zone_id in self.capabilities_cache:
                    return self.capabilities_cache[zone_id]
                _LOGGER.info("DataManager: Fetching capabilities for zone %d", zone_id)
                try:
                    # [DUMMY_HOOK]
                    h = self.coordinator.dummy_handler
                    if h and h.is_dummy_zone(zone_id):
                        caps = h.get_capabilities(zone_id)
                    else:
                        caps = await self._tado.get_capabilities(zone_id)

                    if caps:
                        self.capabilities_cache[zone_id] = caps
                except Exception as e:
                    _LOGGER.error("Capabilities fail for zone %d: %s", zone_id, e)
                    return None
        return self.capabilities_cache.get(zone_id)
