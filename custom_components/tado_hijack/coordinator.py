"""Data Update Coordinator for Tado Hijack."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

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

from .const import (
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
    POWER_OFF,
    POWER_ON,
    SECONDS_PER_HOUR,
    TEMP_DEFAULT_AC,
    TEMP_DEFAULT_HEATING,
    TEMP_DEFAULT_HOT_WATER,
    ZONE_TYPE_AIR_CONDITIONING,
    ZONE_TYPE_HEATING,
    ZONE_TYPE_HOT_WATER,
)
from .helpers.api_manager import TadoApiManager
from .helpers.auth_manager import AuthManager
from .helpers.data_manager import TadoDataManager
from .helpers.device_linker import get_climate_entity_id
from .helpers.entity_resolver import EntityResolver
from .helpers.event_handlers import TadoEventHandler
from .helpers.logging_utils import get_redacted_logger
from .helpers.optimistic_manager import OptimisticManager
from .helpers.overlay_builder import build_overlay_data, get_capped_temperature
from .helpers.patch import get_handler
from .helpers.property_manager import PropertyManager
from .helpers.quota_math import (
    calculate_remaining_polling_budget,
    calculate_weighted_interval,
    get_next_reset_time,
    get_seconds_until_reset,
)
from .helpers.rate_limit_manager import RateLimitManager
from .helpers.state_patcher import patch_zone_overlay, patch_zone_resume
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
            self, client, slow_poll_s, offset_poll_s, presence_poll_s
        )
        self.api_manager = TadoApiManager(hass, self, self._debounce_time)
        self.optimistic = OptimisticManager()
        self.entity_resolver = EntityResolver(self)
        self.event_handler = TadoEventHandler(self)

        self.zones_meta: dict[int, Zone] = {}
        self.devices_meta: dict[str, Device] = {}
        self.bridges: list[Device] = []
        self._climate_to_zone: dict[str, int] = {}
        self._polling_calls_today = 0
        self._last_quota_reset: datetime | None = None
        self._reset_poll_unsub: asyncio.TimerHandle | None = None
        self._post_action_poll_timer: asyncio.TimerHandle | None = None
        self._expiry_timers: set[asyncio.TimerHandle] = set()
        self._force_next_update: bool = False

        self.api_manager.start(entry)
        self.event_handler.setup()
        self._schedule_reset_poll()

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
        return self.entity_resolver.get_zone_id(entity_id)

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
            ) and not self.entity_resolver.is_zone_disabled(zid):
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

    def _calculate_auto_quota_interval(self) -> int | None:
        """Calculate optimal polling interval based on quota settings and reduced window."""
        if self.rate_limit.limit <= 0:
            return None

        seconds_until_reset = get_seconds_until_reset()

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
                    test_dt = now + timedelta(minutes=1)
                    next_reset = get_next_reset_time()
                    while (
                        self._is_in_reduced_window(test_dt, conf)
                        and test_dt < next_reset
                    ):
                        test_dt += timedelta(minutes=15)
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

        background_cost_24h, _ = self.data_manager.estimate_daily_reserved_cost()
        remaining_budget = calculate_remaining_polling_budget(
            limit=self.rate_limit.limit,
            remaining=self.rate_limit.remaining,
            background_cost_24h=background_cost_24h,
            throttle_threshold=self.rate_limit.throttle_threshold,
            auto_quota_percent=self._auto_api_quota_percent,
            seconds_until_reset=seconds_until_reset,
        )

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

        if conf := self._get_reduced_window_config():
            return calculate_weighted_interval(
                remaining_budget=remaining_budget,
                predicted_poll_cost=self.data_manager._measure_zones_poll_cost(),
                is_in_reduced_window_func=self._is_in_reduced_window,
                reduced_window_conf=conf,
                min_floor=min_floor,
            )
        else:
            return SECONDS_PER_HOUR

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

        next_reset = get_next_reset_time()
        now = dt_util.now()
        delay = (next_reset - now).total_seconds()

        _LOGGER.debug(
            "Quota: Scheduling reset poll at %s (in %.1f hours)",
            next_reset.strftime("%Y-%m-%d %H:%M:%S %Z"),
            delay / SECONDS_PER_HOUR,
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

    def _schedule_expiry_poll(self, delay_s: int) -> None:
        """Schedule a poll to run when a timer expires."""
        _LOGGER.debug("Scheduling expiry poll in %d seconds (plus buffer)", delay_s)
        handle = self.hass.loop.call_later(delay_s + 2, self._execute_expiry_poll)
        self._expiry_timers.add(handle)

    def _execute_expiry_poll(self) -> None:
        """Execute the delayed expiry poll."""
        self._expiry_timers = {h for h in self._expiry_timers if not h.cancelled()}
        _LOGGER.debug("Timer expired: Triggering post-action poll")
        self.hass.async_create_task(self.async_manual_poll("zone", silent=True))

    def _schedule_queued_refresh(self) -> None:
        """Schedule a refresh after an action with grace period to collect stragglers."""
        if self._post_action_poll_timer is not None:
            self._post_action_poll_timer.cancel()

        self._post_action_poll_timer = self.hass.loop.call_later(
            RESUME_REFRESH_DELAY_S, self._execute_queued_refresh
        )

    def _execute_queued_refresh(self) -> None:
        """Execute the queued refresh."""
        self._post_action_poll_timer = None
        _LOGGER.debug("Grace period expired: Triggering post-action poll")
        self.hass.async_create_task(self.async_manual_poll("zone", silent=True))

    def shutdown(self) -> None:
        """Cleanup listeners and tasks."""
        self.event_handler.shutdown()

        if self._reset_poll_unsub:
            self._reset_poll_unsub.cancel()
            self._reset_poll_unsub = None

        if self._post_action_poll_timer:
            self._post_action_poll_timer.cancel()
            self._post_action_poll_timer = None

        for handle in self._expiry_timers:
            handle.cancel()
        self._expiry_timers.clear()

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
        refresh_after: bool = False,
    ) -> None:
        """Set HVAC mode for a zone with integrated type-specific logic (DRY)."""
        if hvac_mode == "auto":
            await self.async_set_zone_auto(zone_id, refresh_after=refresh_after)
            return

        power = POWER_OFF if hvac_mode == "off" else POWER_ON

        final_temp = temperature
        if final_temp is None and power == POWER_ON:
            zone = self.zones_meta.get(zone_id)
            ztype = (
                getattr(zone, "type", ZONE_TYPE_HEATING) if zone else ZONE_TYPE_HEATING
            )
            if ztype == ZONE_TYPE_HOT_WATER:
                final_temp = TEMP_DEFAULT_HOT_WATER
            elif ztype == ZONE_TYPE_AIR_CONDITIONING:
                final_temp = TEMP_DEFAULT_AC
            else:
                final_temp = TEMP_DEFAULT_HEATING

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
            refresh_after=refresh_after,
        )

    async def async_set_zone_auto(
        self,
        zone_id: int,
        refresh_after: bool = False,
        ignore_global_config: bool = False,
    ):
        """Set zone to auto mode."""
        old_state = patch_zone_resume(self.data.zone_states.get(str(zone_id)))

        # Use centralized orchestrator to clear manual state and set AUTO
        self.optimistic.apply_zone_state(zone_id, overlay=False)
        self.async_update_listeners()
        self.api_manager.queue_command(
            f"zone_{zone_id}",
            TadoCommand(
                CommandType.RESUME_SCHEDULE,
                zone_id=zone_id,
                rollback_context=old_state,
            ),
        )

        if refresh_after or (self._refresh_after_resume and not ignore_global_config):
            self._schedule_queued_refresh()

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

        old_state = patch_zone_overlay(self.data.zone_states.get(str(zone_id)), data)

        self.optimistic.apply_zone_state(
            zone_id, overlay=True, power="ON", temperature=temp
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

    async def async_set_hot_water_auto(
        self,
        zone_id: int,
        refresh_after: bool = False,
        ignore_global_config: bool = False,
    ):
        """Set hot water zone to auto mode (resume schedule)."""
        old_state = patch_zone_resume(self.data.zone_states.get(str(zone_id)))

        # Use centralized orchestrator to clear manual state and set AUTO
        self.optimistic.apply_zone_state(zone_id, overlay=False, operation_mode="auto")
        self.async_update_listeners()
        self.api_manager.queue_command(
            f"zone_{zone_id}",
            TadoCommand(
                CommandType.RESUME_SCHEDULE,
                zone_id=zone_id,
                rollback_context=old_state,
            ),
        )

        if refresh_after or (self._refresh_after_resume and not ignore_global_config):
            self._schedule_queued_refresh()

    async def async_set_hot_water_off(self, zone_id: int, refresh_after: bool = False):
        """Set hot water zone to off (manual overlay)."""
        data = {
            "setting": {"type": "HOT_WATER", "power": "OFF"},
            "termination": {"typeSkillBasedApp": "MANUAL"},
        }
        old_state = patch_zone_overlay(self.data.zone_states.get(str(zone_id)), data)

        self.optimistic.apply_zone_state(zone_id, overlay=True, power="OFF")
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

        if refresh_after:
            self._schedule_queued_refresh()

    async def async_set_hot_water_heat(
        self, zone_id: int, temperature: float | None = None
    ):
        """Set hot water zone to heat mode (manual overlay)."""
        setting: dict[str, Any] = {"type": "HOT_WATER", "power": "ON"}

        state = self.data.zone_states.get(str(zone_id))
        temp = temperature or TEMP_DEFAULT_HOT_WATER

        # If no temp provided, try to get from current state as secondary fallback
        if (
            temperature is None
            and state
            and state.setting
            and state.setting.temperature
        ):
            temp = state.setting.temperature.celsius

        setting["temperature"] = {"celsius": temp}

        data = {
            "setting": setting,
            "termination": {"typeSkillBasedApp": "MANUAL"},
        }

        old_state = patch_zone_overlay(self.data.zone_states.get(str(zone_id)), data)

        self.optimistic.apply_zone_state(
            zone_id, overlay=True, operation_mode="heat", temperature=temp
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

    async def async_set_hot_water_power(self, zone_id: int, on: bool) -> None:
        """Set hot water power state."""
        data = {
            "setting": {"type": "HOT_WATER", "power": "ON" if on else "OFF"},
            "termination": {"typeSkillBasedApp": "MANUAL"},
        }

        old_state = patch_zone_overlay(self.data.zone_states.get(str(zone_id)), data)

        self.optimistic.apply_zone_state(
            zone_id, overlay=True, power="ON" if on else "OFF"
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

    async def _async_set_zone_property(
        self,
        zone_id: int,
        cmd_type: CommandType,
        data: dict[str, Any],
        optimistic_func: Any,
        optimistic_value: Any,
        rollback_context: Any = None,
    ) -> None:
        """Set a zone property with optimistic state and queuing (Generic helper)."""
        optimistic_func(zone_id, optimistic_value)
        self.async_update_listeners()

        self.api_manager.queue_command(
            f"{cmd_type.value}_{zone_id}",
            TadoCommand(
                cmd_type,
                zone_id=zone_id,
                data=data,
                rollback_context=rollback_context,
            ),
        )

    async def _async_set_device_property(
        self,
        serial_no: str,
        cmd_type: CommandType,
        data: dict[str, Any],
        optimistic_func: Any,
        optimistic_value: Any,
        rollback_context: Any = None,
    ) -> None:
        """Set a device property with optimistic state and queuing (Generic helper)."""
        optimistic_func(serial_no, optimistic_value)
        self.async_update_listeners()

        self.api_manager.queue_command(
            f"{cmd_type.value}_{serial_no}",
            TadoCommand(
                cmd_type,
                data=data,
                rollback_context=rollback_context,
            ),
        )

    async def async_set_child_lock(self, serial_no: str, enabled: bool) -> None:
        """Set child lock for a device."""
        old_val = None
        if device := self.devices_meta.get(serial_no):
            old_val = getattr(device, "child_lock_enabled", None)
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
        old_val = self.data_manager.offsets_cache.get(serial_no)
        if old_val:
            import copy

            try:
                old_val = copy.deepcopy(old_val)
            except Exception:
                old_val = None

        await self.property_manager.async_set_device_property(
            serial_no,
            CommandType.SET_OFFSET,
            {"serial": serial_no, "offset": offset},
            self.optimistic.set_offset,
            offset,
            rollback_context=old_val,
        )

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
            setattr(zone, "early_start_enabled", enabled)

        await self.property_manager.async_set_zone_property(
            zone_id,
            CommandType.SET_EARLY_START,
            {"zone_id": zone_id, "enabled": enabled},
            self.optimistic.set_early_start,
            enabled,
            rollback_context=old_val,
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

        await self.property_manager.async_set_zone_property(
            zone_id,
            CommandType.SET_OPEN_WINDOW,
            {"zone_id": zone_id, "enabled": enabled},
            self.optimistic.set_open_window,
            enabled,
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
            capped_temp = get_capped_temperature(zone_id, float(value), self.zones_meta)
            setting["temperature"] = {"celsius": capped_temp}
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

        old_state = patch_zone_overlay(self.data.zone_states.get(str(zone_id)), data)

        self.optimistic.apply_zone_state(zone_id, overlay=True, power="ON")
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

    def _handle_overlay_side_effects(
        self,
        duration: int | None,
        overlay_mode: str | None,
        refresh_after: bool,
    ) -> None:
        """Handle side effects like expiry timers and automatic refreshes (DRY helper)."""
        # 1. Schedule Expiry Poll for Timers (This is our long-term refresh)
        if duration and duration > 0:
            self._schedule_expiry_poll(duration * 60)

        # 2. Trigger immediate Refresh ONLY if requested AND it's a permanent manual change
        # Logic: If it has a duration, next_block or presence, we don't poll immediately
        # because the cloud state is either known (timer) or unpredictable (next_block/presence).
        is_timed_overlay = bool(
            duration
            or overlay_mode
            in (OVERLAY_NEXT_BLOCK, "presence")  # Use string if const not imported
        )

        if refresh_after and not is_timed_overlay:
            self._schedule_queued_refresh()

    async def async_set_zone_overlay(
        self,
        zone_id: int,
        power: str = "ON",
        temperature: float | None = None,
        duration: int | None = None,
        overlay_type: str | None = None,
        overlay_mode: str | None = None,
        optimistic_value: bool = True,
        refresh_after: bool = False,
    ) -> None:
        """Set a manual overlay with timer/duration support."""
        # Central Validation: Check if temperature control is supported
        final_temp = temperature

        # Resolve fallback temperature if missing for ON state
        if final_temp is None and power == POWER_ON:
            zone = self.zones_meta.get(zone_id)
            ztype = (
                getattr(zone, "type", ZONE_TYPE_HEATING) if zone else ZONE_TYPE_HEATING
            )
            if ztype == ZONE_TYPE_HOT_WATER:
                final_temp = TEMP_DEFAULT_HOT_WATER
            elif ztype == ZONE_TYPE_AIR_CONDITIONING:
                final_temp = TEMP_DEFAULT_AC
            else:
                final_temp = TEMP_DEFAULT_HEATING

        if final_temp is not None and power == "ON":
            capabilities = self.data.capabilities.get(zone_id)
            if not capabilities or not capabilities.temperatures:
                _LOGGER.warning(
                    "Zone %d does not support temperature control, ignoring temperature=%s",
                    zone_id,
                    final_temp,
                )
                final_temp = None

        data = build_overlay_data(
            zone_id=zone_id,
            zones_meta=self.zones_meta,
            power=power,
            temperature=final_temp,
            duration=duration,
            overlay_type=overlay_type,
            overlay_mode=overlay_mode,
        )

        old_state = patch_zone_overlay(self.data.zone_states.get(str(zone_id)), data)

        self.optimistic.apply_zone_state(
            zone_id, optimistic_value, power=power, temperature=final_temp
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
        refresh_after: bool = False,
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
            )
        self.async_update_listeners()

        for zone_id in zone_ids:
            data = build_overlay_data(
                zone_id=zone_id,
                zones_meta=self.zones_meta,
                power=power,
                temperature=temperature,
                duration=duration,
                overlay_mode=overlay_mode,
                overlay_type=overlay_type,
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
            old_state = patch_zone_resume(self.data.zone_states.get(str(zone_id)))

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
            data = build_overlay_data(
                zone_id=zone_id,
                zones_meta=self.zones_meta,
                power=setting.get("power", POWER_ON),
                temperature=setting.get("temperature", {}).get("celsius"),
                overlay_type=setting.get("type"),
            )

            old_state = patch_zone_overlay(
                self.data.zone_states.get(str(zone_id)), data
            )

            self.optimistic.apply_zone_state(
                zone_id,
                overlay=True,
                power=setting.get("power", POWER_ON),
                temperature=setting.get("temperature", {}).get("celsius"),
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

        self.async_update_listeners()
