"""Manages data fetching and caching for Tado Hijack."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, cast

from tadoasync import Tado, TadoConnectionError
from tadoasync.models import Capabilities, TemperatureOffset

from .models_unified import UnifiedDataProvider, UnifiedTadoData

if TYPE_CHECKING:
    from ..coordinator import TadoDataUpdateCoordinator
    from .client import TadoHijackClient
    # Import specific mappers for type checking/special handling

from ..const import (
    CAPABILITY_INSIDE_TEMP,
    DEFAULT_PRESENCE_POLL_INTERVAL,
    GEN_X,
    SLOW_POLL_CYCLE_S,
)
from ..models import TadoData
from .logging_utils import get_redacted_logger

_LOGGER = get_redacted_logger(__name__)

# Tolerance for polling intervals to handle scheduler jitter (5% of interval, max 10s)
_JITTER_TOLERANCE_FACTOR = 0.05
_MAX_JITTER_TOLERANCE_S = 10.0


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
        provider: UnifiedDataProvider | None = None,
    ) -> None:
        """Initialize Tado data manager."""
        self.coordinator = coordinator
        self._tado = client
        self.provider = provider
        self._slow_poll_seconds = slow_poll_seconds
        self._offset_poll_seconds = offset_poll_seconds
        self._presence_poll_seconds = presence_poll_seconds

        self.zones_meta: dict[int, Any] = {}
        self.devices_meta: dict[str, Any] = {}
        self.capabilities_cache: dict[int, Any] = {}
        self.offsets_cache: dict[str, TemperatureOffset] = {}
        self.away_cache: dict[int, float] = {}
        self.timetable_cache: dict[int, dict[str, Any]] = {}
        self.schedule_blocks_cache: dict[int, dict[str, Any]] = {}
        self._capability_locks: dict[int, asyncio.Lock] = {}
        self._last_slow_poll: float = 0
        self._last_offset_poll: float = 0
        self._last_away_poll: float = 0
        self._last_timetable_poll: float = 0
        self._last_schedule_poll: float = 0
        self._last_presence_poll: float = 0
        self._last_zones_poll: float = 0
        self._last_capabilities_poll: float = 0
        self._offset_invalidated_at: float = 0
        self._capabilities_invalidated_at: float = 0
        self._capabilities_fetched_at: float = 0
        self._last_capabilities_refresh_count: int = 0
        self._away_invalidated_at: float = 0
        self._timetable_invalidated_at: float = 0
        self._schedule_invalidated_at: float = 0
        self._presence_invalidated_at: float = 0
        self._zones_invalidated_at: float = 0

        self._metadata_init = False
        self._zones_init = False
        self._presence_init = False

    @property
    def client(self) -> TadoHijackClient:
        """Return the client cast to TadoHijackClient."""
        return cast("TadoHijackClient", self._tado)

    def _should_run_task(self, elapsed: float, interval: float) -> bool:
        """Determine if a task should run, considering timing jitter.

        Long intervals (e.g. 1800s) are given more absolute tolerance than
        short ones, but we cap it to prevent overlapping high-frequency polls.
        """
        if interval <= 0:
            return False

        tolerance = min(interval * _JITTER_TOLERANCE_FACTOR, _MAX_JITTER_TOLERANCE_S)
        return elapsed >= (interval - tolerance)

    def _build_poll_plan(self, current_time: float) -> list[PollTask]:
        """Construct the execution plan for the current poll cycle."""
        plan: list[PollTask] = []
        self._add_fast_track_to_plan(plan, current_time)
        self._add_presence_track_to_plan(plan, current_time)
        self._add_slow_track_to_plan(plan, current_time)
        self._add_medium_track_to_plan(plan, current_time)
        self._add_away_track_to_plan(plan, current_time)
        self._add_timetable_track_to_plan(plan)
        self._add_schedule_track_to_plan(plan)
        self._add_capabilities_track_to_plan(plan)
        return plan

    def _add_fast_track_to_plan(self, plan: list[PollTask], now: float) -> None:
        """Add zone states polling (fast track)."""
        interval = (
            self.coordinator.update_interval.total_seconds()
            if self.coordinator.update_interval
            else 0
        )

        elapsed = now - self._last_zones_poll
        if not self._zones_init or (
            self._zones_invalidated_at > self._last_zones_poll
            or self._should_run_task(elapsed, interval)
        ):
            plan.append(PollTask(1, self._fetch_zones))
        else:
            _LOGGER.debug(
                "DataManager: Skipping fast track (elapsed: %.1fs, interval: %.1fs)",
                elapsed,
                interval,
            )

    def _add_presence_track_to_plan(self, plan: list[PollTask], now: float) -> None:
        """Add presence/home state polling."""
        elapsed = now - self._last_presence_poll
        interval = float(self._presence_poll_seconds)
        if not self._presence_init or (
            self._presence_invalidated_at > self._last_presence_poll
            or self._should_run_task(elapsed, interval)
        ):
            plan.append(PollTask(1, self._fetch_presence))
        else:
            _LOGGER.debug(
                "DataManager: Skipping presence track (elapsed: %.1fs, interval: %.1fs)",
                elapsed,
                interval,
            )

    def _add_slow_track_to_plan(self, plan: list[PollTask], now: float) -> None:
        """Add metadata polling (slow track)."""
        elapsed = now - self._last_slow_poll
        interval = float(self._slow_poll_seconds)

        if not self._metadata_init or self._should_run_task(elapsed, interval):
            plan.append(PollTask(1, self._fetch_metadata))

    def _add_medium_track_to_plan(self, plan: list[PollTask], now: float) -> None:
        if self.coordinator.generation == GEN_X:
            return

        # Skip during initial poll if fetch_extended_data is disabled
        from ..const import CONF_INITIAL_POLL_DONE

        is_initial_poll = not self.coordinator.config_entry.data.get(
            CONF_INITIAL_POLL_DONE, False
        )
        if is_initial_poll and not self.coordinator.fetch_extended_data:
            return

        elapsed = now - self._last_offset_poll
        interval = float(self._offset_poll_seconds)

        if (self._offset_invalidated_at > self._last_offset_poll) or (
            self._should_run_task(elapsed, interval)
        ):
            plan.append(PollTask(1, self._fetch_offsets))

    def _add_away_track_to_plan(self, plan: list[PollTask], now: float) -> None:
        # Tado X: away config not supported via API
        if self.coordinator.generation == GEN_X:
            return

        # Skip during initial poll if fetch_extended_data is disabled
        from ..const import CONF_INITIAL_POLL_DONE

        is_initial_poll = not self.coordinator.config_entry.data.get(
            CONF_INITIAL_POLL_DONE, False
        )
        if is_initial_poll and not self.coordinator.fetch_extended_data:
            return

        if self._away_invalidated_at > self._last_away_poll:
            plan.append(PollTask(1, self._fetch_away_config))

    def _add_timetable_track_to_plan(self, plan: list[PollTask]) -> None:
        """Fetch active timetable types only when a full/timetable poll invalidates."""
        if self._timetable_invalidated_at > self._last_timetable_poll:
            plan.append(PollTask(1, self._fetch_timetables))

    def _add_capabilities_track_to_plan(self, plan: list[PollTask]) -> None:
        """Refetch caps on button/full poll, or with hardware sync when due."""
        if self.coordinator.generation == GEN_X:
            return
        invalidated = self._capabilities_invalidated_at > self._last_capabilities_poll
        slow_running = any(task.coroutine == self._fetch_metadata for task in plan)
        if invalidated or (slow_running and self._capabilities_due()):
            plan.append(PollTask(1, self._refresh_capabilities))

    def _capabilities_due(self) -> bool:
        """True when capabilities should follow the hardware-sync interval."""
        interval = float(self._slow_poll_seconds)
        if interval <= 0:
            return self._capabilities_fetched_at <= 0
        if self._capabilities_fetched_at <= 0:
            return True
        return (time.time() - self._capabilities_fetched_at) >= interval

    def _capability_zone_ids(self) -> list[int]:
        """Classic zones that have a capabilities endpoint (skip dummies)."""
        dummy = self.coordinator.dummy_handler
        return [
            int(zone.id)
            for zone in self.zones_meta.values()
            if not (dummy and dummy.is_dummy_zone(zone.id))
        ]

    def _add_schedule_track_to_plan(self, plan: list[PollTask]) -> None:
        """Fetch weekly plans only when a full/schedule poll invalidates."""
        if self._schedule_invalidated_at > self._last_schedule_poll:
            plan.append(PollTask(1, self._fetch_zone_plans))

    def _measure_presence_poll_cost(self) -> int:
        """Measure cost of home_state poll."""
        return 1

    def _measure_zones_poll_cost(self) -> int:
        """Measure cost of zone_states poll."""
        return 1

    def _count_special_zones_tadox(self) -> int:
        """Count Tado X zones with special polling needs (none)."""
        return 0

    def estimate_daily_reserved_cost(self) -> tuple[int, dict[str, int]]:
        """Estimate API calls reserved for scheduled updates."""
        sec_day = SLOW_POLL_CYCLE_S
        p_cost = 1

        if self.coordinator.generation == GEN_X:
            s_cost = 2 + self._count_special_zones_tadox()
            cap_cost = 0
        else:
            s_cost = 2
            cap_cost = len(self._capability_zone_ids())
        o_cost = sum(
            CAPABILITY_INSIDE_TEMP in (d.characteristics.capabilities or [])
            and not self._is_entity_disabled(
                "number", f"{d.serial_no}_temperature_offset"
            )
            for d in self.devices_meta.values()
        )

        from .offset_calibrate import daily_offset_cal_puts

        slow_s = float(self._slow_poll_seconds)
        breakdown = {
            "presence_poll_total": int(p_cost * (sec_day / self._presence_poll_seconds))
            if self._presence_poll_seconds > 0
            else 0,
            "slow_poll_total": int(s_cost * (sec_day / slow_s)) if slow_s > 0 else 0,
            "capabilities_total": int(cap_cost * (sec_day / slow_s))
            if slow_s > 0
            else 0,
            "offset_poll_total": int(o_cost * (sec_day / self._offset_poll_seconds))
            if self._offset_poll_seconds > 0
            else 0,
            "offset_cal_total": daily_offset_cal_puts(self.coordinator),
            "zones_poll_cost": 1,
        }
        total = (
            breakdown["presence_poll_total"]
            + breakdown["slow_poll_total"]
            + breakdown["capabilities_total"]
            + breakdown["offset_poll_total"]
            + breakdown["offset_cal_total"]
        )
        return total, breakdown

    async def fetch_full_update(self) -> TadoData | UnifiedTadoData:
        """Execute a data fetch based on the built plan."""
        now = time.monotonic()
        plan = self._build_poll_plan(now)

        is_init = self.coordinator.data is None
        home_state = getattr(self.coordinator.data, "home_state", None)
        zone_states = getattr(self.coordinator.data, "zone_states", {})

        for task in plan:
            if task.coroutine == self._fetch_zones:
                zone_states = await task.coroutine(now)
            elif task.coroutine == self._fetch_presence:
                home_state = await task.coroutine(now)
            elif task.coroutine == self._fetch_metadata:
                await task.coroutine(now)
            elif task.coroutine == self._fetch_away_config:
                await task.coroutine()
                self._last_away_poll = now
            elif task.coroutine == self._fetch_offsets:
                await task.coroutine()
                self._last_offset_poll = now
            elif task.coroutine == self._fetch_timetables:
                await task.coroutine()
                self._last_timetable_poll = now
            elif task.coroutine == self._fetch_zone_plans:
                await task.coroutine()
                self._last_schedule_poll = now
            elif task.coroutine == self._refresh_capabilities:
                await task.coroutine()
                self._last_capabilities_poll = now

        if self.coordinator.generation != GEN_X:
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
        from .models_unified import UnifiedTadoData

        presence = (
            home_state.presence
            if home_state and hasattr(home_state, "presence")
            else "HOME"
        )
        return UnifiedTadoData(
            home_state=type("HomeState", (), {"presence": presence}),
            api_status="online",
            zones=self.zones_meta,
            zone_states=(
                zone_states
                if is_init
                else getattr(self.coordinator.data, "zone_states", zone_states)
            ),
            devices=self.devices_meta,
            capabilities=self.capabilities_cache,
            limit=0,
            remaining=0,
            generation=GEN_X,
        )

    async def _fetch_presence(self, now: float) -> Any:
        """Fetch presence state."""
        if not self.provider:
            return None

        state = await self.provider.async_fetch_home_state()
        self._last_presence_poll = now
        self._presence_init = True
        if self.coordinator.data and state is not None:
            from .api_manager import TadoApiManager

            pending_keys = self.coordinator.api_manager.pending_keys
            if "presence" not in pending_keys:
                self.coordinator.data.home_state = state
            elif existing_state := self.coordinator.data.home_state:
                protected = TadoApiManager.get_protected_fields_for_key("presence")
                for field in vars(state):
                    if field not in protected and not field.startswith("_"):
                        setattr(existing_state, field, getattr(state, field))
            else:
                self.coordinator.data.home_state = state
        return state

    def _merge_zone_states(self, states: dict[str, Any]) -> None:
        """Merge new zone states into coordinator data with pending-command protection."""
        if not (
            self.coordinator.data and hasattr(self.coordinator.data, "zone_states")
        ):
            return

        from .api_manager import TadoApiManager

        pending_keys = self.coordinator.api_manager.pending_keys
        for zone_id, new_state in states.items():
            zone_key = f"zone_{zone_id}"
            if zone_key not in pending_keys:
                self.coordinator.data.zone_states[zone_id] = new_state
            elif existing_state := self.coordinator.data.zone_states.get(zone_id):
                protected = TadoApiManager.get_protected_fields_for_key(zone_key)
                for field in vars(new_state):
                    if field not in protected and not field.startswith("_"):
                        setattr(existing_state, field, getattr(new_state, field))
            else:
                self.coordinator.data.zone_states[zone_id] = new_state

    async def _fetch_zones(self, now: float) -> dict[str, Any]:
        """Fetch zone states (Unified)."""
        if not self.provider:
            return {}

        states = await self.provider.async_fetch_zones()

        # [DUMMY_HOOK]
        if h := self.coordinator.dummy_handler:
            h.inject_states(states)

        self._last_zones_poll = now
        self._zones_init = True
        self._merge_zone_states(states)
        return states

    async def _fetch_metadata(self, now: float) -> None:
        """Fetch metadata (Unified)."""
        if not self.provider:
            return

        zones, devices = await self.provider.async_fetch_metadata()

        # Sync with optimistic manager to prevent UI jumps (Open Window)
        for zid, z in zones.items():
            self._sync_optimistic_owd(zid, z)

        self.zones_meta = zones
        self.devices_meta = devices

        # [DUMMY_HOOK]
        if h := self.coordinator.dummy_handler:
            h.inject_metadata(
                self.zones_meta, self.devices_meta, self.capabilities_cache
            )

        self._metadata_init = True

        # Update bridges for discovery
        from .discovery import get_bridges

        self.coordinator.bridges = get_bridges(
            self.devices_meta, self.coordinator.generation
        )

        self._last_slow_poll = now

    def _sync_optimistic_owd(self, zid: int, new_zone: Any) -> None:
        """Sync OWD state from optimistic manager."""
        opt_timeout = self.coordinator.optimistic.get_open_window(zid)
        if (
            opt_timeout is not None
            and hasattr(new_zone, "open_window_detection")
            and new_zone.open_window_detection
        ):
            new_zone.open_window_detection.enabled = opt_timeout > 0
            new_zone.open_window_detection.timeout_in_seconds = opt_timeout

    async def _fetch_capabilities(self, zone_id: int, *, persist: bool = True) -> None:
        """Fetch and cache capabilities for a zone."""
        if not self.provider:
            return

        try:
            caps = await self.provider.async_fetch_capabilities(zone_id)
            if caps:
                self.capabilities_cache[zone_id] = caps
                if persist:
                    self.coordinator._save_capabilities_cache()
        except Exception as e:
            _LOGGER.warning(
                "Capabilities unavailable for zone %d (%s) — skipping",
                zone_id,
                type(e).__name__,
            )
            self.capabilities_cache[zone_id] = None  # Cache failure, no retry

    async def _refresh_capabilities(self) -> None:
        """GET capabilities for every classic zone (no bulk endpoint)."""
        zone_ids = self._capability_zone_ids()
        if not zone_ids:
            return
        _LOGGER.info(
            "DataManager: Refreshing capabilities for %d zone(s)", len(zone_ids)
        )
        self._last_capabilities_refresh_count = 0
        for zone_id in zone_ids:
            self.capabilities_cache.pop(zone_id, None)
            await self._fetch_capabilities(zone_id, persist=False)
            self._last_capabilities_refresh_count += 1
        self._capabilities_fetched_at = time.time()
        self.coordinator._save_capabilities_cache()

    def take_capabilities_refresh_count(self) -> int:
        """Return GETs from the last capabilities refresh and clear the counter."""
        count = self._last_capabilities_refresh_count
        self._last_capabilities_refresh_count = 0
        return count

    async def async_get_capabilities(self, zone_id: int) -> Any:
        """Get capabilities (thread-safe, cached)."""
        # [TADO_X] Capabilities not supported via API
        if self.coordinator.generation == GEN_X:
            return None

        if zone_id not in self.capabilities_cache:
            if zone_id not in self._capability_locks:
                self._capability_locks[zone_id] = asyncio.Lock()
            async with self._capability_locks[zone_id]:
                if zone_id in self.capabilities_cache:
                    return self.capabilities_cache[zone_id]

                await self._fetch_capabilities(zone_id)

        return self.capabilities_cache.get(zone_id)

    def export_capabilities_cache(self) -> dict[str, Any]:
        """JSON-safe capabilities for storage (skip dummies and failed lookups)."""
        dumped: dict[str, Any] = {}
        dummy = self.coordinator.dummy_handler
        for zone_id, caps in self.capabilities_cache.items():
            if caps is None:
                continue
            if dummy and dummy.is_dummy_zone(zone_id):
                continue
            to_dict = getattr(caps, "to_dict", None)
            if not callable(to_dict):
                continue
            dumped[str(zone_id)] = to_dict()
        return {
            "fetched_at": self._capabilities_fetched_at,
            "zones": dumped,
        }

    def restore_capabilities_cache(self, raw: dict[str, Any]) -> int:
        """Load persisted capabilities. Returns how many zones were restored."""
        fetched = raw.get("fetched_at")
        zones = raw.get("zones")
        if isinstance(zones, dict):
            if isinstance(fetched, int | float) and fetched > 0:
                self._capabilities_fetched_at = float(fetched)
            raw = zones
        count = 0
        for key, payload in raw.items():
            if not isinstance(payload, dict):
                continue
            try:
                self.capabilities_cache[int(key)] = Capabilities.from_dict(payload)
            except TypeError, ValueError, KeyError, AttributeError:
                _LOGGER.debug("Skipping stored capabilities for zone %s", key)
                continue
            count += 1
        return count

    def invalidate_cache(self, refresh_type: str = "all") -> None:
        """Force specific cache refresh."""
        now = time.monotonic()
        if refresh_type in {"all", "metadata"}:
            self._metadata_init = False
        if refresh_type in {"all", "offsets"}:
            self._offset_invalidated_at = now
        if refresh_type in {"all", "away"}:
            self._away_invalidated_at = now
        if refresh_type in {"all", "timetable"}:
            self._timetable_invalidated_at = now
        if refresh_type in {"all", "schedule"}:
            self._schedule_invalidated_at = now
        if refresh_type in {"all", "capabilities"}:
            self._capabilities_invalidated_at = now
        if refresh_type in {"all", "presence"}:
            self._presence_invalidated_at = now
            self._presence_init = False
        if refresh_type in {"all", "zone"}:
            self._zones_invalidated_at = now
            self._zones_init = False

    def _is_entity_disabled(self, platform: str, unique_id: str) -> bool:
        """Check if an entity is disabled."""
        from .entity_registry_utils import is_entity_disabled

        return is_entity_disabled(self.coordinator.hass, platform, unique_id)

    async def _fetch_offsets(self) -> None:
        """Fetch temperature offsets (V3 only)."""
        if not self.provider or self.coordinator.generation == GEN_X:
            return

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
            await self._fetch_offset_for(d.serial_no)

    async def _fetch_offset_for(self, serial: str) -> None:
        """Fetch temperature offset for a single device (V3 only)."""
        if not self.provider or self.coordinator.generation == GEN_X:
            return

        opt_val = self.coordinator.optimistic.get_offset(serial)
        if opt_val is not None:
            from tadoasync.models import TemperatureOffset

            self.offsets_cache[serial] = TemperatureOffset(
                celsius=float(opt_val), fahrenheit=0.0
            )
            _LOGGER.debug("Synced offset from optimistic for %s", serial)
            return

        from .tadov3.mapper import TadoV3Mapper

        mapper = cast(TadoV3Mapper, self.provider)
        try:
            off = await mapper.async_fetch_device_offset(serial)
            self.offsets_cache[serial] = off
        except TadoConnectionError as e:
            _LOGGER.warning("Offset fail for %s: %s", serial, e)
        except ValueError as e:
            _LOGGER.warning("Offset parse fail for %s: %s", serial, e)

    async def _fetch_away_config(self) -> None:
        """Fetch away configuration (V3 only)."""
        if not self.provider or self.coordinator.generation == GEN_X:
            return

        from ..const import ZONE_TYPE_HEATING
        from .zone_utils import get_zone_type

        active = [
            z
            for z in self.zones_meta.values()
            if get_zone_type(z, "") == ZONE_TYPE_HEATING
            and not self._is_entity_disabled("number", f"zone_{z.id}_away_temperature")
        ]
        if not active:
            return

        _LOGGER.info("DataManager: Fetching away config for %d zones", len(active))

        for z in active:
            await self._fetch_away_config_for(z.id)

    async def _fetch_timetables(self) -> None:
        """Fetch active timetable types for every compatible zone."""
        from .timetable import compatible_zone_ids

        zone_ids = compatible_zone_ids(self.coordinator)
        if not zone_ids:
            return

        _LOGGER.info(
            "DataManager: Fetching timetables for %d zone(s)",
            len(zone_ids),
        )
        await self.coordinator._execute_timetable_refreshes(zone_ids, notify=False)

    async def _fetch_zone_plans(self) -> None:
        """Fetch weekly heating plans for every capable zone."""
        from .schedule import schedule_capable_zone_ids

        zone_ids = schedule_capable_zone_ids(self.coordinator)
        if not zone_ids:
            return

        _LOGGER.info(
            "DataManager: Fetching weekly plans for %d zone(s)",
            len(zone_ids),
        )
        await self.coordinator._execute_zone_plan_refreshes(zone_ids, notify=False)

    async def _fetch_away_config_for(self, zone_id: int) -> None:
        """Fetch away configuration for a single zone (V3 only)."""
        if not self.provider or self.coordinator.generation == GEN_X:
            return

        # Don't overwrite cache while a SET_AWAY_TEMP command is pending —
        # the API GET may race with the pending POST and return a stale value.

        if f"set_away_temp_{zone_id}" in self.coordinator.api_manager.pending_keys:
            return

        opt_val = self.coordinator.optimistic.get_away_temp(zone_id)
        if opt_val is not None:
            self.away_cache[zone_id] = float(opt_val)
            return

        try:
            val = await self.provider.async_fetch_away_config(zone_id)
            if val is not None:
                self.away_cache[zone_id] = val
        except Exception as e:
            _LOGGER.warning("Away config fail for zone %d: %s", zone_id, e)

    async def async_targeted_fetch(self, refresh_type: str, entity_id: str) -> bool:
        """Fetch data for a specific entity without a full coordinator refresh.

        Returns True if the fetch was targeted (no full refresh needed),
        False if it fell back to cache invalidation (caller must trigger async_refresh).
        """
        if refresh_type == "offsets":
            if serial := self.coordinator.entity_resolver.get_serial_from_entity(
                entity_id
            ):
                await self._fetch_offset_for(serial)
                return True
            _LOGGER.warning(
                "Targeted offset fetch: could not resolve serial for %s, falling back",
                entity_id,
            )
            self.invalidate_cache("offsets")
            return False

        if refresh_type == "away":
            zone_id = self.coordinator.get_zone_id_from_entity(entity_id)
            if zone_id is not None:
                await self._fetch_away_config_for(zone_id)
                return True
            _LOGGER.warning(
                "Targeted away fetch: could not resolve zone for %s, falling back",
                entity_id,
            )
            self.invalidate_cache("away")
            return False

        if refresh_type == "capabilities":
            zone_id = self.coordinator.get_zone_id_from_entity(entity_id)
            if zone_id is not None:
                self.capabilities_cache.pop(zone_id, None)
                await self.async_get_capabilities(zone_id)
                return True
            _LOGGER.warning(
                "Targeted capabilities fetch: could not resolve zone for %s, falling back",
                entity_id,
            )
            self.capabilities_cache.clear()
            return False

        if refresh_type == "timetable":
            zone_id = self.coordinator.get_zone_id_from_entity(entity_id)
            if zone_id is not None:
                await self.coordinator._execute_timetable_refresh(zone_id)
                return True
            _LOGGER.warning(
                "Targeted timetable fetch: could not resolve zone for %s, falling back",
                entity_id,
            )
            self.invalidate_cache("timetable")
            return False

        if refresh_type == "schedule":
            zone_id = self.coordinator.get_zone_id_from_entity(entity_id)
            if zone_id is not None:
                await self.coordinator._fetch_zone_plan(zone_id)
                self.coordinator.async_update_listeners()
                return True
            _LOGGER.warning(
                "Targeted schedule fetch: could not resolve zone for %s, falling back",
                entity_id,
            )
            self.invalidate_cache("schedule")
            return False

        # Bulk-only types (zone, metadata, presence, all): invalidate and signal full refresh
        self.invalidate_cache(refresh_type)
        return False
