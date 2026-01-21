"""Data Update Coordinator for Tado Hijack."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from tadoasync import Tado, TadoError

if TYPE_CHECKING:
    from tadoasync.models import Device, Zone
    from . import TadoConfigEntry
    from .helpers.client import TadoHijackClient

from .const import (
    BOOST_MODE_TEMP,
    CONF_DEBOUNCE_TIME,
    CONF_DISABLE_POLLING_WHEN_THROTTLED,
    CONF_OFFSET_POLL_INTERVAL,
    CONF_SLOW_POLL_INTERVAL,
    CONF_THROTTLE_THRESHOLD,
    DEFAULT_DEBOUNCE_TIME,
    DEFAULT_OFFSET_POLL_INTERVAL,
    DEFAULT_SLOW_POLL_INTERVAL,
    DEFAULT_THROTTLE_THRESHOLD,
    DOMAIN,
)
from .helpers.api_manager import TadoApiManager
from .helpers.auth_manager import AuthManager
from .helpers.data_manager import TadoDataManager
from .helpers.logging_utils import get_redacted_logger
from .helpers.optimistic_manager import OptimisticManager
from .helpers.patch import get_handler
from .helpers.rate_limit_manager import RateLimitManager
from .models import CommandType, RateLimit, TadoCommand

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

        self.api_manager.start(entry)

    @property
    def client(self) -> TadoHijackClient:
        """Return the Tado client."""
        return cast("TadoHijackClient", self._tado)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch update via DataManager."""
        try:
            data = await self.data_manager.fetch_full_update()

            self.zones_meta = self.data_manager.zones_meta
            self.devices_meta = self.data_manager.devices_meta

            self.auth_manager.check_and_update_token()

            self.optimistic.cleanup()

            self.rate_limit.sync_from_headers()

            data["rate_limit"] = RateLimit(
                limit=self.rate_limit.limit,
                remaining=self.rate_limit.remaining,
            )
            data["api_status"] = self.rate_limit.api_status
            return data
        except TadoError as err:
            raise UpdateFailed(f"Tado API error: {err}") from err

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
        """Set zone to manual heat mode."""
        self.optimistic.set_zone(zone_id, True)
        self.async_update_listeners()
        self.api_manager.queue_command(
            f"zone_{zone_id}",
            TadoCommand(
                CommandType.SET_OVERLAY,
                zone_id=zone_id,
                data={
                    "setting": {
                        "type": "HEATING",
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

    async def async_set_ac_setting(self, zone_id: int, key: str, value: str) -> None:
        """Set an AC specific setting (fan speed, swing, etc.)."""
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
            "power": state.setting.power,
            "mode": state.setting.mode,
            api_key_map.get("fan_speed"): state.setting.fan_speed,
            api_key_map.get("vertical_swing"): state.setting.vertical_swing,
            api_key_map.get("horizontal_swing"): state.setting.horizontal_swing,
            api_key_map.get("swing"): state.setting.swing,
        }
        if state.setting.temperature:
            setting["temperature"] = {"celsius": state.setting.temperature.celsius}

        # Override the changed value
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

    async def async_resume_all_schedules(self) -> None:
        """Resume all zone schedules using bulk API endpoint (single call)."""
        _LOGGER.debug("Resume all schedules triggered")

        if not self.zones_meta:
            _LOGGER.warning("No zones to resume")
            return

        for zone_id in self.zones_meta:
            self.optimistic.set_zone(zone_id, None)
        self.async_update_listeners()

        _LOGGER.info("Queued resume schedules for all %d zones", len(self.zones_meta))

        self.api_manager.queue_command(
            "resume_all",
            TadoCommand(CommandType.RESUME_SCHEDULE, zone_id=None),
        )

    async def async_turn_off_all_zones(self) -> None:
        """Turn off all heating zones using bulk API endpoint."""
        _LOGGER.debug("Turn off all zones triggered")
        if not self.zones_meta:
            _LOGGER.warning("No zones to turn off")
            return

        overlays = [
            {
                "overlay": {
                    "setting": {"power": "OFF", "type": "HEATING"},
                    "termination": {"typeSkillBasedApp": "MANUAL"},
                },
                "room": zone_id,
            }
            for zone_id, zone in self.zones_meta.items()
            if getattr(zone, "type", "HEATING") == "HEATING"
        ]
        if not overlays:
            return

        # Optimistic update (UI Feedback)
        for item in overlays:
            self.optimistic.set_zone(cast(int, item["room"]), True)
        self.async_update_listeners()

        _LOGGER.info("Queued turn off for %d zones", len(overlays))

        self.api_manager.queue_command(
            "turn_off_all",
            TadoCommand(
                CommandType.SET_OVERLAY,
                zone_id=None,
                data={
                    "setting": {"power": "OFF", "type": "HEATING"},
                    "termination": {"typeSkillBasedApp": "MANUAL"},
                },
            ),
        )

    async def async_boost_all_zones(self) -> None:
        """Boost all heating zones (25C) via bulk API."""
        _LOGGER.debug("Boost all zones triggered")
        if not self.zones_meta:
            _LOGGER.warning("No zones to boost")
            return

        overlays = [
            {
                "overlay": {
                    "setting": {
                        "power": "ON",
                        "type": "HEATING",
                        "temperature": {"celsius": BOOST_MODE_TEMP},
                    },
                    "termination": {"typeSkillBasedApp": "MANUAL"},
                },
                "room": zone_id,
            }
            for zone_id, zone in self.zones_meta.items()
            if getattr(zone, "type", "HEATING") == "HEATING"
        ]
        if not overlays:
            return

        # Optimistic update (UI Feedback)
        for item in overlays:
            self.optimistic.set_zone(cast(int, item["room"]), True)
        self.async_update_listeners()

        _LOGGER.info("Queued boost for %d zones", len(overlays))

        self.api_manager.queue_command(
            "boost_all",
            TadoCommand(
                CommandType.SET_OVERLAY,
                zone_id=None,
                data={
                    "setting": {
                        "power": "ON",
                        "type": "HEATING",
                        "temperature": {"celsius": BOOST_MODE_TEMP},
                    },
                    "termination": {"typeSkillBasedApp": "MANUAL"},
                },
            ),
        )
