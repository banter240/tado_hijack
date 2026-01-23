"""Data Update Coordinator for Tado Hijack."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, cast
from zoneinfo import ZoneInfo

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
from tadoasync import Tado, TadoError

if TYPE_CHECKING:
    from tadoasync.models import Device, Zone
    from . import TadoConfigEntry
    from .helpers.client import TadoHijackClient

from .const import (
    API_RESET_BUFFER_MINUTES,
    API_RESET_HOUR,
    BOOST_MODE_TEMP,
    CONF_AUTO_API_QUOTA_PERCENT,
    CONF_DEBOUNCE_TIME,
    CONF_DISABLE_POLLING_WHEN_THROTTLED,
    CONF_OFFSET_POLL_INTERVAL,
    CONF_SLOW_POLL_INTERVAL,
    CONF_THROTTLE_THRESHOLD,
    DEFAULT_AUTO_API_QUOTA_PERCENT,
    DEFAULT_DEBOUNCE_TIME,
    DEFAULT_OFFSET_POLL_INTERVAL,
    DEFAULT_SLOW_POLL_INTERVAL,
    DEFAULT_THROTTLE_THRESHOLD,
    DOMAIN,
)
from .helpers.api_manager import TadoApiManager
from .helpers.auth_manager import AuthManager
from .helpers.data_manager import TadoDataManager
from .helpers.device_linker import get_climate_entity_id
from .helpers.logging_utils import get_redacted_logger
from .helpers.optimistic_manager import OptimisticManager
from .helpers.patch import get_handler
from .helpers.rate_limit_manager import RateLimitManager
from .models import CommandType, RateLimit, TadoCommand, TadoCoordinatorData

_LOGGER = get_redacted_logger(__name__)


class TadoDataUpdateCoordinator(DataUpdateCoordinator):
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
        self._base_scan_interval = scan_interval  # Store original interval

        self.rate_limit = RateLimitManager(throttle_threshold, get_handler())
        self.auth_manager = AuthManager(hass, entry, client)

        slow_poll_s = (
            entry.data.get(CONF_SLOW_POLL_INTERVAL, DEFAULT_SLOW_POLL_INTERVAL) * 3600
        )
        offset_poll_s = (
            entry.data.get(CONF_OFFSET_POLL_INTERVAL, DEFAULT_OFFSET_POLL_INTERVAL)
            * 3600
        )
        self.data_manager = TadoDataManager(self, client, slow_poll_s, offset_poll_s)
        self.api_manager = TadoApiManager(hass, self, self._debounce_time)
        self.optimistic = OptimisticManager()

        self.zones_meta: dict[int, Zone] = {}
        self.devices_meta: dict[str, Device] = {}
        self.bridges: list[Device] = []
        self._climate_to_zone: dict[str, int] = {}
        self._unsub_listener: CALLBACK_TYPE | None = None
        self._reset_poll_unsub: CALLBACK_TYPE | None = None
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
                if zone_id := self._climate_to_zone.get(eid):
                    if is_auto_mode:
                        # AUTO mode = Resume Schedule
                        _LOGGER.debug(
                            "Intercepted AUTO mode on HomeKit climate %s. Resuming schedule for zone %d.",
                            eid,
                            zone_id,
                        )
                        # Schedule resume (async call handled by coordinator)
                        self.hass.async_create_task(self.async_resume_schedule(zone_id))
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
            if zone.type != "HEATING":
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
        # 1. Check HomeKit mapping
        if zone_id := self._climate_to_zone.get(entity_id):
            return zone_id

        # 2. Check Hijack registry
        from homeassistant.helpers import entity_registry as er

        ent_reg = er.async_get(self.hass)
        if entry := ent_reg.async_get(entity_id):
            return self._parse_zone_id_from_unique_id(entry.unique_id)

        return None

    def _parse_zone_id_from_unique_id(self, unique_id: str) -> int | None:
        """Extract zone ID from unique_id with support for multiple formats.

        Supported formats:
        - {entry_id}_hw_{zone_id}     (hot water switch)
        - {entry_id}_sch_{zone_id}    (schedule switch)
        - {entry_id}_.._{zone_id}     (any suffix ending in zone_id)
        - zone_{zone_id}_...          (zone entities like target_temp)
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

    async def _async_update_data(self) -> TadoCoordinatorData:
        """Fetch update via DataManager.

        Handles throttling logic by skipping API calls if quota is low and
        the feature is enabled.
        """
        # 1. Check if polling should be disabled when throttled
        # We allow the fetch if it's forced (reset poll) or no data exists yet
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
                return cast(TadoCoordinatorData, self.data)

            # If no data exists yet, allow first fetch
            _LOGGER.info("No data exists, allowing initial fetch despite throttling")

        # Reset force flag
        self._force_next_update = False

        try:
            # 2. Capture starting quota to measure actual poll cost
            quota_start = self.rate_limit.remaining

            # 3. Execute full data fetch
            data = await self.data_manager.fetch_full_update()

            # 4. Synchronize metadata
            self.zones_meta = self.data_manager.zones_meta
            self.devices_meta = self.data_manager.devices_meta
            self._update_climate_map()

            # 5. Maintenance tasks
            self.auth_manager.check_and_update_token()
            self.optimistic.cleanup()

            # 6. Rate limit tracking & cost measurement
            self.rate_limit.sync_from_headers()

            # Measure exactly how many calls this poll used
            actual_cost = quota_start - self.rate_limit.remaining
            if actual_cost > 0:
                self.rate_limit.last_poll_cost = float(actual_cost)

            data["rate_limit"] = RateLimit(
                limit=self.rate_limit.limit,
                remaining=self.rate_limit.remaining,
            )
            data["api_status"] = self.rate_limit.api_status

            # 7. Auto API Quota: Adjust polling interval dynamically
            self._adjust_interval_for_auto_quota()

            return cast(TadoCoordinatorData, data)
        except TadoError as err:
            raise UpdateFailed(f"Tado API error: {err}") from err

    def _get_next_reset_time(self) -> datetime:
        """Calculate next API quota reset time (12:01 CET with buffer)."""
        berlin_tz = ZoneInfo("Europe/Berlin")
        now = datetime.now(berlin_tz)

        # Reset happens at API_RESET_HOUR:API_RESET_BUFFER_MINUTES
        reset_today = now.replace(
            hour=API_RESET_HOUR,
            minute=API_RESET_BUFFER_MINUTES,
            second=0,
            microsecond=0,
        )

        # If we are within 5 minutes of today's reset or already past it,
        # the NEXT reset is tomorrow.
        if now >= (reset_today - timedelta(minutes=5)):
            return reset_today + timedelta(days=1)

        return reset_today

    def _calculate_auto_quota_interval(self) -> int | None:
        """Calculate optimal polling interval based on quota settings.

        Respects throttle threshold - if enabled and remaining calls drop below
        threshold, polling is disabled or slowed significantly regardless of
        auto quota settings.

        Returns:
            Interval in seconds, or None if auto quota is disabled

        """
        if self._auto_api_quota_percent <= 0:
            return None

        limit = self.rate_limit.limit
        remaining = self.rate_limit.remaining

        if limit <= 0:
            _LOGGER.warning("API limit is 0, cannot calculate interval")
            return None

        # Calculate time until next reset
        next_reset = self._get_next_reset_time()
        now = datetime.now(ZoneInfo("Europe/Berlin"))
        seconds_until_reset = int((next_reset - now).total_seconds())

        # Throttling has absolute priority
        if self.rate_limit.is_throttled:
            if self._disable_polling_when_throttled:
                _LOGGER.warning(
                    "Throttled (remaining=%d < threshold=%d). Polling suspended until %s.",
                    remaining,
                    self.rate_limit.throttle_threshold,
                    next_reset.strftime("%H:%M"),
                )
                return max(3600, seconds_until_reset)

            _LOGGER.warning(
                "Throttled (remaining=%d < threshold=%d). Slowing to 1h.",
                remaining,
                self.rate_limit.throttle_threshold,
            )
            return 3600

        # Calculate FREE quota after all reservations
        # 1. Throttle threshold (emergency reserve)
        # 2. Scheduled updates (slow poll, offset poll) - measured, not hardcoded
        throttle_threshold = self.rate_limit.throttle_threshold
        reserved_daily, reserved_breakdown = (
            self.data_manager.estimate_daily_reserved_cost()
        )

        # FREE QUOTA = Limit - Throttle Reserve - Scheduled Updates
        free_quota = max(0, limit - throttle_threshold - reserved_daily)

        # Target = X% of FREE quota (not total!)
        target_api_calls = int(free_quota * self._auto_api_quota_percent / 100)

        _LOGGER.debug(
            "Quota breakdown: Limit=%d, Throttle=%d, Reserved=%d (slow=%d, offset=%d), Free=%d, Target=%d%%=%d",
            limit,
            throttle_threshold,
            reserved_daily,
            reserved_breakdown.get("slow_poll_total", 0),
            reserved_breakdown.get("offset_poll_total", 0),
            free_quota,
            self._auto_api_quota_percent,
            target_api_calls,
        )

        # Total calls used so far today
        used_total_calls = max(0, limit - remaining)

        # HYBRID STRATEGY: Use the more generous of two approaches
        # Strategy A: Long-term daily budget planning
        budget_from_target = max(0, target_api_calls - used_total_calls)

        # Strategy B: Short-term remaining-based fallback
        usable_remaining = max(0, remaining - throttle_threshold)
        budget_from_remaining = int(
            usable_remaining * self._auto_api_quota_percent / 100
        )

        # Use MAX to ensure system continues polling even when over daily budget
        # This prevents self-throttling when low on quota (e.g., 100 remaining)
        remaining_budget = max(budget_from_target, budget_from_remaining)

        _LOGGER.debug(
            "Quota breakdown: Limit=%d, Throttle=%d, Target=%d, Used=%d, BudgetTarget=%d, BudgetRemaining=%d, FinalBudget=%d",
            limit,
            throttle_threshold,
            target_api_calls,
            used_total_calls,
            budget_from_target,
            budget_from_remaining,
            remaining_budget,
        )

        if remaining_budget <= 0:
            # Budget exhausted - return to base interval or stop if base is 0
            if self._base_scan_interval <= 0:
                _LOGGER.info(
                    "Budget reached (%d/%d used). Stopping polling.",
                    used_total_calls,
                    target_api_calls,
                )
                return None

            new_interval = max(15, int(self._base_scan_interval))
            _LOGGER.info(
                "Budget reached (%d/%d used). Falling back to base interval (%ds).",
                used_total_calls,
                target_api_calls,
                new_interval,
            )
            return new_interval

        # Calculate interval based on predicted cost of the upcoming poll
        predicted_cost = self.data_manager.predict_next_poll_cost()

        # How many polls of this predicted size can we afford?
        remaining_polls = remaining_budget / predicted_cost

        if remaining_polls <= 0:
            return 3600

        # Adaptive interval calculation with 15s safety floor
        adaptive_interval = seconds_until_reset / remaining_polls
        bounded_interval = int(max(15, min(3600, adaptive_interval)))

        _LOGGER.info(
            "Quota: Interval=%ds (Budget: %d/%d used, Next Cost: %d, Rem: %d calls -> %d polls, Reset in %.1fh)",
            bounded_interval,
            used_total_calls,
            target_api_calls,
            predicted_cost,
            remaining_budget,
            int(remaining_polls),
            seconds_until_reset / 3600,
        )

        return bounded_interval

    def _adjust_interval_for_auto_quota(self) -> None:
        """Adjust update interval based on auto API quota percentage."""
        calculated_interval = self._calculate_auto_quota_interval()

        if calculated_interval is None:
            # Fallback to base interval if auto quota is inactive
            self.update_interval = (
                timedelta(seconds=self._base_scan_interval)
                if self._base_scan_interval > 0
                else None
            )
        else:
            self.update_interval = timedelta(seconds=calculated_interval)

    def _schedule_reset_poll(self) -> None:
        """Schedule automatic poll at daily quota reset time."""
        if self._auto_api_quota_percent <= 0:
            return

        next_reset = self._get_next_reset_time()
        now = datetime.now(ZoneInfo("Europe/Berlin"))
        delay = (next_reset - now).total_seconds()

        _LOGGER.debug(
            "Quota: Scheduling reset poll at %s (in %.1f hours)",
            next_reset.strftime("%Y-%m-%d %H:%M:%S %Z"),
            delay / 3600,
        )

        # Cancel existing timer
        if self._reset_poll_unsub:
            self._reset_poll_unsub()

        # Schedule new timer
        self._reset_poll_unsub = self.hass.loop.call_later(
            delay, lambda: self.hass.async_create_task(self._on_reset_poll())
        )

    async def _on_reset_poll(self) -> None:
        """Execute automatic poll at quota reset time."""
        _LOGGER.info("Quota: Executing scheduled reset poll to fetch fresh quota")

        # Set force flag to ensure this poll bypasses any throttling blocks
        self._force_next_update = True

        # Trigger refresh to get updated quota info
        await self.async_refresh()

        # Schedule next reset poll
        self._schedule_reset_poll()

    def shutdown(self) -> None:
        """Cleanup listeners and tasks."""
        if self._unsub_listener:
            self._unsub_listener()
            self._unsub_listener = None

        if self._reset_poll_unsub:
            self._reset_poll_unsub.cancel()
            self._reset_poll_unsub = None

        # Cleanup API manager (worker task + pending timers)
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
        self.data["rate_limit"] = RateLimit(
            limit=self.rate_limit.limit,
            remaining=self.rate_limit.remaining,
        )
        self.data["api_status"] = self.rate_limit.api_status
        if not silent:
            self.async_update_listeners()

    async def async_sync_states(self, types: list[str]) -> None:
        """Targeted refresh after worker actions."""
        if "presence" in types:
            self.data["home_state"] = await self._tado.get_home_state()
        if "zone" in types:
            self.data["zone_states"] = await self._tado.get_zone_states()

        self.update_rate_limit_local(silent=False)

    async def async_set_zone_auto(self, zone_id: int):
        """Set zone to auto mode."""
        self.optimistic.set_zone(zone_id, False)
        self.async_update_listeners()
        self.api_manager.queue_command(
            f"zone_{zone_id}",
            TadoCommand(CommandType.RESUME_SCHEDULE, zone_id=zone_id),
        )

    async def async_set_zone_heat(self, zone_id: int, temp: float = 25.0):
        """Set zone to manual mode with temperature."""
        zone = self.zones_meta.get(zone_id)
        overlay_type = getattr(zone, "type", "HEATING") if zone else "HEATING"

        self.optimistic.set_zone(zone_id, True)
        self.async_update_listeners()
        self.api_manager.queue_command(
            f"zone_{zone_id}",
            TadoCommand(
                CommandType.SET_OVERLAY,
                zone_id=zone_id,
                data={
                    "setting": {
                        "type": overlay_type,
                        "power": "ON",
                        "temperature": {"celsius": temp},
                    },
                    "termination": {"typeSkillBasedApp": "MANUAL"},
                },
            ),
        )

    async def async_set_presence_debounced(self, presence: str):
        """Set presence state."""
        self.optimistic.set_presence(presence)
        self.async_update_listeners()
        self.api_manager.queue_command(
            "presence",
            TadoCommand(CommandType.SET_PRESENCE, data={"presence": presence}),
        )

    async def async_set_child_lock(self, serial_no: str, enabled: bool) -> None:
        """Set child lock for a device."""
        self.optimistic.set_child_lock(serial_no, enabled)
        self.async_update_listeners()
        self.api_manager.queue_command(
            f"child_lock_{serial_no}",
            TadoCommand(
                CommandType.SET_CHILD_LOCK,
                data={"serial": serial_no, "enabled": enabled},
            ),
        )

    async def async_set_temperature_offset(self, serial_no: str, offset: float) -> None:
        """Set temperature offset for a device."""
        self.optimistic.set_offset(serial_no, offset)
        self.async_update_listeners()
        self.api_manager.queue_command(
            f"offset_{serial_no}",
            TadoCommand(
                CommandType.SET_OFFSET,
                data={"serial": serial_no, "offset": offset},
            ),
        )

    async def async_set_away_temperature(self, zone_id: int, temp: float) -> None:
        """Set away temperature for a zone."""
        self.optimistic.set_away_temp(zone_id, temp)
        self.async_update_listeners()
        self.api_manager.queue_command(
            f"away_temp_{zone_id}",
            TadoCommand(
                CommandType.SET_AWAY_TEMP,
                data={"zone_id": zone_id, "temp": temp},
            ),
        )

    async def async_set_hot_water_power(self, zone_id: int, on: bool) -> None:
        """Set hot water power state."""
        self.optimistic.set_zone(zone_id, True, power="ON" if on else "OFF")
        self.async_update_listeners()
        self.api_manager.queue_command(
            f"zone_{zone_id}",
            TadoCommand(
                CommandType.SET_OVERLAY,
                zone_id=zone_id,
                data={
                    "setting": {"type": "HOT_WATER", "power": "ON" if on else "OFF"},
                    "termination": {"typeSkillBasedApp": "MANUAL"},
                },
            ),
        )

    async def async_set_dazzle_mode(self, zone_id: int, enabled: bool) -> None:
        """Set dazzle mode for a zone."""
        self.optimistic.set_dazzle(zone_id, enabled)
        self.async_update_listeners()
        self.api_manager.queue_command(
            f"dazzle_{zone_id}",
            TadoCommand(
                CommandType.SET_DAZZLE,
                data={"zone_id": zone_id, "enabled": enabled},
            ),
        )

    async def async_set_early_start(self, zone_id: int, enabled: bool) -> None:
        """Set early start for a zone."""
        self.optimistic.set_early_start(zone_id, enabled)
        self.async_update_listeners()
        self.api_manager.queue_command(
            f"early_start_{zone_id}",
            TadoCommand(
                CommandType.SET_EARLY_START,
                data={"zone_id": zone_id, "enabled": enabled},
            ),
        )

    async def async_set_open_window_detection(
        self, zone_id: int, enabled: bool
    ) -> None:
        """Set open window detection for a zone."""
        self.optimistic.set_open_window(zone_id, enabled)
        self.async_update_listeners()
        self.api_manager.queue_command(
            f"open_window_{zone_id}",
            TadoCommand(
                CommandType.SET_OPEN_WINDOW,
                data={"zone_id": zone_id, "enabled": enabled},
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

    async def async_set_ac_setting(self, zone_id: int, key: str, value: str) -> None:
        """Set an AC specific setting (fan speed, swing, temperature, etc.)."""
        state = self.data.get("zone_states", {}).get(str(zone_id))
        if not state or not state.setting:
            _LOGGER.error("Cannot set AC setting: No state for zone %d", zone_id)
            return

        # Map internal keys to API keys
        api_key_map = {
            "fan_speed": "fanSpeed",
            "vertical_swing": "verticalSwing",
            "horizontal_swing": "horizontalSwing",
            "swing": "swing",
        }

        # Build combined setting from current state
        setting = {
            "type": state.setting.type,
            "power": "ON",  # Ensure power is ON when setting values
            "mode": state.setting.mode,
            api_key_map.get("fan_speed"): state.setting.fan_speed,
            api_key_map.get("vertical_swing"): state.setting.vertical_swing,
            api_key_map.get("horizontal_swing"): state.setting.horizontal_swing,
            api_key_map.get("swing"): state.setting.swing,
        }

        if key == "temperature":
            setting["temperature"] = {"celsius": float(value)}
        elif state.setting.temperature:
            setting["temperature"] = {"celsius": state.setting.temperature.celsius}

        # Override the changed value (if it's not temperature)
        if key != "temperature":
            setting[api_key_map.get(key, key)] = value

        # Optimistic Update: Setting a value implies Manual Mode (Overlay) and Power ON
        self.optimistic.set_zone(zone_id, True, power="ON")
        self.async_update_listeners()

        self.api_manager.queue_command(
            f"zone_{zone_id}",
            TadoCommand(
                CommandType.SET_OVERLAY,
                zone_id=zone_id,
                data={
                    "setting": {k: v for k, v in setting.items() if v is not None},
                    "termination": {"typeSkillBasedApp": "MANUAL"},
                },
            ),
        )

    async def async_set_zone_overlay(
        self,
        zone_id: int,
        power: str = "ON",
        temperature: float | None = None,
        duration: int | None = None,
        overlay_type: str | None = None,
        optimistic_value: bool = True,
    ) -> None:
        """Set a manual overlay with timer/duration support."""
        data = self._build_overlay_data(
            zone_id=zone_id,
            power=power,
            temperature=temperature,
            duration=duration,
            overlay_type=overlay_type,
        )

        # Optimistic Update
        self.optimistic.set_zone(zone_id, optimistic_value, power=power)
        self.async_update_listeners()

        # Queue Command
        self.api_manager.queue_command(
            f"zone_{zone_id}",
            TadoCommand(
                CommandType.SET_OVERLAY,
                zone_id=zone_id,
                data=data,
            ),
        )

    def _build_overlay_data(
        self,
        zone_id: int,
        power: str = "ON",
        temperature: float | None = None,
        duration: int | None = None,
        overlay_type: str | None = None,
        overlay_mode: str | None = None,
    ) -> dict[str, Any]:
        """Build the overlay data dictionary (DRY helper).

        Args:
            zone_id: Zone ID
            power: Power state (ON/OFF)
            temperature: Target temperature (optional)
            duration: Duration in minutes (optional)
            overlay_type: Zone type (HEATING/AIR_CONDITIONING/HOT_WATER)
            overlay_mode: Termination mode - "manual", "timer", or "auto" (next_time_block)

        """
        # 1. Determine Type
        if not overlay_type:
            zone = self.zones_meta.get(zone_id)
            overlay_type = getattr(zone, "type", "HEATING") if zone else "HEATING"

        # 2. Build Termination
        # Priority: overlay_mode > duration > default (MANUAL)
        if overlay_mode == "auto":
            # Auto-return to schedule at next time block
            termination: dict[str, Any] = {"type": "NEXT_TIME_BLOCK"}
        elif overlay_mode == "presence":
            # While in current Presence Mode (indefinite until presence change or manual change)
            termination = {"type": "TADO_MODE"}
        elif overlay_mode == "timer" or duration:
            # Timer with specific duration
            duration_seconds = duration * 60 if duration else 1800  # Default 30min
            termination = {
                "typeSkillBasedApp": "TIMER",
                "durationInSeconds": duration_seconds,
            }
        else:
            # Manual (indefinite until user changes)
            termination = {"typeSkillBasedApp": "MANUAL"}

        # 3. Build Setting
        setting: dict[str, Any] = {"type": overlay_type, "power": power}
        if temperature is not None and power == "ON":
            setting["temperature"] = {"celsius": temperature}

        return {"setting": setting, "termination": termination}

    async def async_set_multiple_zone_overlays(
        self,
        zone_ids: list[int],
        power: str = "ON",
        temperature: float | None = None,
        duration: int | None = None,
        overlay_mode: str | None = None,
    ) -> None:
        """Set manual overlays for multiple zones in a single batched process.

        Args:
            zone_ids: List of zone IDs to set
            power: Power state (ON/OFF)
            temperature: Target temperature (optional)
            duration: Duration in minutes (optional)
            overlay_mode: "manual", "timer", or "auto" (next_time_block)

        """
        if not zone_ids:
            return

        _LOGGER.debug(
            "Batched set_timer requested for zones: %s (mode: %s)",
            zone_ids,
            overlay_mode or "default",
        )

        # 1. Trigger Optimistic Updates for all zones
        for zone_id in zone_ids:
            self.optimistic.set_zone(zone_id, True, power=power)
        self.async_update_listeners()

        # 2. Queue Commands
        # The ApiManager will automatically merge these because they are queued
        # in the same execution cycle (before the debounce timer expires).
        for zone_id in zone_ids:
            data = self._build_overlay_data(
                zone_id=zone_id,
                power=power,
                temperature=temperature,
                duration=duration,
                overlay_mode=overlay_mode,
            )
            self.api_manager.queue_command(
                f"zone_{zone_id}",
                TadoCommand(
                    CommandType.SET_OVERLAY,
                    zone_id=zone_id,
                    data=data,
                ),
            )

    async def async_resume_all_schedules(self) -> None:
        """Resume all zone schedules using bulk API endpoint (single call)."""
        _LOGGER.debug("Resume all schedules triggered")

        if not self.zones_meta:
            _LOGGER.warning("No zones to resume")
            return

        active_zones = [
            zid for zid in self.zones_meta if not self._is_zone_disabled(zid)
        ]

        if not active_zones:
            _LOGGER.warning("All zones are disabled, skipping resume")
            return

        for zone_id in active_zones:
            self.optimistic.set_zone(zone_id, None)
        self.async_update_listeners()

        _LOGGER.info("Queued resume schedules for %d active zones", len(active_zones))

        # Send individual commands. The ApiManager is smart enough to batch them into one call!
        for zone_id in active_zones:
            self.api_manager.queue_command(
                f"zone_{zone_id}",
                TadoCommand(CommandType.RESUME_SCHEDULE, zone_id=zone_id),
            )

    async def async_turn_off_all_zones(self) -> None:
        """Turn off all heating zones using bulk API endpoint."""
        _LOGGER.debug("Turn off all zones triggered")
        self._apply_bulk_zone_overlay(
            command_key="turn_off_all",
            setting={"power": "OFF", "type": "HEATING"},
            action_name="turn off",
        )

    async def async_boost_all_zones(self) -> None:
        """Boost all heating zones (25C) via bulk API."""
        _LOGGER.debug("Boost all zones triggered")
        self._apply_bulk_zone_overlay(
            command_key="boost_all",
            setting={
                "power": "ON",
                "type": "HEATING",
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
        """Apply same overlay setting to all heating zones (DRY helper).

        Args:
            command_key: Unique key for API command queue
            setting: Overlay setting dict (power, type, temperature)
            action_name: Human-readable action name for logging

        """
        if not self.zones_meta:
            _LOGGER.warning("No zones to %s", action_name)
            return

        zone_ids = [
            zone_id
            for zone_id, zone in self.zones_meta.items()
            if getattr(zone, "type", "HEATING") == "HEATING"
            and not self._is_zone_disabled(zone_id)
        ]

        if not zone_ids:
            _LOGGER.warning("No active heating zones to %s", action_name)
            return

        # Optimistic update (UI Feedback)
        for zone_id in zone_ids:
            self.optimistic.set_zone(zone_id, True)
        self.async_update_listeners()

        _LOGGER.info("Queued %s for %d active zones", action_name, len(zone_ids))

        for zone_id in zone_ids:
            self.api_manager.queue_command(
                f"zone_{zone_id}",
                TadoCommand(
                    CommandType.SET_OVERLAY,
                    zone_id=zone_id,
                    data={
                        "setting": setting,
                        "termination": {"typeSkillBasedApp": "MANUAL"},
                    },
                ),
            )
