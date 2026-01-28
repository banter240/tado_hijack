"""Data Update Coordinator for Tado Hijack."""

from __future__ import annotations

import asyncio
import copy
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    HomeAssistant,
    callback,
)

from homeassistant.components.climate import (
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    EVENT_CALL_SERVICE,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from tadoasync import Tado, TadoError
from tadoasync.models import Overlay, Temperature, Termination

if TYPE_CHECKING:
    from tadoasync.models import Device, Zone
    from . import TadoConfigEntry
    from .helpers.client import TadoHijackClient

from .const import (
    API_RESET_BUFFER_MINUTES,
    API_RESET_HOUR,
    BOOST_MODE_TEMP,
    CONF_API_PROXY_URL,
    CONF_AUTO_API_QUOTA_PERCENT,
    CONF_DEBOUNCE_TIME,
    CONF_DISABLE_POLLING_WHEN_THROTTLED,
    CONF_JITTER_PERCENT,
    CONF_OFFSET_POLL_INTERVAL,
    CONF_PRESENCE_POLL_INTERVAL,
    CONF_REDUCED_POLLING_ACTIVE,
    CONF_REDUCED_POLLING_END,
    CONF_REDUCED_POLLING_INTERVAL,
    CONF_REDUCED_POLLING_START,
    CONF_REFRESH_AFTER_RESUME,
    CONF_SLOW_POLL_INTERVAL,
    CONF_THROTTLE_THRESHOLD,
    DEFAULT_AUTO_API_QUOTA_PERCENT,
    DEFAULT_DEBOUNCE_TIME,
    DEFAULT_JITTER_PERCENT,
    DEFAULT_OFFSET_POLL_INTERVAL,
    DEFAULT_REDUCED_POLLING_END,
    DEFAULT_REDUCED_POLLING_INTERVAL,
    DEFAULT_REDUCED_POLLING_START,
    DEFAULT_PRESENCE_POLL_INTERVAL,
    DEFAULT_REFRESH_AFTER_RESUME,
    DEFAULT_SLOW_POLL_INTERVAL,
    DEFAULT_THROTTLE_THRESHOLD,
    DOMAIN,
    RESUME_REFRESH_DELAY_S,
    MIN_AUTO_QUOTA_INTERVAL_S,
    MIN_PROXY_INTERVAL_S,
    OVERLAY_NEXT_BLOCK,
    OVERLAY_PRESENCE,
    OVERLAY_TIMER,
    POWER_OFF,
    POWER_ON,
    SECONDS_PER_HOUR,
    TEMP_MAX_AC,
    TEMP_MAX_HEATING,
    TEMP_MAX_HOT_WATER,
    TERMINATION_MANUAL,
    TERMINATION_NEXT_TIME_BLOCK,
    TERMINATION_TADO_MODE,
    TERMINATION_TIMER,
    ZONE_TYPE_AIR_CONDITIONING,
    ZONE_TYPE_HEATING,
    ZONE_TYPE_HOT_WATER,
)
from .helpers.api_manager import TadoApiManager
from .helpers.auth_manager import AuthManager
from .helpers.data_manager import TadoDataManager
from .helpers.device_linker import get_climate_entity_id
from .helpers.logging_utils import get_redacted_logger
from .helpers.optimistic_manager import OptimisticManager
from .helpers.patch import get_handler
from .helpers.rate_limit_manager import RateLimitManager
from .helpers.utils import apply_jitter
from .models import CommandType, RateLimit, TadoCommand, TadoData

_LOGGER = get_redacted_logger(__name__)


class TadoDataUpdateCoordinator(DataUpdateCoordinator[TadoData]):
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
        self._base_scan_interval = scan_interval  # Store original interval

        self.is_polling_enabled = True  # Master switch (always starts ON)
        self.is_reduced_polling_logic_enabled = bool(
            entry.data.get(CONF_REDUCED_POLLING_ACTIVE, False)
        )

        self.rate_limit = RateLimitManager(throttle_threshold, get_handler())
        self.auth_manager = AuthManager(hass, entry, client)

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
            self, client, slow_poll_s, offset_poll_s, presence_poll_s
        )
        self.api_manager = TadoApiManager(hass, self, self._debounce_time)
        self.optimistic = OptimisticManager()

        # Cache for resolving entity IDs to zone IDs to avoid repeated registry scans
        self._entity_id_cache: dict[str, int] = {}

        self.zones_meta: dict[int, Zone] = {}
        self.devices_meta: dict[str, Device] = {}
        self.bridges: list[Device] = []
        self._climate_to_zone: dict[str, int] = {}
        self._unsub_listener: CALLBACK_TYPE | None = None
        self._polling_calls_today = 0
        self._last_quota_reset: datetime | None = None
        self._reset_poll_unsub: asyncio.TimerHandle | None = None  # gitleaks:allow
        self._resume_refresh_timer: asyncio.TimerHandle | None = None
        self._force_next_update: bool = False

        self.api_manager.start(entry)
        self._setup_event_listener()
        self._schedule_reset_poll()

    def _setup_event_listener(self) -> None:
        """Listen for climate service calls to trigger optimistic updates."""

        @callback
        def _handle_service_call(event: Event) -> None:
            data = event.data
            domain = data.get("domain")
            service = data.get("service")

            if domain != "climate" or service not in (
                SERVICE_SET_TEMPERATURE,
                SERVICE_SET_HVAC_MODE,
            ):
                return

            # service_data contains entity_id which can be a list or string
            service_data = data.get("service_data", {})
            entity_ids = service_data.get(ATTR_ENTITY_ID)

            if not entity_ids:
                return

            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]

            # Check if this is AUTO mode (resume schedule)
            hvac_mode = service_data.get("hvac_mode")
            is_auto_mode = hvac_mode == "auto"

            for eid in entity_ids:
                if (zone_id := self._climate_to_zone.get(eid)) is not None:
                    if is_auto_mode:
                        # AUTO mode = Resume Schedule
                        _LOGGER.debug(
                            "Intercepted AUTO mode on HomeKit climate %s. Resuming schedule for zone %d.",
                            eid,
                            zone_id,
                        )
                        self.hass.async_create_task(self.async_set_zone_auto(zone_id))
                    else:
                        # Normal temp change or other HVAC mode = Manual override
                        _LOGGER.debug(
                            "Intercepted climate change on %s. Setting optimistic MANUAL for zone %d.",
                            eid,
                            zone_id,
                        )
                        self.optimistic.set_zone(zone_id, True)
                        self.async_update_listeners()

        self._unsub_listener = self.hass.bus.async_listen(
            EVENT_CALL_SERVICE, _handle_service_call
        )

    def _update_climate_map(self) -> None:
        """Map HomeKit climate entities to Tado zones."""
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
        if entity_id in self._entity_id_cache:
            return self._entity_id_cache[entity_id]

        if (zone_id := self._climate_to_zone.get(entity_id)) is not None:
            self._entity_id_cache[entity_id] = zone_id
            return zone_id

        from homeassistant.helpers import entity_registry as er

        ent_reg = er.async_get(self.hass)
        if entry := ent_reg.async_get(entity_id):
            if (
                zone_id := self._parse_zone_id_from_unique_id(entry.unique_id)
            ) is not None:
                self._entity_id_cache[entity_id] = zone_id
                return zone_id

        _LOGGER.debug("Starting deep entity registry scan for %s", entity_id)
        target_name = entity_id.split(".", 1)[-1]
        target_base = self._get_entity_base_name(target_name)

        for entity_entry in er.async_entries_for_config_entry(
            ent_reg, self.config_entry.entry_id
        ):
            if (
                zid := self._parse_zone_id_from_unique_id(entity_entry.unique_id)
            ) is not None:
                self._entity_id_cache[entity_entry.entity_id] = zid
                entry_name = entity_entry.entity_id.split(".", 1)[-1]
                if entry_base := self._get_entity_base_name(entry_name):
                    self._entity_id_cache[f"{entity_entry.domain}.{entry_base}"] = zid

        if entity_id in self._entity_id_cache:
            return self._entity_id_cache[entity_id]

        if target_base:
            for domain in ["water_heater", "climate", "switch", "sensor"]:
                if (
                    zid := self._entity_id_cache.get(f"{domain}.{target_base}")
                ) is not None:
                    self._entity_id_cache[entity_id] = zid
                    return zid
        return None

    @staticmethod
    def _get_entity_base_name(entity_name: str | None) -> str | None:
        """Normalize an entity name by stripping numeric suffixes.

        Example: hot_water_2 -> hot_water
        """
        if not entity_name:
            return None
        if entity_name[-1].isdigit() and "_" in entity_name:
            return entity_name.rsplit("_", 1)[0]
        return entity_name

    def _parse_zone_id_from_unique_id(self, unique_id: str) -> int | None:
        """Extract zone ID from unique_id with support for multiple formats.

        Supported formats:
        - {entry_id}_hw_{zone_id}           (legacy hot water switch)
        - {entry_id}_water_heater_{zone_id} (water heater entity)
        - {entry_id}_sch_{zone_id}          (schedule switch)
        - {entry_id}_.._{zone_id}           (any suffix ending in zone_id)
        - zone_{zone_id}_...                (zone entities like target_temp)
        """
        try:
            parts = unique_id.split("_")

            # Pattern 1: Ends with zone_id (e.g., entry_hw_5, entry_sch_5)
            if parts[-1].isdigit():
                return int(parts[-1])

            # Pattern 2: zone_{id}_suffix (e.g., zone_5_target_temp)
            # Find "zone" and check if next part is the zone_id
            for i, part in enumerate(parts):
                if part == "zone" and i + 1 < len(parts) and parts[i + 1].isdigit():
                    return int(parts[i + 1])

        except (ValueError, IndexError, AttributeError):
            pass
        return None

    def _is_zone_disabled(self, zone_id: int) -> bool:
        """Check if the zone control is disabled by user."""
        if not self.config_entry:
            return False

        from homeassistant.helpers import entity_registry as er

        ent_reg = er.async_get(self.hass)
        unique_id = f"{self.config_entry.entry_id}_sch_{zone_id}"
        if entity_id := ent_reg.async_get_entity_id("switch", DOMAIN, unique_id):
            entry = ent_reg.async_get(entity_id)
            if entry and entry.disabled:
                return True
        return False

    def get_active_zones(
        self,
        include_heating: bool = True,
        include_ac: bool = False,
        include_hot_water: bool = False,
    ) -> list[int]:
        """Return a list of active zone IDs filtered by type (DRY helper)."""
        zone_ids: list[int] = []
        for zid, zone in self.zones_meta.items():
            ztype = getattr(zone, "type", ZONE_TYPE_HEATING)
            if (
                (ztype == ZONE_TYPE_HEATING and include_heating)
                or (ztype == ZONE_TYPE_AIR_CONDITIONING and include_ac)
                or (ztype == ZONE_TYPE_HOT_WATER and include_hot_water)
            ) and not self._is_zone_disabled(zid):
                zone_ids.append(zid)
        return zone_ids

    async def _async_update_data(self) -> TadoData:
        """Fetch update via DataManager."""
        if not self.is_polling_enabled:
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
            # Return existing data without making new API calls
            if self.data:
                return cast(TadoData, self.data)

            # If no data exists yet, allow first fetch
            _LOGGER.info("No data exists, allowing initial fetch despite throttling")

        self._force_next_update = False

        try:
            quota_start = self.rate_limit.remaining

            data = await self.data_manager.fetch_full_update()

            self.zones_meta = self.data_manager.zones_meta
            self.devices_meta = self.data_manager.devices_meta
            self._update_climate_map()

            self.auth_manager.check_and_update_token()
            self.optimistic.cleanup()

            self.rate_limit.sync_from_headers()

            actual_cost = quota_start - self.rate_limit.remaining
            if actual_cost > 0:
                self.rate_limit.last_poll_cost = float(actual_cost)

            data.rate_limit = RateLimit(
                limit=self.rate_limit.limit,
                remaining=self.rate_limit.remaining,
            )
            data.api_status = self.rate_limit.api_status

            self._adjust_interval_for_auto_quota()

            return cast(TadoData, data)
        except TadoError as err:
            raise UpdateFailed(f"Tado API error: {err}") from err

    def _get_next_reset_time(self) -> datetime:
        """Get the next API quota reset time (12:01 AM Berlin)."""
        berlin_tz = dt_util.get_time_zone("Europe/Berlin")
        now_berlin = dt_util.now().astimezone(berlin_tz)

        # Reset happens at 12:01 Berlin (CET/CEST)
        reset_berlin = now_berlin.replace(
            hour=API_RESET_HOUR,
            minute=API_RESET_BUFFER_MINUTES,
            second=0,
            microsecond=0,
        )

        if reset_berlin <= now_berlin:
            reset_berlin += timedelta(days=1)

        return cast(datetime, reset_berlin)

    def _get_seconds_until_reset(self) -> int:
        """Get seconds until next API quota reset."""
        reset_time = self._get_next_reset_time()
        return int((reset_time - dt_util.now()).total_seconds())

    def _get_remaining_polling_budget(self, seconds_until_reset: int) -> float:
        """Calculate the remaining API budget for the rest of the day."""
        limit = self.rate_limit.limit
        remaining = self.rate_limit.remaining

        # 1. Calculate background reserves (Hardware Sync, Presence, Offsets)
        background_cost_24h, _ = self.data_manager.estimate_daily_reserved_cost()
        seconds_per_day = 24 * 3600
        progress_done = (seconds_per_day - seconds_until_reset) / seconds_per_day
        progress_remaining = seconds_until_reset / seconds_per_day

        # 2. Calculate user activity vs threshold (to protect the buffer)
        expected_background_so_far = background_cost_24h * progress_done
        actual_used_total = max(0, limit - remaining)
        user_calls_so_far = max(0, actual_used_total - expected_background_so_far)

        # Everything used beyond the threshold is "excess" and reduces our daily pool
        user_excess = max(0, user_calls_so_far - self.rate_limit.throttle_threshold)

        # 3. Calculate final available budget for the remaining day
        available_for_day = max(0, limit - background_cost_24h - user_excess)
        total_auto_quota_budget = (
            available_for_day * self._auto_api_quota_percent / 100.0
        )
        return max(0.0, total_auto_quota_budget * progress_remaining)

    def _calculate_auto_quota_interval(self) -> int | None:
        """Calculate optimal polling interval based on quota settings and reduced window."""
        if self.rate_limit.limit <= 0:
            return None

        seconds_until_reset = self._get_seconds_until_reset()

        # 1. Throttling (Highest Priority)
        if self.rate_limit.is_throttled:
            if self._disable_polling_when_throttled:
                _LOGGER.warning(
                    "Throttled (remaining=%d). Polling suspended until reset.",
                    self.rate_limit.remaining,
                )
                return max(SECONDS_PER_HOUR, seconds_until_reset)
            return SECONDS_PER_HOUR

        # 2. Economy Window (Immediate Priority if active)
        if self.is_reduced_polling_logic_enabled:
            conf = self._get_reduced_window_config()
            now = dt_util.now()
            if conf and self._is_in_reduced_window(now, conf):
                reduced_interval = conf["interval"]
                if reduced_interval == 0:
                    # Handle pause logic
                    test_dt = now + timedelta(minutes=1)
                    next_reset = self._get_next_reset_time()
                    # Safe loop to find end of window
                    while (
                        self._is_in_reduced_window(test_dt, conf)
                        and test_dt < next_reset
                    ):
                        test_dt += timedelta(minutes=15)  # Faster stepping
                    diff = int((test_dt - now).total_seconds())
                    _LOGGER.debug("In 0-polling window. Sleeping for %ds.", diff)
                    return max(MIN_AUTO_QUOTA_INTERVAL_S, diff)

                _LOGGER.debug(
                    "In economy window. Using interval: %ds", reduced_interval
                )
                return int(reduced_interval)

        # 3. Auto Quota Logic (Only if enabled)
        if self._auto_api_quota_percent <= 0:
            return None

        min_floor = (
            MIN_PROXY_INTERVAL_S
            if self.config_entry.data.get(CONF_API_PROXY_URL)
            else MIN_AUTO_QUOTA_INTERVAL_S
        )

        remaining_budget = self._get_remaining_polling_budget(seconds_until_reset)

        if remaining_budget <= 0:
            return (
                max(int(self._base_scan_interval), 300)
                if self._base_scan_interval > 0
                else None
            )

        if not self.is_reduced_polling_logic_enabled:
            predicted_cost = self.data_manager._measure_zones_poll_cost()
            remaining_polls = remaining_budget / predicted_cost
            if remaining_polls <= 0:
                return SECONDS_PER_HOUR
            adaptive_interval = seconds_until_reset / remaining_polls
            return int(max(min_floor, min(SECONDS_PER_HOUR, adaptive_interval)))

        now = dt_util.now()
        next_reset = self._get_next_reset_time()
        return self._calculate_weighted_interval(
            now, next_reset, remaining_budget, min_floor
        )

    def _calculate_weighted_interval(
        self,
        now: datetime,
        next_reset: datetime,
        remaining_budget: float,
        min_floor: int,
    ) -> int:
        """Calculate weighted interval for performance hours (reinvesting savings)."""
        try:
            conf = self._get_reduced_window_config()
            if not conf:
                return SECONDS_PER_HOUR

            # Calculate total normal and reduced seconds until next reset
            normal_seconds = 0
            reduced_seconds = 0
            test_dt = now
            while test_dt < next_reset:
                # Ensure chunk is at least the floor to prevent infinite loops
                chunk = max(
                    MIN_AUTO_QUOTA_INTERVAL_S,
                    min(3600, int((next_reset - test_dt).total_seconds())),
                )
                if self._is_in_reduced_window(test_dt, conf):
                    reduced_seconds += chunk
                else:
                    normal_seconds += chunk
                test_dt += timedelta(seconds=chunk)

            predicted_cost = self.data_manager._measure_zones_poll_cost()
            reduced_interval = conf["interval"]

            if reduced_interval == 0:
                reduced_budget_cost = 0.0
            else:
                reduced_polls_needed = reduced_seconds / reduced_interval
                reduced_budget_cost = reduced_polls_needed * predicted_cost

            # All remaining budget goes to performance (normal) hours
            normal_budget = max(0, remaining_budget - reduced_budget_cost)

            if normal_budget > 0:
                normal_polls = normal_budget / predicted_cost
                if normal_polls > 0:
                    adaptive_interval = normal_seconds / normal_polls
                    # Cap at reduced_interval to ensure night is always slower or equal
                    cap = reduced_interval if reduced_interval > 0 else SECONDS_PER_HOUR
                    return int(max(min_floor, min(cap, adaptive_interval)))

            return SECONDS_PER_HOUR

        except Exception as e:
            _LOGGER.error("Error in weighted polling calculation: %s", e)
            return int(max(min_floor, SECONDS_PER_HOUR))

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

        next_reset = self._get_next_reset_time()
        now = dt_util.now()
        delay = (next_reset - now).total_seconds()

        _LOGGER.debug(
            "Quota: Scheduling reset poll at %s (in %.1f hours)",
            next_reset.strftime("%Y-%m-%d %H:%M:%S %Z"),
            delay / 3600,
        )

        if self._reset_poll_unsub:
            self._reset_poll_unsub.cancel()

        self._reset_poll_unsub = self.hass.loop.call_later(
            max(1.0, delay), lambda: self.hass.async_create_task(self._on_reset_poll())
        )

    async def _on_reset_poll(self) -> None:
        """Execute automatic poll at quota reset time."""
        _LOGGER.info("Quota: Executing scheduled reset poll to fetch fresh quota")

        self._force_next_update = True

        await self.async_refresh()

        self._schedule_reset_poll()

    def shutdown(self) -> None:
        """Cleanup listeners and tasks."""
        if self._unsub_listener:
            self._unsub_listener()
            self._unsub_listener = None

        if self._reset_poll_unsub:
            self._reset_poll_unsub.cancel()
            self._reset_poll_unsub = None

        if self._resume_refresh_timer:
            self._resume_refresh_timer.cancel()
            self._resume_refresh_timer = None

        self.api_manager.shutdown()

    async def _execute_manual_poll(self, refresh_type: str = "all") -> None:
        """Execute the manual poll logic (worker target)."""
        self.data_manager.invalidate_cache(refresh_type)
        await self.async_refresh()

    async def async_manual_poll(self, refresh_type: str = "all") -> None:
        """Trigger a manual poll (debounced)."""
        _LOGGER.info("Queued manual poll (type: %s)", refresh_type)
        self.api_manager.queue_command(
            f"manual_poll_{refresh_type}",
            TadoCommand(CommandType.MANUAL_POLL, data={"type": refresh_type}),
        )

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
    ) -> None:
        """Set HVAC mode for a zone with integrated type-specific logic (DRY)."""
        if hvac_mode == "auto":
            await self.async_set_zone_auto(zone_id)
            return

        power = POWER_OFF if hvac_mode == "off" else POWER_ON

        final_temp = temperature
        if final_temp is not None:
            zone = self.zones_meta.get(zone_id)
            if zone and getattr(zone, "type", "") == ZONE_TYPE_HOT_WATER:
                final_temp = float(round(final_temp))

        await self.async_set_zone_overlay(
            zone_id=zone_id,
            power=power,
            temperature=final_temp,
            duration=duration,
            overlay_type=None,  # Auto-resolve
            overlay_mode=overlay_mode,
        )

    async def async_set_zone_auto(self, zone_id: int):
        """Set zone to auto mode."""
        old_state = self._patch_zone_resume(zone_id)

        self.optimistic.set_zone(zone_id, False)
        self.async_update_listeners()
        self.api_manager.queue_command(
            f"zone_{zone_id}",
            TadoCommand(
                CommandType.RESUME_SCHEDULE,
                zone_id=zone_id,
                rollback_context=old_state,
            ),
        )

        if self._refresh_after_resume:
            self._schedule_resume_refresh()

    def _schedule_resume_refresh(self) -> None:
        """Schedule a refresh after resume with grace period to collect stragglers."""
        if self._resume_refresh_timer is not None:
            self._resume_refresh_timer.cancel()

        self._resume_refresh_timer = self.hass.loop.call_later(
            RESUME_REFRESH_DELAY_S, self._execute_resume_refresh
        )

    def _execute_resume_refresh(self) -> None:
        """Execute the resume refresh (called by timer)."""
        self._resume_refresh_timer = None
        self.api_manager.queue_command(
            "refresh_after_resume",
            TadoCommand(CommandType.MANUAL_POLL, data={"type": "zone"}),
        )

    async def async_set_zone_heat(self, zone_id: int, temp: float = 25.0):
        """Set zone to manual mode with temperature."""
        zone = self.zones_meta.get(zone_id)
        overlay_type = (
            getattr(zone, "type", ZONE_TYPE_HEATING) if zone else ZONE_TYPE_HEATING
        )

        data = {
            "setting": {
                "type": overlay_type,
                "power": "ON",
                "temperature": {"celsius": temp},
            },
            "termination": {"typeSkillBasedApp": "MANUAL"},
        }

        old_state = self._patch_zone_local(zone_id, data)

        self.optimistic.set_zone(zone_id, True)
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

    async def async_set_hot_water_auto(self, zone_id: int):
        """Set hot water zone to auto mode (resume schedule)."""
        old_state = self._patch_zone_resume(zone_id)

        self.optimistic.set_zone(zone_id, False, operation_mode="auto")
        self.async_update_listeners()
        self.api_manager.queue_command(
            f"zone_{zone_id}",
            TadoCommand(
                CommandType.RESUME_SCHEDULE,
                zone_id=zone_id,
                rollback_context=old_state,
            ),
        )

    async def async_set_hot_water_off(self, zone_id: int):
        """Set hot water zone to off (manual overlay)."""
        data = {
            "setting": {"type": "HOT_WATER", "power": "OFF"},
            "termination": {"typeSkillBasedApp": "MANUAL"},
        }
        old_state = self._patch_zone_local(zone_id, data)

        self.optimistic.set_zone(zone_id, True, operation_mode="off")
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

    async def async_set_hot_water_heat(self, zone_id: int):
        """Set hot water zone to heat mode (manual overlay)."""
        setting: dict[str, Any] = {"type": "HOT_WATER", "power": "ON"}

        state = self.data.zone_states.get(str(zone_id))
        if state and state.setting and state.setting.temperature:
            setting["temperature"] = {"celsius": state.setting.temperature.celsius}

        data = {
            "setting": setting,
            "termination": {"typeSkillBasedApp": "MANUAL"},
        }

        old_state = self._patch_zone_local(zone_id, data)

        self.optimistic.set_zone(zone_id, True, operation_mode="heat")
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

    async def async_set_hot_water_power(self, zone_id: int, on: bool) -> None:
        """Set hot water power state."""
        data = {
            "setting": {"type": "HOT_WATER", "power": "ON" if on else "OFF"},
            "termination": {"typeSkillBasedApp": "MANUAL"},
        }

        old_state = self._patch_zone_local(zone_id, data)

        self.optimistic.set_zone(zone_id, True, power="ON" if on else "OFF")
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

    async def async_set_presence_debounced(self, presence: str):
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

        self.optimistic.set_child_lock(serial_no, enabled)
        self.async_update_listeners()
        self.api_manager.queue_command(
            f"child_lock_{serial_no}",
            TadoCommand(
                CommandType.SET_CHILD_LOCK,
                data={"serial": serial_no, "enabled": enabled},
                rollback_context=old_val,
            ),
        )

    async def async_set_temperature_offset(self, serial_no: str, offset: float) -> None:
        """Set temperature offset for a device."""
        old_val = self.data_manager.offsets_cache.get(serial_no)
        if old_val:
            import copy

            try:
                old_val = copy.deepcopy(old_val)
            except Exception:
                old_val = None

        self.optimistic.set_offset(serial_no, offset)
        self.async_update_listeners()
        self.api_manager.queue_command(
            f"offset_{serial_no}",
            TadoCommand(
                CommandType.SET_OFFSET,
                data={"serial": serial_no, "offset": offset},
                rollback_context=old_val,
            ),
        )

    async def async_set_away_temperature(self, zone_id: int, temp: float) -> None:
        """Set away temperature for a zone."""
        old_val = self.data_manager.away_cache.get(zone_id)
        self.data_manager.away_cache[zone_id] = temp

        self.optimistic.set_away_temp(zone_id, temp)
        self.async_update_listeners()
        self.api_manager.queue_command(
            f"away_temp_{zone_id}",
            TadoCommand(
                CommandType.SET_AWAY_TEMP,
                data={"zone_id": zone_id, "temp": temp},
                rollback_context=old_val,
            ),
        )

    async def async_set_dazzle_mode(self, zone_id: int, enabled: bool) -> None:
        """Set dazzle mode for a zone."""
        old_val = None
        if zone := self.zones_meta.get(zone_id):
            old_val = getattr(zone, "dazzle_enabled", None)
            zone.dazzle_enabled = enabled

        self.optimistic.set_dazzle(zone_id, enabled)
        self.async_update_listeners()
        self.api_manager.queue_command(
            f"dazzle_{zone_id}",
            TadoCommand(
                CommandType.SET_DAZZLE,
                data={"zone_id": zone_id, "enabled": enabled},
                rollback_context=old_val,
            ),
        )

    async def async_set_early_start(self, zone_id: int, enabled: bool) -> None:
        """Set early start for a zone."""
        old_val = None
        if zone := self.zones_meta.get(zone_id):
            old_val = getattr(zone, "early_start_enabled", None)
            # tadoasync Zone model misses this field, so we set it dynamically
            setattr(zone, "early_start_enabled", enabled)

        self.optimistic.set_early_start(zone_id, enabled)
        self.async_update_listeners()
        self.api_manager.queue_command(
            f"early_start_{zone_id}",
            TadoCommand(
                CommandType.SET_EARLY_START,
                data={"zone_id": zone_id, "enabled": enabled},
                rollback_context=old_val,
            ),
        )

    async def async_set_open_window_detection(
        self, zone_id: int, enabled: bool
    ) -> None:
        """Set open window detection for a zone."""
        old_val = None
        if zone := self.zones_meta.get(zone_id):
            if zone.open_window_detection:
                old_val = zone.open_window_detection.enabled
                zone.open_window_detection.enabled = enabled

        self.optimistic.set_open_window(zone_id, enabled)
        self.async_update_listeners()
        self.api_manager.queue_command(
            f"open_window_{zone_id}",
            TadoCommand(
                CommandType.SET_OPEN_WINDOW,
                data={"zone_id": zone_id, "enabled": enabled},
                rollback_context=old_val,
            ),
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

    async def async_get_capabilities(self, zone_id: int) -> Any:
        """Fetch capabilities via DataManager (on-demand)."""
        return await self.data_manager.async_get_capabilities(zone_id)

    async def async_set_ac_setting(self, zone_id: int, key: str, value: str) -> None:
        """Set an AC specific setting (fan speed, swing, temperature, etc.)."""
        state = self.data.zone_states.get(str(zone_id))
        if not state or not state.setting:
            _LOGGER.error("Cannot set AC setting: No state for zone %d", zone_id)
            return

        setting = {
            "type": state.setting.type,
            "power": "ON",
            "mode": state.setting.mode,
            "fanSpeed": getattr(state.setting, "fan_speed", None),
            "fanLevel": getattr(state.setting, "fan_level", None),
            "verticalSwing": getattr(state.setting, "vertical_swing", None),
            "horizontalSwing": getattr(state.setting, "horizontal_swing", None),
            "swing": getattr(state.setting, "swing", None),
        }

        if key == "temperature":
            setting["temperature"] = {"celsius": float(value)}
        elif state.setting.temperature:
            setting["temperature"] = {"celsius": state.setting.temperature.celsius}

        if key != "temperature":
            api_key_map = {
                "fan_speed": "fanSpeed",
                "vertical_swing": "verticalSwing",
                "horizontal_swing": "horizontalSwing",
                "swing": "swing",
            }

            api_key = api_key_map.get(key, key)
            setting[api_key] = value
            if key == "fan_speed":
                setting["fanLevel"] = value
            elif key == "vertical_swing":
                setting["swing"] = value

        data = {
            "setting": {k: v for k, v in setting.items() if v is not None},
            "termination": {"typeSkillBasedApp": "MANUAL"},
        }

        old_state = self._patch_zone_local(zone_id, data)

        self.optimistic.set_zone(zone_id, True, power="ON")
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

    def _patch_zone_local(self, zone_id: int, overlay_data: dict[str, Any]) -> Any:
        """Patch local zone state and return old state for rollback."""
        if not self.data or not self.data.zone_states:
            return None

        str_id = str(zone_id)
        current = self.data.zone_states.get(str_id)
        if not current:
            return None

        try:
            old_state = copy.deepcopy(current)
        except Exception as e:
            _LOGGER.warning("Failed to copy state for zone %d: %s", zone_id, e)
            return None

        try:
            sett_d = overlay_data.get("setting", {})
            term_d = overlay_data.get("termination", {})

            if current.setting:
                if "power" in sett_d:
                    current.setting.power = sett_d["power"]
                if "temperature" in sett_d and "celsius" in sett_d["temperature"]:
                    val = float(sett_d["temperature"]["celsius"])
                    if current.setting.temperature:
                        current.setting.temperature.celsius = val
                    else:
                        current.setting.temperature = Temperature(
                            celsius=val, fahrenheit=0.0
                        )

            term_obj = Termination(
                type=term_d.get("typeSkillBasedApp", "MANUAL"),
                type_skill_based_app=term_d.get("typeSkillBasedApp"),
                projected_expiry=None,
            )

            current.overlay = Overlay(
                type="MANUAL",
                setting=current.setting,
                termination=term_obj,
            )
            current.overlay_active = True

        except Exception as e:
            _LOGGER.warning("Error patching local state for zone %d: %s", zone_id, e)
            return None

        return old_state

    async def async_set_zone_overlay(
        self,
        zone_id: int,
        power: str = "ON",
        temperature: float | None = None,
        duration: int | None = None,
        overlay_type: str | None = None,
        overlay_mode: str | None = None,
        optimistic_value: bool = True,
    ) -> None:
        """Set a manual overlay with timer/duration support."""
        # Central Validation: Check if temperature control is supported
        final_temp = temperature
        if final_temp is not None and power == "ON":
            capabilities = self.data.capabilities.get(zone_id)
            if not capabilities or not capabilities.temperatures:
                _LOGGER.warning(
                    "Zone %d does not support temperature control, ignoring temperature=%s",
                    zone_id,
                    final_temp,
                )
                final_temp = None

        data = self._build_overlay_data(
            zone_id=zone_id,
            power=power,
            temperature=final_temp,
            duration=duration,
            overlay_type=overlay_type,
            overlay_mode=overlay_mode,
        )

        old_state = self._patch_zone_local(zone_id, data)

        self.optimistic.set_zone(zone_id, optimistic_value, power=power)
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

    def get_capped_temperature(self, zone_id: int, temperature: float) -> float:
        """Get safety-capped temperature based on zone type."""
        zone = self.zones_meta.get(zone_id)
        ztype = getattr(zone, "type", ZONE_TYPE_HEATING) if zone else ZONE_TYPE_HEATING

        limit = TEMP_MAX_HEATING if ztype == ZONE_TYPE_HEATING else TEMP_MAX_AC
        if ztype == ZONE_TYPE_HOT_WATER:
            limit = TEMP_MAX_HOT_WATER

        return min(temperature, limit)

    def _build_overlay_data(
        self,
        zone_id: int,
        power: str = POWER_ON,
        temperature: float | None = None,
        duration: int | None = None,
        overlay_type: str | None = None,
        overlay_mode: str | None = None,
    ) -> dict[str, Any]:
        """Build the overlay data dictionary (DRY helper)."""
        if not overlay_type:
            zone = self.zones_meta.get(zone_id)
            overlay_type = (
                getattr(zone, "type", ZONE_TYPE_HEATING) if zone else ZONE_TYPE_HEATING
            )

        if overlay_mode == OVERLAY_NEXT_BLOCK:
            termination: dict[str, Any] = {
                "typeSkillBasedApp": TERMINATION_NEXT_TIME_BLOCK
            }
        elif overlay_mode == OVERLAY_PRESENCE:
            termination = {"type": TERMINATION_TADO_MODE}
        elif overlay_mode == OVERLAY_TIMER or duration:
            duration_seconds = duration * 60 if duration else 1800
            termination = {
                "typeSkillBasedApp": TERMINATION_TIMER,
                "durationInSeconds": duration_seconds,
            }
        else:
            termination = {"typeSkillBasedApp": TERMINATION_MANUAL}

        setting: dict[str, Any] = {"type": overlay_type, "power": power}
        if temperature is not None and power == POWER_ON:
            capped_temp = self.get_capped_temperature(zone_id, temperature)
            setting["temperature"] = {"celsius": capped_temp}

        return {"setting": setting, "termination": termination}

    async def async_set_multiple_zone_overlays(
        self,
        zone_ids: list[int],
        power: str = POWER_ON,
        temperature: float | None = None,
        duration: int | None = None,
        overlay_mode: str | None = None,
        overlay_type: str | None = None,
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
            self.optimistic.set_zone(zone_id, True, power=power)
        self.async_update_listeners()

        for zone_id in zone_ids:
            data = self._build_overlay_data(
                zone_id=zone_id,
                power=power,
                temperature=temperature,
                duration=duration,
                overlay_mode=overlay_mode,
                overlay_type=overlay_type,
            )

            old_state = self._patch_zone_local(zone_id, data)

            self.api_manager.queue_command(
                f"zone_{zone_id}",
                TadoCommand(
                    CommandType.SET_OVERLAY,
                    zone_id=zone_id,
                    data=data,
                    rollback_context=old_state,
                ),
            )

    async def async_resume_all_schedules(self) -> None:
        """Resume all heating zone schedules using bulk API endpoint (single call)."""
        _LOGGER.debug("Resume all schedules triggered")

        active_zones = self.get_active_zones(include_heating=True)

        if not active_zones:
            _LOGGER.warning("No active heating zones to resume")
            return

        _LOGGER.info(
            "Queued resume schedules for %d active heating zones", len(active_zones)
        )

        for zone_id in active_zones:
            old_state = self._patch_zone_resume(zone_id)

            self.optimistic.set_zone(zone_id, False)

            self.api_manager.queue_command(
                f"zone_{zone_id}",
                TadoCommand(
                    CommandType.RESUME_SCHEDULE,
                    zone_id=zone_id,
                    rollback_context=old_state,
                ),
            )

        self.async_update_listeners()

    async def async_turn_off_all_zones(self) -> None:
        """Turn off all heating zones using bulk API endpoint."""
        _LOGGER.debug("Turn off all zones triggered")
        self._apply_bulk_zone_overlay(
            command_key="turn_off_all",
            setting={"power": POWER_OFF, "type": ZONE_TYPE_HEATING},
            action_name="turn off",
        )

    async def async_boost_all_zones(self) -> None:
        """Boost all heating zones (25C) via bulk API."""
        _LOGGER.debug("Boost all zones triggered")
        self._apply_bulk_zone_overlay(
            command_key="boost_all",
            setting={
                "power": POWER_ON,
                "type": ZONE_TYPE_HEATING,
                "temperature": {"celsius": BOOST_MODE_TEMP},
            },
            action_name="boost",
        )

    def _apply_bulk_zone_overlay(
        self,
        command_key: str,
        setting: dict[str, Any],
        action_name: str,
    ) -> None:
        """Apply same overlay setting to all heating zones (DRY helper)."""
        zone_ids = self.get_active_zones(include_heating=True)

        if not zone_ids:
            _LOGGER.warning("No active heating zones to %s", action_name)
            return

        _LOGGER.info("Queued %s for %d active zones", action_name, len(zone_ids))

        for zone_id in zone_ids:
            data = {
                "setting": setting,
                "termination": {"typeSkillBasedApp": "MANUAL"},
            }

            old_state = self._patch_zone_local(zone_id, data)

            self.optimistic.set_zone(zone_id, True)

            self.api_manager.queue_command(
                f"zone_{zone_id}",
                TadoCommand(
                    CommandType.SET_OVERLAY,
                    zone_id=zone_id,
                    data=data,
                    rollback_context=old_state,
                ),
            )

        self.async_update_listeners()

    def _patch_zone_resume(self, zone_id: int) -> Any:
        """Patch local zone state to resume schedule and return old state."""
        if not self.data or not self.data.zone_states:
            return None

        str_id = str(zone_id)
        current = self.data.zone_states.get(str_id)
        if not current:
            return None

        try:
            old_state = copy.deepcopy(current)
        except Exception as e:
            _LOGGER.warning("Failed to copy state for zone %d: %s", zone_id, e)
            return None

        current.overlay = None
        current.overlay_active = False

        return old_state
