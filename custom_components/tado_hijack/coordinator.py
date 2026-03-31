"""Data Update Coordinator for Tado Hijack."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

import aiohttp
from homeassistant.core import (
    HomeAssistant,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from tadoasync import Tado, TadoError

if TYPE_CHECKING:
    from tadoasync.models import Device, Zone

    from . import TadoConfigEntry
    from .helpers.client import TadoHijackClient
    from .lib.tadox_models import HopsRoomSnapshot

from .const import (
    CONF_API_PROXY_URL,
    CONF_AUTO_API_QUOTA_PERCENT,
    CONF_DEBOUNCE_TIME,
    CONF_DISABLE_POLLING_WHEN_THROTTLED,
    CONF_ENABLE_DUMMY_ZONES,  # [DUMMY_HOOK]
    CONF_FETCH_EXTENDED_DATA,
    CONF_FULL_CLOUD_MODE,
    CONF_GENERATION,
    CONF_JITTER_PERCENT,
    CONF_MIN_AUTO_QUOTA_INTERVAL_S,
    CONF_OFFSET_POLL_INTERVAL,
    CONF_PRESENCE_POLL_INTERVAL,
    CONF_QUOTA_SAFETY_RESERVE,
    CONF_REDUCED_POLLING_ACTIVE,
    CONF_REDUCED_POLLING_END,
    CONF_REDUCED_POLLING_INTERVAL,
    CONF_REDUCED_POLLING_START,
    CONF_REFRESH_AFTER_RESUME,
    CONF_SLOW_POLL_INTERVAL,
    CONF_SUPPRESS_REDUNDANT_BUTTONS,
    CONF_SUPPRESS_REDUNDANT_CALLS,
    CONF_THROTTLE_THRESHOLD,
    DEFAULT_AUTO_API_QUOTA_PERCENT,
    DEFAULT_DEBOUNCE_TIME,
    DEFAULT_JITTER_PERCENT,
    DEFAULT_MIN_AUTO_QUOTA_INTERVAL_S,
    DEFAULT_OFFSET_POLL_INTERVAL,
    DEFAULT_PRESENCE_POLL_INTERVAL,
    DEFAULT_QUOTA_SAFETY_RESERVE,
    DEFAULT_REDUCED_POLLING_END,
    DEFAULT_REDUCED_POLLING_INTERVAL,
    DEFAULT_REDUCED_POLLING_START,
    DEFAULT_REFRESH_AFTER_RESUME,
    DEFAULT_SLOW_POLL_INTERVAL,
    DEFAULT_SUPPRESS_REDUNDANT_BUTTONS,
    DEFAULT_SUPPRESS_REDUNDANT_CALLS,
    DEFAULT_THROTTLE_THRESHOLD,
    DOMAIN,
    GEN_CLASSIC,
    GEN_X,
    MIN_AUTO_QUOTA_INTERVAL_S,
    MIN_PROXY_INTERVAL_S,
    OVERLAY_NEXT_BLOCK,
    POWER_OFF,
    POWER_ON,
    RESUME_REFRESH_DELAY_S,
    SECONDS_PER_HOUR,
    TEMP_DEFAULT_AC,
    TEMP_DEFAULT_HEATING,
    TEMP_DEFAULT_HOT_WATER,
    THROTTLE_RECOVERY_INTERVAL_S,
    ZONE_TYPE_AIR_CONDITIONING,
    ZONE_TYPE_HEATING,
    ZONE_TYPE_HOT_WATER,
)
from .dummy.dummy_handler import TadoDummyHandler  # [DUMMY_HOOK]
from .helpers.api_manager import TadoApiManager
from .helpers.auth_manager import AuthManager
from .helpers.data_manager import TadoDataManager, UnifiedDataProvider
from .helpers.device_linker import get_climate_entity_id
from .helpers.entity_resolver import EntityResolver
from .helpers.event_handlers import TadoEventHandler
from .helpers.logging_utils import get_redacted_logger
from .helpers.optimistic_manager import OptimisticManager
from .helpers.overlay_builder import build_overlay_data
from .helpers.poll_scheduler import PollScheduler
from .helpers.property_manager import PropertyManager
from .helpers.quota_math import (
    calculate_remaining_polling_budget,
    calculate_safety_reserve_interval,
    calculate_weighted_interval,
    check_quota_reset,
    get_seconds_until_reset,
    is_in_reset_safe_window,
)
from .helpers.rate_limit_manager import RateLimitManager
from .helpers.reset_window_tracker import ResetWindowTracker
from .helpers.state_patcher import patch_zone_overlay, patch_zone_resume
from .helpers.storage import TadoStorage
from .helpers.utils import apply_jitter
from .lib.patches import get_handler
from .models import CommandType, RateLimit, TadoCommand, TadoData

_LOGGER = get_redacted_logger(__name__)


class TadoDataUpdateCoordinator(DataUpdateCoordinator[Any]):
    """Orchestrates Tado integration logic via specialized managers."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: TadoConfigEntry,
        client: Tado,
        scan_interval: int,
    ):
        """Initialize Tado coordinator."""
        self._tado = client

        self.generation = entry.data.get(CONF_GENERATION, GEN_CLASSIC)

        # Migration: old values
        if self.generation in ("v2", "v3", "v2_v3", "classic"):
            self.generation = GEN_CLASSIC
        elif self.generation == "x":
            self.generation = GEN_X

        self.full_cloud_mode = entry.data.get(CONF_FULL_CLOUD_MODE, False)
        self.fetch_extended_data = entry.data.get(CONF_FETCH_EXTENDED_DATA, True)
        self.provider: UnifiedDataProvider | None = None

        if self.generation == GEN_X:
            from .helpers.tadox.mapper import TadoXMapper
            from .lib.tadox_api import TadoXApi

            self.tadox_bridge = TadoXApi(client)
            self.provider = TadoXMapper(self.tadox_bridge)
            _LOGGER.debug("Initialized Tado X mode")
        elif self.generation == GEN_CLASSIC:
            from .helpers.client import TadoHijackClient
            from .helpers.tadov3.mapper import TadoV3Mapper

            self.provider = TadoV3Mapper(cast(TadoHijackClient, client))
            _LOGGER.info(
                "Initialized Classic mode (full_cloud=%s)", self.full_cloud_mode
            )
        else:
            raise ValueError(f"Unknown generation: {self.generation}")

        update_interval = (
            timedelta(seconds=scan_interval) if scan_interval > 0 else None
        )

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=update_interval,
        )

        throttle_threshold = int(
            entry.data.get(CONF_THROTTLE_THRESHOLD, DEFAULT_THROTTLE_THRESHOLD)
        )
        self._disable_polling_when_throttled: bool = bool(
            entry.data.get(CONF_DISABLE_POLLING_WHEN_THROTTLED, False)
        )
        self._debounce_time = int(
            entry.data.get(CONF_DEBOUNCE_TIME, DEFAULT_DEBOUNCE_TIME)
        )
        self._auto_api_quota_percent = int(
            entry.data.get(CONF_AUTO_API_QUOTA_PERCENT, DEFAULT_AUTO_API_QUOTA_PERCENT)
        )
        self._refresh_after_resume: bool = bool(
            entry.data.get(CONF_REFRESH_AFTER_RESUME, DEFAULT_REFRESH_AFTER_RESUME)
        )
        self._suppress_redundant_calls: bool = bool(
            entry.data.get(
                CONF_SUPPRESS_REDUNDANT_CALLS, DEFAULT_SUPPRESS_REDUNDANT_CALLS
            )
        )
        self._suppress_redundant_buttons: bool = bool(
            entry.data.get(
                CONF_SUPPRESS_REDUNDANT_BUTTONS, DEFAULT_SUPPRESS_REDUNDANT_BUTTONS
            )
        )
        self._base_scan_interval = scan_interval  # Store original interval

        self.is_polling_enabled = True  # Master switch (always starts ON)
        self.is_reduced_polling_logic_enabled = bool(
            entry.data.get(CONF_REDUCED_POLLING_ACTIVE, False)
        )

        self.rate_limit = RateLimitManager(throttle_threshold, get_handler())
        self.auth_manager = AuthManager(hass, entry, client)
        self.property_manager = PropertyManager(self)

        slow_poll_s = entry.data.get(
            CONF_SLOW_POLL_INTERVAL, DEFAULT_SLOW_POLL_INTERVAL
        )
        offset_poll_s = entry.data.get(
            CONF_OFFSET_POLL_INTERVAL, DEFAULT_OFFSET_POLL_INTERVAL
        )
        presence_poll_s = entry.data.get(
            CONF_PRESENCE_POLL_INTERVAL, DEFAULT_PRESENCE_POLL_INTERVAL
        )
        self.data_manager = TadoDataManager(
            self,
            client,
            slow_poll_s,
            offset_poll_s,
            presence_poll_s,
            provider=self.provider,
        )
        self.api_manager = TadoApiManager(hass, self, self._debounce_time)
        # [DUMMY_HOOK]
        self.dummy_handler = TadoDummyHandler(self) if CONF_ENABLE_DUMMY_ZONES else None
        _LOGGER.info(
            "Coordinator Init: Generation=%s, DummiesEnabled=%s, Proxy=%s",
            self.generation,
            CONF_ENABLE_DUMMY_ZONES,
            bool(entry.data.get(CONF_API_PROXY_URL)),
        )

        self.optimistic = OptimisticManager()
        self.entity_resolver = EntityResolver(self)
        self.event_handler = TadoEventHandler(self)

        from .helpers.action_provider_base import TadoActionProvider
        from .helpers.tadov3.action_provider import TadoV3ActionProvider
        from .helpers.tadox.action_provider import TadoXActionProvider

        # Initialize action provider now that coordinator is ready
        if self.generation == GEN_X:
            self.action_provider: TadoActionProvider = TadoXActionProvider(self)
        else:
            self.action_provider = TadoV3ActionProvider(self)

        self.zones_meta: dict[int, Zone | HopsRoomSnapshot] = {}
        self.devices_meta: dict[str, Device] = {}
        self.bridges: list[Device] = []
        self._climate_to_zone: dict[str, int] = {}
        self._polling_calls_today = 0
        self._last_quota_reset: datetime | None = None
        self._last_remaining: int | None = None
        self._force_next_update: bool = False

        # Adaptive quota reset window learning
        self.reset_tracker = ResetWindowTracker()
        self.storage = TadoStorage(hass, entry.entry_id)

        self.poll_scheduler = PollScheduler(hass)
        self.api_manager.start(entry)
        self.event_handler.setup()
        self._schedule_reset_poll()

    async def async_setup(self) -> None:
        """Set up coordinator and load persistent state."""
        tracker_data = await self.storage.async_get("reset_tracker")
        if tracker_data:
            self.reset_tracker.load_dict(tracker_data)
            _LOGGER.debug(
                "Restored adaptive quota tracker state (history: %d)",
                self.reset_tracker.history_count,
            )
            # Without this, get_next_reset_time falls back to now+20h on restart.
            if last_reset := self.reset_tracker.get_last_reset_original():
                self._last_quota_reset = last_reset

    def _save_reset_tracker(self) -> None:
        """Persist reset tracker state to storage."""
        self.hass.async_create_task(
            self.storage.async_update("reset_tracker", self.reset_tracker.to_dict())
        )

    def _update_climate_map(self) -> None:
        """Map HomeKit climate entities to Tado zones (v3 only).

        Should only be called for v3 Classic generation.
        """
        for zone in self.zones_meta.values():
            if zone.type != ZONE_TYPE_HEATING:
                continue
            for device in zone.devices:
                if climate_id := get_climate_entity_id(self.hass, device.serial_no):
                    self._climate_to_zone[climate_id] = zone.id

    @property
    def client(self) -> TadoHijackClient:
        """Return the Tado client."""
        return cast("TadoHijackClient", self._tado)

    def get_zone_id_from_entity(self, entity_id: str) -> int | None:
        """Resolve a Tado zone ID from any entity ID (HomeKit or Hijack)."""
        return self.entity_resolver.get_zone_id(entity_id)

    def is_feature_supported(self, feature: str) -> bool:
        """Check if a feature is supported by the current hardware generation."""
        return self.provider.is_feature_supported(feature) if self.provider else True

    def get_device_offset(self, serial: str) -> Any:
        """Return the temperature offset for a device."""
        return self.data_manager.offsets_cache.get(serial)

    def get_away_config(self, zone_id: int) -> float | None:
        """Return the away temperature for a zone."""
        return self.data_manager.away_cache.get(zone_id)

    async def async_get_capabilities(self, zone_id: int) -> Any:
        """Return capabilities for a zone."""
        return await self.data_manager.async_get_capabilities(zone_id)

    def get_active_zones(
        self,
        include_heating: bool = True,
        include_ac: bool = False,
        include_hot_water: bool = False,
    ) -> list[int]:
        """Return a list of active zone IDs filtered by type.

        Delegates to generation-specific action provider.
        """
        return self.action_provider.get_active_zone_ids(
            include_heating=include_heating,
            include_hot_water=include_hot_water,
            include_ac=include_ac,
        )

    async def _async_update_data(self) -> TadoData:
        """Fetch update via DataManager."""
        if not self.is_polling_enabled and not self._force_next_update:
            _LOGGER.debug("Polling globally disabled via switch.")
            if self.data:
                return cast(TadoData, self.data)
            _LOGGER.info(
                "No data exists, allowing initial fetch despite disabled switch"
            )

        if self.is_reduced_polling_logic_enabled:
            conf = self._get_reduced_window_config()
            if conf and conf["interval"] == 0:
                now = dt_util.now()
                if self._is_in_reduced_window(now, conf):
                    _LOGGER.debug("In 0-polling window, skipping API call.")
                    if self.data:
                        self.async_update_interval_local()
                        return cast(TadoData, self.data)

        if (
            self._disable_polling_when_throttled
            and self.rate_limit.is_throttled
            and not self._force_next_update
        ):
            _LOGGER.warning(
                "Throttled (remaining: %d, threshold: %d). Polling suspended.",
                self.rate_limit.remaining,
                self.rate_limit.throttle_threshold,
            )
            if self.data:
                return cast(TadoData, self.data)

            # If no data exists yet, allow first fetch
            _LOGGER.info("No data exists, allowing initial fetch despite throttling")

        try:
            quota_start = self.rate_limit.remaining
            _LOGGER.debug("Starting data fetch (quota: %d)", quota_start)

            data = await self.data_manager.fetch_full_update()

            self.zones_meta = self.data_manager.zones_meta
            self.devices_meta = self.data_manager.devices_meta

            from .helpers.discovery import get_bridges

            self.bridges = get_bridges(self.devices_meta, self.generation)

            if self.generation == GEN_CLASSIC and not self.full_cloud_mode:
                self._update_climate_map()

            self.auth_manager.check_and_update_token()
            self.optimistic.cleanup()

            self.rate_limit.sync_from_headers()

            actual_cost = quota_start - self.rate_limit.remaining
            if actual_cost > 0:
                self.rate_limit.last_poll_cost = float(actual_cost)
                self._polling_calls_today += actual_cost

            self._detect_quota_reset()

            data.rate_limit = RateLimit(
                limit=self.rate_limit.limit, remaining=self.rate_limit.remaining
            )
            data.api_status = self.rate_limit.api_status

            self._adjust_interval_for_auto_quota()

            # Reset force flag only after a successful fetch
            self._force_next_update = False

            return cast(TadoData, data)
        except (TimeoutError, TadoError, aiohttp.ClientError) as err:
            self._force_next_update = False

            if self.data:
                _LOGGER.warning("Tado API transient error, using cached data: %s", err)
                return cast(TadoData, self.data)

            raise UpdateFailed(f"Tado API error: {err}") from err
        except Exception as err:
            self._force_next_update = False
            _LOGGER.error("Unexpected error fetching Tado data: %s", err, exc_info=True)
            if self.data:
                return cast(TadoData, self.data)
            raise UpdateFailed(f"Unexpected error: {err}") from err

    def _handle_throttled_interval(self, seconds_until_reset: int) -> int:
        """Handle polling interval when throttled."""
        if self._disable_polling_when_throttled:
            _LOGGER.warning(
                "Throttled (remaining=%d). Polling suspended until reset.",
                self.rate_limit.remaining,
            )
            return max(THROTTLE_RECOVERY_INTERVAL_S, seconds_until_reset)
        return THROTTLE_RECOVERY_INTERVAL_S

    def _handle_economy_window_interval(
        self, expected_hour: int | None, expected_minute: int | None
    ) -> int | None:
        """Handle polling interval during economy window."""
        conf = self._get_reduced_window_config()
        now = dt_util.now()
        if not conf or not self._is_in_reduced_window(now, conf):
            return None

        reduced_interval = conf["interval"]
        if reduced_interval == 0:
            test_dt = now + timedelta(minutes=1)
            next_reset = self.reset_tracker.get_next_reset_time()
            while self._is_in_reduced_window(test_dt, conf) and test_dt < next_reset:
                test_dt += timedelta(minutes=15)
            diff = int((test_dt - now).total_seconds())
            _LOGGER.debug("In 0-polling window. Sleeping for %ds.", diff)
            return max(self._get_min_auto_quota_interval(), diff)

        _LOGGER.debug("In economy window. Using interval: %ds", reduced_interval)
        return int(reduced_interval)

    def _handle_budget_exhausted(
        self, safety_reserve: int, expected_hour: int | None = None
    ) -> int | None:
        """Handle interval when budget is exhausted."""
        if is_in_reset_safe_window(expected_hour) and safety_reserve > 0:
            safety_interval = calculate_safety_reserve_interval(safety_reserve)
            _LOGGER.debug(
                "Budget exhausted, using safety reserve (%d calls @ %ds interval)",
                safety_reserve,
                safety_interval,
            )
            return safety_interval
        return (
            max(int(self._base_scan_interval), 300)
            if self._base_scan_interval > 0
            else None
        )

    def _calculate_simple_adaptive_interval(
        self, remaining_budget: float, seconds_until_reset: int, min_floor: int
    ) -> int:
        """Calculate simple adaptive interval without reduced window logic."""
        predicted_cost = self.data_manager._measure_zones_poll_cost()

        max_possible_polls = seconds_until_reset / min_floor
        budget_needed = max_possible_polls * predicted_cost

        if budget_needed <= remaining_budget:
            return min_floor

        remaining_polls = remaining_budget / predicted_cost
        if remaining_polls <= 0:
            return SECONDS_PER_HOUR

        adaptive_interval = seconds_until_reset / remaining_polls
        return int(max(min_floor, min(SECONDS_PER_HOUR, adaptive_interval)))

    def _calculate_auto_quota_interval(self) -> int | None:
        """Calculate optimal polling interval based on quota settings.

        Priority:
        1. Invalid limit → safety interval
        2. Throttled → recovery interval
        3. Economy window → reduced interval
        4. Auto quota disabled → None
        5. Budget exhausted → safety reserve or fallback
        6. Normal operation → adaptive interval
        """
        # 0. Validate quota limit
        if self.rate_limit.limit <= 0:
            _LOGGER.warning(
                "Invalid API limit (%d). Using safety interval.",
                self.rate_limit.limit,
            )
            return max(int(self._base_scan_interval), 300)

        expected_hour, expected_minute = self._get_learned_reset_window()
        seconds_until_reset = get_seconds_until_reset(
            self.reset_tracker.get_next_reset_time()
        )

        # 1. Throttling (Highest Priority)
        if self.rate_limit.is_throttled:
            return self._handle_throttled_interval(seconds_until_reset)

        # 2. Economy Window (if active)
        if self.is_reduced_polling_logic_enabled:
            if interval := self._handle_economy_window_interval(
                expected_hour, expected_minute
            ):
                return interval

        # 3. Auto Quota disabled
        if self._auto_api_quota_percent <= 0:
            return None

        min_floor = self._get_min_auto_quota_interval()
        background_cost_24h, _ = self.data_manager.estimate_daily_reserved_cost()
        safety_reserve = int(
            self.config_entry.data.get(
                CONF_QUOTA_SAFETY_RESERVE, DEFAULT_QUOTA_SAFETY_RESERVE
            )
        )
        remaining_budget = calculate_remaining_polling_budget(
            limit=self.rate_limit.limit,
            remaining=self.rate_limit.remaining,
            background_cost_24h=background_cost_24h,
            throttle_threshold=self.rate_limit.throttle_threshold,
            auto_quota_percent=self._auto_api_quota_percent,
            seconds_until_reset=seconds_until_reset,
            safety_reserve=safety_reserve,
            actual_polls_today=self._polling_calls_today,
        )

        # 4. Budget exhausted
        if remaining_budget <= 0:
            return self._handle_budget_exhausted(safety_reserve, expected_hour)

        # 5. Normal operation - adaptive interval
        if not self.is_reduced_polling_logic_enabled:
            return self._calculate_simple_adaptive_interval(
                remaining_budget, seconds_until_reset, min_floor
            )

        # 6. Weighted interval with reduced window
        if conf := self._get_reduced_window_config():
            return calculate_weighted_interval(
                remaining_budget=remaining_budget,
                predicted_poll_cost=self.data_manager._measure_zones_poll_cost(),
                is_in_reduced_window_func=self._is_in_reduced_window,
                reduced_window_conf=conf,
                min_floor=min_floor,
                next_reset=self.reset_tracker.get_next_reset_time(),
            )

        return SECONDS_PER_HOUR

    def _get_learned_reset_window(self) -> tuple[int | None, int | None]:
        """Get learned reset window from tracker.

        Returns:
            (hour, minute) tuple or (None, None) if using default

        """
        expected = self.reset_tracker.get_expected_window()
        if expected.confidence == "learned":
            return expected.hour, expected.minute
        return None, None

    def _adjust_interval_for_auto_quota(self) -> None:
        """Adjust update interval based on auto API quota percentage."""
        calculated_interval = self._calculate_auto_quota_interval()

        if calculated_interval is None:
            self.update_interval = (
                timedelta(seconds=self._base_scan_interval)
                if self._base_scan_interval > 0
                else None
            )
        else:
            final_interval = float(calculated_interval)
            # Apply jitter only when using proxy (Standard requirement)
            if self.config_entry.data.get(CONF_API_PROXY_URL):
                jitter_percent = float(
                    self.config_entry.data.get(
                        CONF_JITTER_PERCENT, DEFAULT_JITTER_PERCENT
                    )
                )
                final_interval = apply_jitter(final_interval, jitter_percent)
                _LOGGER.debug("Applied jitter to interval: %s", final_interval)

            self.update_interval = timedelta(seconds=final_interval)

    def _schedule_reset_poll(self) -> None:
        """Schedule automatic poll at daily quota reset time."""
        if self._auto_api_quota_percent <= 0:
            return

        next_reset = self.reset_tracker.get_next_reset_time()
        now = dt_util.now()
        delay = (next_reset - now).total_seconds()

        _LOGGER.debug(
            "Quota: Scheduling reset poll at %s (in %.1f hours)",
            next_reset.strftime("%Y-%m-%d %H:%M:%S %Z"),
            delay / SECONDS_PER_HOUR,
        )

        self.poll_scheduler.schedule_reset_poll(delay, self._on_reset_poll)

    def _detect_quota_reset(self) -> None:
        """Detect quota reset by monitoring any increase in remaining quota.

        Since quota only decreases through usage, any upward movement
        unambiguously signals a reset. Uses adaptive learning to track actual
        reset times, independent of time-of-day.
        """
        if check_quota_reset(
            limit=self.rate_limit.limit,
            remaining=self.rate_limit.remaining,
            last_remaining=self._last_remaining,
        ):
            reset_time = dt_util.now()
            self._last_quota_reset = reset_time
            self._polling_calls_today = 0

            self.reset_tracker.record_reset(reset_time)
            self._save_reset_tracker()

            expected = self.reset_tracker.get_expected_window()
            _LOGGER.info(
                "Quota reset detected! remaining: %d/%d (%d -> %d), "
                "expected window: %s",
                self.rate_limit.remaining,
                self.rate_limit.limit,
                self._last_remaining,
                self.rate_limit.remaining,
                expected,
            )

        self._last_remaining = self.rate_limit.remaining

    async def _on_reset_poll(self) -> None:
        """Execute automatic poll at quota reset time."""
        _LOGGER.info("Quota: Executing scheduled reset poll to fetch fresh quota")

        self._force_next_update = True

        await self.async_refresh()

        self._schedule_reset_poll()

    def _schedule_expiry_poll(self, delay_s: int) -> None:
        """Schedule a poll to run when a timer expires."""
        self.poll_scheduler.schedule_expiry_poll(
            delay_s, lambda: self.async_manual_poll("zone", silent=True)
        )

    def _schedule_queued_refresh(self) -> None:
        """Schedule a debounced refresh after a resume/off action."""
        self.poll_scheduler.schedule_queued_refresh(
            RESUME_REFRESH_DELAY_S, lambda: self.async_manual_poll("zone", silent=True)
        )

    def shutdown(self) -> None:
        """Cleanup listeners and tasks."""
        self.event_handler.shutdown()
        self.poll_scheduler.shutdown()
        self.api_manager.shutdown()

    async def _execute_manual_poll(self, refresh_type: str = "all") -> None:
        """Execute the manual poll logic (worker target)."""
        self.data_manager.invalidate_cache(refresh_type)
        await self.async_refresh()

    async def async_manual_poll(
        self, refresh_type: str = "all", silent: bool = False
    ) -> None:
        """Trigger a manual poll (debounced)."""
        if not silent:
            _LOGGER.info("Queued manual poll (type: %s)", refresh_type)
        else:
            _LOGGER.debug("Queued silent manual poll (type: %s)", refresh_type)

        self._force_next_update = True
        self.api_manager.queue_command(
            f"manual_poll_{refresh_type}",
            TadoCommand(CommandType.MANUAL_POLL, data={"type": refresh_type}),
        )

    async def async_targeted_fetch(self, refresh_type: str, entity_id: str) -> None:
        """Fetch a specific data type for a single entity (targeted, cheaper than full poll)."""
        _LOGGER.info("Targeted fetch: type=%s entity=%s", refresh_type, entity_id)
        targeted = await self.data_manager.async_targeted_fetch(refresh_type, entity_id)
        if targeted:
            self.async_update_listeners()
        else:
            # Fell back to cache invalidation — need a full coordinator refresh
            await self.async_refresh()

    def update_rate_limit_local(self, silent: bool = False) -> None:
        """Update local stats and sync internal remaining from headers."""
        self.rate_limit.sync_from_headers()
        self.data.rate_limit = RateLimit(
            limit=self.rate_limit.limit,
            remaining=self.rate_limit.remaining,
        )
        self.data.api_status = self.rate_limit.api_status
        if not silent:
            self.async_update_listeners()

    async def async_sync_states(self, types: list[str]) -> None:
        """Targeted refresh after worker actions."""
        if "presence" in types:
            self.data.home_state = await self._tado.get_home_state()
        if "zone" in types:
            self.data.zone_states = await self._tado.get_zone_states()

        self.update_rate_limit_local(silent=False)

    async def async_set_zone_hvac_mode(
        self,
        zone_id: int,
        hvac_mode: str,
        temperature: float | None = None,
        duration: int | None = None,
        overlay_mode: str | None = None,
        ac_mode: str | None = None,
        refresh_after: bool = False,
    ) -> None:
        """Set HVAC mode for a zone with integrated type-specific logic (DRY)."""
        if hvac_mode == "auto":
            await self.async_set_zone_auto(zone_id, refresh_after=refresh_after)
            return

        power = POWER_OFF if hvac_mode == "off" else POWER_ON

        # Temperature resolution happens in async_set_zone_overlay -> _resolve_zone_temperature
        # No need to duplicate that logic here
        await self.async_set_zone_overlay(
            zone_id=zone_id,
            power=power,
            temperature=temperature,
            duration=duration,
            overlay_type=None,  # Auto-resolve
            overlay_mode=overlay_mode,
            ac_mode=ac_mode,
            refresh_after=refresh_after,
        )

    def _execute_overlay_command(
        self,
        zone_id: int,
        data: dict[str, Any],
        power: str | None = None,
        temperature: float | None = None,
        operation_mode: str | None = None,
    ) -> None:
        """Apply optimistic overlay state and queue the SET_OVERLAY command."""
        old_state = patch_zone_overlay(self.data.zone_states.get(str(zone_id)), data)
        self.optimistic.apply_zone_state(
            zone_id,
            overlay=True,
            power=power,
            temperature=temperature,
            operation_mode=operation_mode,
        )
        self.async_update_listeners()
        self.api_manager.queue_command(
            f"zone_{zone_id}",
            TadoCommand(
                CommandType.SET_OVERLAY,
                zone_id=zone_id,
                data=data,
                rollback_context=old_state,
            ),
        )

    def _execute_resume_command(
        self, zone_id: int, operation_mode: str | None = None
    ) -> None:
        """Apply optimistic resume state and queue the RESUME_SCHEDULE command."""
        old_state = patch_zone_resume(self.data.zone_states.get(str(zone_id)))
        self.optimistic.apply_zone_state(
            zone_id, overlay=False, operation_mode=operation_mode
        )
        self.async_update_listeners()
        self.api_manager.queue_command(
            f"zone_{zone_id}",
            TadoCommand(
                CommandType.RESUME_SCHEDULE,
                zone_id=zone_id,
                rollback_context=old_state,
            ),
        )

    async def async_set_zone_auto(
        self,
        zone_id: int,
        refresh_after: bool = False,
        ignore_global_config: bool = False,
    ) -> None:
        """Set zone to auto mode (resume schedule)."""
        self._execute_resume_command(zone_id)

        # Trigger refresh only for AC and Hot Water zones (TRVs are excluded)
        from .helpers.zone_utils import get_zone_type

        zone = self.zones_meta.get(zone_id)
        ztype = get_zone_type(zone, None)
        is_refresh_eligible = ztype in (
            ZONE_TYPE_AIR_CONDITIONING,
            ZONE_TYPE_HOT_WATER,
        )

        if (
            refresh_after or (self._refresh_after_resume and not ignore_global_config)
        ) and is_refresh_eligible:
            self._schedule_queued_refresh()

    async def async_set_zone_heat(self, zone_id: int, temp: float = 25.0) -> None:
        """Set zone to manual mode with temperature."""
        data = build_overlay_data(
            zone_id,
            self.zones_meta,
            power="ON",
            temperature=temp,
            supports_temp=self.supports_temperature(zone_id),
        )
        self._execute_overlay_command(zone_id, data, power="ON", temperature=temp)

    async def async_set_zone_off(self, zone_id: int) -> None:
        """Set zone to OFF (frost protection mode).

        Uses magic number (OFF_MAGIC_TEMP) to signal OFF mode.
        Executor will map OFF_MAGIC_TEMP to power=OFF before sending to API.
        """
        from .const import OFF_MAGIC_TEMP

        data = build_overlay_data(
            zone_id,
            self.zones_meta,
            power="ON",
            temperature=OFF_MAGIC_TEMP,
            supports_temp=self.supports_temperature(zone_id),
        )
        self._execute_overlay_command(
            zone_id, data, power="ON", temperature=OFF_MAGIC_TEMP
        )

    async def async_set_hot_water_auto(
        self,
        zone_id: int,
        refresh_after: bool = False,
        ignore_global_config: bool = False,
    ) -> None:
        """Set hot water zone to auto mode (resume schedule)."""
        self._execute_resume_command(zone_id, operation_mode="auto")

        if refresh_after or (self._refresh_after_resume and not ignore_global_config):
            self._schedule_queued_refresh()

    async def async_set_hot_water_off(
        self, zone_id: int, refresh_after: bool = False
    ) -> None:
        """Set hot water zone to off (manual overlay)."""
        data = build_overlay_data(
            zone_id,
            self.zones_meta,
            power="OFF",
            overlay_type="HOT_WATER",
            supports_temp=self.supports_temperature(zone_id),
        )
        self._execute_overlay_command(zone_id, data, power="OFF")

        if refresh_after:
            self._schedule_queued_refresh()

    async def async_set_hot_water_heat(
        self, zone_id: int, temperature: float | None = None
    ) -> None:
        """Set hot water zone to heat mode (manual overlay)."""
        state = self.data.zone_states.get(str(zone_id))
        temp = temperature or TEMP_DEFAULT_HOT_WATER

        # If no temp provided, try to get from current state as fallback
        if (
            temperature is None
            and state
            and state.setting
            and hasattr(state.setting, "temperature")
            and state.setting.temperature
        ):
            temp = state.setting.temperature.celsius

        # Builder will only include temperature if supports_temp=True (OpenTherm)
        data = build_overlay_data(
            zone_id,
            self.zones_meta,
            power="ON",
            temperature=temp,
            overlay_type="HOT_WATER",
            supports_temp=self.supports_temperature(zone_id),
        )
        self._execute_overlay_command(
            zone_id, data, operation_mode="heat", temperature=temp
        )

    async def async_set_presence_debounced(self, presence: str) -> None:
        """Set presence state."""
        self.optimistic.set_presence(presence)

        old_presence = None
        if self.data and self.data.home_state:
            old_presence = self.data.home_state.presence
            self.data.home_state.presence = presence

        self.async_update_listeners()
        self.api_manager.queue_command(
            "presence",
            TadoCommand(
                CommandType.SET_PRESENCE,
                data={"presence": presence, "old_presence": old_presence},
            ),
        )

    def _get_reduced_window_config(self) -> dict[str, Any] | None:
        """Fetch and parse reduced window configuration."""
        try:
            start_str = self.config_entry.data.get(
                CONF_REDUCED_POLLING_START, DEFAULT_REDUCED_POLLING_START
            )
            end_str = self.config_entry.data.get(
                CONF_REDUCED_POLLING_END, DEFAULT_REDUCED_POLLING_END
            )
            interval = self.config_entry.data.get(
                CONF_REDUCED_POLLING_INTERVAL, DEFAULT_REDUCED_POLLING_INTERVAL
            )

            # Support HH:MM and HH:MM:SS formats from HA TimeSelector
            start_h, start_m = map(int, start_str.split(":")[:2])
            end_h, end_m = map(int, end_str.split(":")[:2])

            return {
                "start_h": start_h,
                "start_m": start_m,
                "end_h": end_h,
                "end_m": end_m,
                "interval": interval,
            }
        except Exception as e:
            _LOGGER.error("Error parsing reduced window config: %s", e)
            return None

    def _is_in_reduced_window(self, dt: datetime, conf: dict[str, Any]) -> bool:
        """Check if a given datetime is within the configured reduced window."""
        t = dt.time()
        start = dt.replace(
            hour=conf["start_h"], minute=conf["start_m"], second=0, microsecond=0
        ).time()
        end = dt.replace(
            hour=conf["end_h"], minute=conf["end_m"], second=0, microsecond=0
        ).time()

        return start <= t <= end if start <= end else t >= start or t <= end

    def _get_min_auto_quota_interval(self) -> int:
        """Get minimum auto quota interval with mode-specific floor enforcement.

        One field, two minimums:
        - Proxy mode: Minimum 120s (enforced even if user sets lower)
        - Standard mode: Minimum 5s (enforced even if user sets lower)
        """
        configured = self.config_entry.data.get(
            CONF_MIN_AUTO_QUOTA_INTERVAL_S, DEFAULT_MIN_AUTO_QUOTA_INTERVAL_S
        )

        if self.config_entry.data.get(CONF_API_PROXY_URL):
            # Proxy: Enforce 120s minimum
            return max(MIN_PROXY_INTERVAL_S, int(configured))

        # Standard: Enforce 5s minimum
        return max(MIN_AUTO_QUOTA_INTERVAL_S, int(configured))

    async def async_set_polling_active(self, enabled: bool) -> None:
        """Globally enable or disable periodic polling."""
        self.is_polling_enabled = enabled
        _LOGGER.info("Polling %s globally", "enabled" if enabled else "disabled")

        # If enabling, force a refresh to get latest data immediately
        if enabled:
            self._force_next_update = True
            await self.async_refresh()
        else:
            # If disabling, we just stop the interval
            self.async_update_interval_local()
            self.async_update_listeners()

    async def async_set_reduced_polling_logic(self, enabled: bool) -> None:
        """Enable or disable the reduced polling timeframe logic."""
        self.is_reduced_polling_logic_enabled = enabled
        _LOGGER.info("Reduced polling logic %s", "enabled" if enabled else "disabled")

        # Persist change to config entry
        new_data = {**self.config_entry.data, CONF_REDUCED_POLLING_ACTIVE: enabled}
        self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)

        # Trigger re-calculation of interval
        self.async_update_interval_local()
        self.async_update_listeners()

    def async_update_interval_local(self) -> None:
        """Recalculate and set the update interval immediately."""
        new_interval_s = self._calculate_auto_quota_interval()
        if not self.is_polling_enabled:
            self.update_interval = None
        elif new_interval_s is None:
            self.update_interval = (
                timedelta(seconds=self._base_scan_interval)
                if self._base_scan_interval > 0
                else None
            )
        else:
            self.update_interval = timedelta(seconds=new_interval_s)

    async def async_set_child_lock(self, serial_no: str, enabled: bool) -> None:
        """Set child lock for a device."""
        old_val = None
        if device := self.devices_meta.get(serial_no):
            old_val = getattr(device, "child_lock_enabled", None)
            device.child_lock_enabled = enabled

        await self.property_manager.async_set_device_property(
            serial_no,
            CommandType.SET_CHILD_LOCK,
            {"serial": serial_no, "enabled": enabled},
            self.optimistic.set_child_lock,
            enabled,
            rollback_context=old_val,
        )

    async def async_set_temperature_offset(self, serial_no: str, offset: float) -> None:
        """Set temperature offset for a device."""
        await self.action_provider.async_set_temperature_offset(serial_no, offset)

    async def async_set_away_temperature(self, zone_id: int, temp: float) -> None:
        """Set away temperature for a zone."""
        old_val = self.data_manager.away_cache.get(zone_id)
        self.data_manager.away_cache[zone_id] = temp

        await self.property_manager.async_set_zone_property(
            zone_id,
            CommandType.SET_AWAY_TEMP,
            {"zone_id": zone_id, "temp": temp},
            self.optimistic.set_away_temp,
            temp,
            rollback_context=old_val,
        )

    async def async_set_dazzle_mode(self, zone_id: int, enabled: bool) -> None:
        """Set dazzle mode for a zone."""
        old_val = None
        if zone := self.zones_meta.get(zone_id):
            old_val = getattr(zone, "dazzle_enabled", None)
            zone.dazzle_enabled = enabled

        await self.property_manager.async_set_zone_property(
            zone_id,
            CommandType.SET_DAZZLE,
            {"zone_id": zone_id, "enabled": enabled},
            self.optimistic.set_dazzle,
            enabled,
            rollback_context=old_val,
        )

    async def async_set_early_start(self, zone_id: int, enabled: bool) -> None:
        """Set early start for a zone."""
        old_val = None
        if zone := self.zones_meta.get(zone_id):
            old_val = getattr(zone, "early_start_enabled", None)
            # tadoasync Zone model misses this field, so we set it dynamically
            zone.early_start_enabled = enabled  # type: ignore[union-attr]

        await self.property_manager.async_set_zone_property(
            zone_id,
            CommandType.SET_EARLY_START,
            {"zone_id": zone_id, "enabled": enabled},
            self.optimistic.set_early_start,
            enabled,
            rollback_context=old_val,
        )

    async def async_set_open_window_detection(
        self, zone_id: int, enabled: bool, timeout_seconds: int | None = None
    ) -> None:
        """Set open window detection for a zone."""
        old_val = None
        if zone := self.zones_meta.get(zone_id):
            if zone.open_window_detection:
                old_val = (
                    zone.open_window_detection.enabled,
                    zone.open_window_detection.timeout_in_seconds,
                )
                zone.open_window_detection.enabled = enabled
                if timeout_seconds is not None:
                    zone.open_window_detection.timeout_in_seconds = timeout_seconds

        data = {"zone_id": zone_id, "enabled": enabled}
        if enabled and timeout_seconds is not None:
            data["timeout_seconds"] = timeout_seconds

        await self.property_manager.async_set_zone_property(
            zone_id,
            CommandType.SET_OPEN_WINDOW,
            data,
            self.optimistic.set_open_window,
            timeout_seconds if enabled else 0,
            rollback_context=old_val,
        )

    async def async_identify_device(self, serial_no: str) -> None:
        """Identify a device."""
        self.api_manager.queue_command(
            f"identify_{serial_no}",
            TadoCommand(
                CommandType.IDENTIFY,
                data={"serial": serial_no},
            ),
        )

    async def async_add_meter_reading(self, reading: int) -> None:
        """Add a meter reading to Tado Energy IQ."""
        if self.generation == GEN_X:
            _LOGGER.warning(
                "Meter readings are not currently supported via Hops API in this integration"
            )
            # Tado X does not support set_meter_readings via the current Hops Api wrapper we have,
            # or it requires EIQ API. We will just pass for now or throw error if user tries.
        else:
            try:
                await self.client.set_meter_readings(reading=reading)
            except Exception as e:
                _LOGGER.error("Failed to add meter reading: %s", e)

    async def async_set_ac_setting(self, zone_id: int, key: str, value: str) -> None:
        """Set an AC specific setting (fan speed, swing, temperature, etc.)."""
        await self.action_provider.async_set_ac_setting(zone_id, key, value)

    def _handle_overlay_side_effects(
        self,
        duration: int | None,
        overlay_mode: str | None,
        refresh_after: bool,
    ) -> None:
        """Handle side effects like expiry timers and automatic refreshes (DRY helper)."""
        if duration and duration > 0:
            self._schedule_expiry_poll(duration * 60)

        is_timed_overlay = bool(
            duration or overlay_mode in (OVERLAY_NEXT_BLOCK, "presence")
        )

        if refresh_after and not is_timed_overlay:
            self._schedule_queued_refresh()

    def supports_temperature(self, zone_id: int) -> bool:
        """Check if a zone supports temperature control in overlays.

        Uses capabilities as source of truth. For HOT_WATER zones, we check
        if capabilities.temperatures exists. If the API later rejects with 422,
        that's a real error that should be logged.
        """
        from .helpers.zone_utils import get_zone_type

        zone = self.zones_meta.get(zone_id)
        ztype = get_zone_type(zone)

        # Heating/AC zones always support temperature
        if ztype in (ZONE_TYPE_HEATING, ZONE_TYPE_AIR_CONDITIONING):
            return True

        # Hot water: Check capabilities
        if ztype == ZONE_TYPE_HOT_WATER:
            capabilities = self.data_manager.capabilities_cache.get(zone_id)
            return bool(capabilities and getattr(capabilities, "temperatures", None))

        return True

    def _resolve_zone_temperature(
        self, zone_id: int, temperature: float | None, power: str
    ) -> float | None:
        """Resolve temperature with simple fallback chain.

        Validator will catch invalid payloads later, no need for defensive logic here.
        """
        # If temperature provided, use it
        if temperature is not None:
            return temperature

        # If power OFF, no temperature needed
        if power != POWER_ON:
            return None

        # Fallback to zone-type defaults for power ON
        from .helpers.zone_utils import get_zone_type

        zone = self.zones_meta.get(zone_id)
        ztype = get_zone_type(zone)

        if ztype == ZONE_TYPE_HOT_WATER:
            return TEMP_DEFAULT_HOT_WATER
        if ztype == ZONE_TYPE_AIR_CONDITIONING:
            return TEMP_DEFAULT_AC
        return TEMP_DEFAULT_HEATING

    async def async_set_zone_overlay(
        self,
        zone_id: int,
        power: str = "ON",
        temperature: float | None = None,
        duration: int | None = None,
        overlay_type: str | None = None,
        overlay_mode: str | None = None,
        ac_mode: str | None = None,
        optimistic_value: bool = True,
        refresh_after: bool = False,
        additional_setting_fields: dict[str, Any] | None = None,
    ) -> None:
        """Set a manual overlay with timer/duration support."""
        final_temp = self._resolve_zone_temperature(zone_id, temperature, power)

        data = build_overlay_data(
            zone_id=zone_id,
            zones_meta=self.zones_meta,
            power=power,
            temperature=final_temp,
            duration=duration,
            overlay_type=overlay_type,
            overlay_mode=overlay_mode,
            ac_mode=ac_mode,
            supports_temp=self.supports_temperature(zone_id),
            additional_setting_fields=additional_setting_fields,
        )

        old_state = patch_zone_overlay(self.data.zone_states.get(str(zone_id)), data)

        self.optimistic.apply_zone_state(
            zone_id,
            optimistic_value,
            power=power,
            temperature=final_temp,
            ac_mode=ac_mode,
        )
        self.async_update_listeners()

        self.api_manager.queue_command(
            f"zone_{zone_id}",
            TadoCommand(
                CommandType.SET_OVERLAY,
                zone_id=zone_id,
                data=data,
                rollback_context=old_state,
            ),
        )

        self._handle_overlay_side_effects(duration, overlay_mode, refresh_after)

    async def async_set_multiple_zone_overlays(
        self,
        zone_ids: list[int],
        power: str = POWER_ON,
        temperature: float | None = None,
        duration: int | None = None,
        overlay_mode: str | None = None,
        overlay_type: str | None = None,
        ac_mode: str | None = None,
        refresh_after: bool = False,
        additional_setting_fields: dict[str, Any] | None = None,
    ) -> None:
        """Set manual overlays for multiple zones in a single batched process."""
        if not zone_ids:
            return

        _LOGGER.debug(
            "Batched set_timer requested for zones: %s (mode: %s)",
            zone_ids,
            overlay_mode or "default",
        )

        for zone_id in zone_ids:
            self.optimistic.apply_zone_state(
                zone_id,
                overlay=True,
                power=power,
                temperature=temperature,
                ac_mode=ac_mode,
            )
        self.async_update_listeners()

        for zone_id in zone_ids:
            zone_temp = self._resolve_zone_temperature(zone_id, temperature, power)

            data = build_overlay_data(
                zone_id=zone_id,
                zones_meta=self.zones_meta,
                power=power,
                temperature=zone_temp,
                duration=duration,
                overlay_mode=overlay_mode,
                overlay_type=overlay_type,
                ac_mode=ac_mode,
                supports_temp=self.supports_temperature(zone_id),
                additional_setting_fields=additional_setting_fields,
            )

            old_state = patch_zone_overlay(
                self.data.zone_states.get(str(zone_id)), data
            )

            self.api_manager.queue_command(
                f"zone_{zone_id}",
                TadoCommand(
                    CommandType.SET_OVERLAY,
                    zone_id=zone_id,
                    data=data,
                    rollback_context=old_state,
                ),
            )

        self._handle_overlay_side_effects(duration, overlay_mode, refresh_after)

    async def async_resume_all_schedules(self) -> None:
        """Resume all heating zone schedules."""
        _LOGGER.debug("Resume all schedules triggered")

        # Redundancy check (Toggle 2 - Aggressive Button Suppression)
        from .helpers.redundancy_checker import should_skip_all_action_provider

        if should_skip_all_action_provider(
            action_type="resume_all",
            action_provider=self.action_provider,
            suppress_calls=self._suppress_redundant_calls,
            suppress_buttons=self._suppress_redundant_buttons,
        ):
            return

        # Delegate to generation-specific provider
        await self.action_provider.async_resume_all_schedules()

    async def async_turn_off_all_zones(self) -> None:
        """Turn off all heating zones."""
        _LOGGER.debug("Turn off all zones triggered")

        # Redundancy check (Toggle 2 - Aggressive Button Suppression)
        from .helpers.redundancy_checker import should_skip_all_action_provider

        if should_skip_all_action_provider(
            action_type="turn_off_all",
            action_provider=self.action_provider,
            suppress_calls=self._suppress_redundant_calls,
            suppress_buttons=self._suppress_redundant_buttons,
        ):
            return

        # Delegate to generation-specific provider
        await self.action_provider.async_turn_off_all_zones()

    async def async_boost_all_zones(self) -> None:
        """Boost all heating zones (25C)."""
        _LOGGER.debug("Boost all zones triggered")

        # Redundancy check (Toggle 2 - Aggressive Button Suppression)
        from .helpers.redundancy_checker import should_skip_all_action_provider

        if should_skip_all_action_provider(
            action_type="boost_all",
            action_provider=self.action_provider,
            suppress_calls=self._suppress_redundant_calls,
            suppress_buttons=self._suppress_redundant_buttons,
        ):
            return

        # Delegate to generation-specific provider
        await self.action_provider.async_boost_all_zones()
