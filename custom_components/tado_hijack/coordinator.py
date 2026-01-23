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

        self.api_manager.start(entry)
        self._setup_event_listener()

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

            for eid in entity_ids:
                if zone_id := self._climate_to_zone.get(eid):
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
        """Extract zone ID from unique_id with support for multiple formats."""
        try:
            parts = unique_id.split("_")
            # Pattern: {entry_id}_..._{zone_id}
            if parts[-1].isdigit():
                return int(parts[-1])
            # Pattern: zone_{zone_id}
            if len(parts) >= 2 and parts[-2] == "zone" and parts[-1].isdigit():
                return int(parts[-1])
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
        if self._disable_polling_when_throttled and self.rate_limit.is_throttled:
            _LOGGER.warning(
                "Polling disabled due to throttling (remaining: %d, threshold: %d)",
                self.rate_limit.remaining,
                self.rate_limit.throttle_threshold,
            )
            # Return existing data without making new API calls
            if self.data:
                return cast(TadoCoordinatorData, self.data)
            # If no data exists yet, allow first fetch
            _LOGGER.info("No data exists, allowing initial fetch despite throttling")

        try:
            # 2. Execute full data fetch
            data = await self.data_manager.fetch_full_update()

            # 3. Synchronize metadata
            self.zones_meta = self.data_manager.zones_meta
            self.devices_meta = self.data_manager.devices_meta
            self._update_climate_map()

            # 4. Maintenance tasks
            self.auth_manager.check_and_update_token()
            self.optimistic.cleanup()

            # 5. Rate limit tracking
            self.rate_limit.sync_from_headers()

            data["rate_limit"] = RateLimit(
                limit=self.rate_limit.limit,
                remaining=self.rate_limit.remaining,
            )
            data["api_status"] = self.rate_limit.api_status

            # 6. Auto API Quota: Adjust polling interval dynamically
            self._adjust_interval_for_auto_quota()

            return cast(TadoCoordinatorData, data)
        except TadoError as err:
            raise UpdateFailed(f"Tado API error: {err}") from err

    def _adjust_interval_for_auto_quota(self) -> None:
        """Adjust update interval based on auto API quota percentage.

        When auto_api_quota_percent > 0, dynamically calculates the optimal
        polling interval to use exactly X% of the daily API quota, distributed
        evenly until the next reset at 12:00 noon Berlin time.
        """
        if self._auto_api_quota_percent <= 0:
            # Auto quota disabled, use base interval
            if self._base_scan_interval > 0:
                self.update_interval = timedelta(seconds=self._base_scan_interval)
            else:
                self.update_interval = None
            return

        # Get current quota information
        limit = self.rate_limit.limit
        remaining = self.rate_limit.remaining

        if limit <= 0:
            _LOGGER.warning("Auto quota: API limit is 0, cannot calculate interval")
            return

        # Calculate time until next reset (12:00 noon Berlin time)
        berlin_tz = ZoneInfo("Europe/Berlin")
        now = datetime.now(berlin_tz)

        # Next reset is at 12:00 noon today or tomorrow
        next_reset = now.replace(hour=12, minute=0, second=0, microsecond=0)
        if now >= next_reset:
            # Reset already happened today, next reset is tomorrow
            next_reset = next_reset + timedelta(days=1)

        seconds_until_reset = (next_reset - now).total_seconds()

        # Calculate target quota for the day
        target_quota = int(limit * self._auto_api_quota_percent / 100)

        # Calculate how many calls we've already used since last reset
        used_calls = limit - remaining

        # Calculate remaining calls we want to make until reset
        remaining_target_calls = max(0, target_quota - used_calls)

        if remaining_target_calls <= 0:
            # We've already reached our quota target, slow down significantly
            # Use a very long interval (e.g., seconds until reset)
            new_interval_seconds = max(3600, seconds_until_reset)
            _LOGGER.info(
                "Auto quota: Target reached (%d%% of %d = %d calls). "
                "Slowing down polling to %d seconds",
                self._auto_api_quota_percent,
                limit,
                target_quota,
                int(new_interval_seconds),
            )
        else:
            # Calculate optimal interval to spread remaining calls evenly
            new_interval_seconds = seconds_until_reset / remaining_target_calls

            # Apply reasonable bounds (min 30s, max 1 hour)
            new_interval_seconds = max(30, min(3600, new_interval_seconds))

            _LOGGER.info(
                "Auto quota: Adjusting interval to %d seconds "
                "(target: %d%% of %d = %d calls, used: %d, remaining target: %d, "
                "time until reset: %.1f hours)",
                int(new_interval_seconds),
                self._auto_api_quota_percent,
                limit,
                target_quota,
                used_calls,
                remaining_target_calls,
                seconds_until_reset / 3600,
            )

        self.update_interval = timedelta(seconds=new_interval_seconds)

    def shutdown(self) -> None:
        """Cleanup listeners and tasks."""
        if self._unsub_listener:
            self._unsub_listener()
            self._unsub_listener = None

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
        self.optimistic.set_zone(zone_id, not on)
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
        self.optimistic.set_zone(zone_id, optimistic_value)
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
    ) -> dict[str, Any]:
        """Build the overlay data dictionary (DRY helper)."""
        # 1. Determine Type
        if not overlay_type:
            zone = self.zones_meta.get(zone_id)
            overlay_type = getattr(zone, "type", "HEATING") if zone else "HEATING"

        # 2. Build Termination
        termination: dict[str, Any] = {"typeSkillBasedApp": "MANUAL"}
        if duration:
            termination = {
                "typeSkillBasedApp": "TIMER",
                "durationInSeconds": duration * 60,
            }

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
    ) -> None:
        """Set manual overlays for multiple zones in a single batched process."""
        if not zone_ids:
            return

        _LOGGER.debug("Batched set_timer requested for zones: %s", zone_ids)

        # 1. Trigger Optimistic Updates for all zones
        for zone_id in zone_ids:
            self.optimistic.set_zone(zone_id, True)
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
