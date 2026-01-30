"""Manages prioritized and debounced API access for Tado Hijack."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HassJob, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later

from ..const import (
    BATCH_LINGER_S,
    CONF_API_PROXY_URL,
    CONF_CALL_JITTER_ENABLED,
    CONF_JITTER_PERCENT,
    DEFAULT_JITTER_PERCENT,
)
from ..models import CommandType, TadoCommand
from .command_merger import CommandMerger
from .logging_utils import get_redacted_logger
from .utils import apply_jitter

if TYPE_CHECKING:
    from ..coordinator import TadoDataUpdateCoordinator

_LOGGER = get_redacted_logger(__name__)


class TadoApiManager:
    """Handles queuing, debouncing and sequential execution of API commands."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: TadoDataUpdateCoordinator,
        debounce_time: int,
    ) -> None:
        """Initialize Tado API manager."""
        self.hass = hass
        self.coordinator = coordinator
        self._debounce_time = debounce_time
        self._api_queue: asyncio.Queue[TadoCommand] = asyncio.Queue()
        self._action_queue: dict[str, TadoCommand] = {}
        self._pending_timers: dict[str, CALLBACK_TYPE] = {}
        self._worker_task: asyncio.Task | None = None
        self._pending_keys: set[str] = set()  # Track in-flight commands

    def start(self, entry: ConfigEntry) -> None:
        """Start background worker task."""
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = entry.async_create_background_task(
                self.hass, self._worker_loop(), name="tado_api_manager_worker"
            )
            _LOGGER.debug("TadoApiManager background worker started")

    def shutdown(self) -> None:
        """Stop worker task and cancel all pending timers."""
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
        for cancel_fn in self._pending_timers.values():
            cancel_fn()
        self._pending_timers.clear()
        self._action_queue.clear()

    def _get_command_key(self, command: TadoCommand) -> str:
        """Reconstruct the key for a command (reverse of queue_command key logic)."""
        if command.cmd_type == CommandType.MANUAL_POLL:
            refresh_type = command.data.get("type", "all") if command.data else "all"
            return f"manual_poll_{refresh_type}"
        if command.cmd_type == CommandType.SET_PRESENCE:
            return "presence"
        if command.cmd_type == CommandType.IDENTIFY:
            serial = command.data.get("serial", "") if command.data else ""
            return f"identify_{serial}"
        if command.cmd_type in (
            CommandType.SET_CHILD_LOCK,
            CommandType.SET_OFFSET,
        ):
            # Device properties use serial from data
            serial = command.data.get("serial", "") if command.data else ""
            return f"{command.cmd_type.value}_{serial}"
        if command.cmd_type in (
            CommandType.SET_AWAY_TEMP,
            CommandType.SET_DAZZLE,
            CommandType.SET_EARLY_START,
            CommandType.SET_OPEN_WINDOW,
        ):
            # Zone properties
            return f"{command.cmd_type.value}_{command.zone_id}"
        if command.cmd_type in (CommandType.SET_OVERLAY, CommandType.RESUME_SCHEDULE):
            # Zone overlay/resume commands
            return f"zone_{command.zone_id}"

        # Fallback for unknown types
        return f"{command.cmd_type.value}_{command.zone_id or 'unknown'}"

    @property
    def pending_keys(self) -> set[str]:
        """Return set of currently pending command keys."""
        return self._pending_keys.copy()

    @staticmethod
    def get_protected_fields_for_key(key: str) -> set[str]:
        """Return which state fields should be protected for a given command key.

        Args:
            key: Command key (e.g., "zone_12", "presence", "set_offset_ABC123")

        Returns:
            Set of field names that should not be overwritten by polls while
            this command is pending.

        Examples:
            "zone_12" → {"overlay", "overlay_active", "setting"}
            "presence" → {"presence"}
            "set_offset_ABC123" → set() (device-level, no zone state protection)

        """
        # Zone overlay/resume commands protect overlay state
        if key.startswith("zone_"):
            return {"overlay", "overlay_active", "setting"}

        # Presence commands protect home state presence field
        return {"presence"} if key == "presence" else set()

    def queue_command(self, key: str, command: TadoCommand) -> None:
        """Add command to debounce queue."""
        if cancel_fn := self._pending_timers.pop(key, None):
            cancel_fn()

        self._action_queue[key] = command
        self._pending_keys.add(key)  # Mark key as pending

        @callback
        def _move_to_worker(_now=None, target_key: str = key):
            self._pending_timers.pop(target_key, None)
            if cmd := self._action_queue.pop(target_key, None):
                self._api_queue.put_nowait(cmd)

        self._pending_timers[key] = async_call_later(
            self.hass,
            float(self._debounce_time),
            HassJob(_move_to_worker, cancel_on_shutdown=True),
        )

    async def _worker_loop(self) -> None:
        """Sequential background processing loop."""
        batch: list[TadoCommand] = []
        while True:
            try:
                cmd = await self._api_queue.get()
                batch.append(cmd)
                self._api_queue.task_done()

                await asyncio.sleep(BATCH_LINGER_S)
                while not self._api_queue.empty():
                    batch.append(self._api_queue.get_nowait())
                    self._api_queue.task_done()

                if batch:
                    await self._process_batch(batch)
                    batch.clear()
            except asyncio.CancelledError:
                break
            except Exception:
                _LOGGER.exception("Unexpected error in worker loop")
                await asyncio.sleep(float(self._debounce_time))

    async def _process_batch(self, commands: list[TadoCommand]) -> None:
        """Merge and execute a batch of commands."""
        # Initial jitter to break temporal correlation with triggers (1.0s base)
        await self._maybe_apply_call_jitter(base_delay=1.0)

        # Collect keys from batch for cleanup after execution
        batch_keys = {self._get_command_key(cmd) for cmd in commands}

        merger = CommandMerger(self.coordinator.zones_meta)
        for cmd in commands:
            merger.add(cmd)
        merged = merger.result

        if merged["presence"]:
            await self._execute_presence(merged["presence"], merged.get("old_presence"))

        await self._execute_child_locks(
            merged["child_lock"], merged.get("rollback_child_locks", {})
        )
        await self._execute_offset_actions(
            merged["offsets"], merged.get("rollback_offsets", {})
        )

        for prop, action_name, api_call, rollback_fn, rollback_data in [
            (
                merged["away_temps"],
                "away temp",
                self.coordinator.client.set_away_configuration,
                self.coordinator.optimistic.clear_away_temp,
                merged.get("rollback_away_temps", {}),
            ),
            (
                merged["dazzle_modes"],
                "dazzle",
                self.coordinator.client.set_dazzle_mode,
                self.coordinator.optimistic.clear_dazzle,
                merged.get("rollback_dazzle_modes", {}),
            ),
            (
                merged["early_starts"],
                "early start",
                self.coordinator.client.set_early_start,
                self.coordinator.optimistic.clear_early_start,
                merged.get("rollback_early_starts", {}),
            ),
            (
                merged["open_windows"],
                "open window",
                self.coordinator.client.set_open_window_detection,
                self.coordinator.optimistic.clear_open_window,
                merged.get("rollback_open_windows", {}),
            ),
        ]:
            await self._execute_zone_property_actions(
                prop, action_name, api_call, rollback_fn, rollback_data
            )

        await self._execute_identify_actions(merged["identifies"])
        await self._execute_zone_actions(
            merged["zones"], merged.get("rollback_zones", {})
        )

        # Clear pending keys after batch execution
        for key in batch_keys:
            self._pending_keys.discard(key)

        self.coordinator.update_rate_limit_local(silent=False)
        if merged["manual_poll"]:
            # Jitter manual poll as well
            await self._maybe_apply_call_jitter()
            await self.coordinator._execute_manual_poll(merged["manual_poll"])
        elif self.coordinator.rate_limit.is_throttled:
            self.coordinator.rate_limit.decrement(len(commands))

    async def _execute_presence(self, presence: str, old_presence: str | None) -> None:
        """Execute presence update with local rollback."""
        await self._maybe_apply_call_jitter()
        try:
            await self.coordinator.client.set_presence(presence)
        except Exception as e:
            _LOGGER.error(
                "Failed to set presence to '%s': %s (type: %s)",
                presence,
                e,
                type(e).__name__,
            )
            self.coordinator.optimistic.clear_presence()

            if old_presence and self.coordinator.data.home_state:
                _LOGGER.info("Rolling back local presence state to %s", old_presence)
                self.coordinator.data.home_state.presence = old_presence
                self.coordinator.async_update_listeners()
            else:
                await self.coordinator.async_manual_poll("presence")

    async def _execute_device_actions(
        self,
        actions: dict[str, Any],
        action_name: str,
        api_call: Any,
        rollback_fn: Any,
        rollback_data: dict[str, Any],
        attribute_name: str,
    ) -> None:
        """Execute generic device action helper with rollback."""
        for serial, value in actions.items():
            await self._maybe_apply_call_jitter()
            try:
                await api_call(serial, value)
            except Exception as e:
                _LOGGER.error(
                    "Failed to set %s for %s: %s (type: %s). Value: %s",
                    action_name,
                    serial,
                    e,
                    type(e).__name__,
                    value,
                )
                rollback_fn(serial)

                if serial in rollback_data and self.coordinator.devices_meta.get(
                    serial
                ):
                    old_val = rollback_data[serial]
                    setattr(
                        self.coordinator.devices_meta[serial], attribute_name, old_val
                    )
                    _LOGGER.info("Rolled back %s for %s", attribute_name, serial)

                self.coordinator.async_update_listeners()

    async def _execute_child_locks(
        self, actions: dict[str, bool], rollback_data: dict[str, Any]
    ) -> None:
        """Execute child locks."""
        await self._execute_device_actions(
            actions,
            "set child lock",
            lambda s, v: self.coordinator.client.set_child_lock(s, child_lock=v),
            self.coordinator.optimistic.clear_child_lock,
            rollback_data,
            "child_lock_enabled",
        )

    async def _execute_offset_actions(
        self, actions: dict[str, float], rollback_data: dict[str, Any]
    ) -> None:
        """Execute offsets."""
        for serial, value in actions.items():
            await self._maybe_apply_call_jitter()
            try:
                await self.coordinator.client.set_temperature_offset(serial, value)
            except Exception as e:
                _LOGGER.error(
                    "Failed to set offset for %s: %s (type: %s). Value: %s",
                    serial,
                    e,
                    type(e).__name__,
                    value,
                )
                self.coordinator.optimistic.clear_offset(serial)

                if serial in rollback_data:
                    self.coordinator.data_manager.offsets_cache[serial] = rollback_data[
                        serial
                    ]
                    _LOGGER.info("Rolled back offset for %s", serial)

                self.coordinator.async_update_listeners()

    async def _execute_zone_property_actions(
        self,
        actions: dict[int, Any],
        action_name: str,
        api_call: Any,
        rollback_fn: Any,
        rollback_data: dict[int, Any],
    ) -> None:
        """Execute generic zone property helper with rollback."""
        attr_map = {
            "away temp": None,
            "dazzle": "dazzle_enabled",
            "early start": "early_start_enabled",
            "open window": None,
        }

        handler = self.coordinator.dummy_handler  # [DUMMY_HOOK]
        for zone_id, value in actions.items():
            # [DUMMY_HOOK]
            if handler and handler.is_dummy_zone(zone_id):
                continue

            await self._maybe_apply_call_jitter()
            try:
                await api_call(zone_id, value)
            except Exception as e:
                _LOGGER.error(
                    "Failed to set %s for zone %d: %s (type: %s). Value: %s",
                    action_name,
                    zone_id,
                    e,
                    type(e).__name__,
                    value,
                )
                rollback_fn(zone_id)

                if zone_id in rollback_data:
                    old_val = rollback_data[zone_id]

                    if action_name == "away temp":
                        self.coordinator.data_manager.away_cache[zone_id] = old_val
                    elif action_name == "open window":
                        if zone := self.coordinator.zones_meta.get(zone_id):
                            if zone.open_window_detection:
                                zone.open_window_detection.enabled = old_val
                    elif attr := attr_map.get(action_name):
                        if zone := self.coordinator.zones_meta.get(zone_id):
                            setattr(zone, attr, old_val)

                    _LOGGER.info("Rolled back %s for zone %d", action_name, zone_id)

                self.coordinator.async_update_listeners()

    async def _execute_identify_actions(self, actions: set[str]) -> None:
        """Execute identify."""
        for serial in actions:
            await self._maybe_apply_call_jitter()
            try:
                await self.coordinator.client.identify_device(serial)
            except Exception as e:
                _LOGGER.error("Failed to identify device %s: %s", serial, e)

    async def _execute_zone_actions(
        self,
        actions: dict[int, dict[str, Any] | None],
        rollback_zones: dict[int, Any],
    ) -> None:
        """Execute zone actions (bulk for heating, individual for hot water)."""
        heating_resumes, heating_overlays, hw_actions = self._group_zone_actions(
            actions
        )

        if heating_resumes:
            await self._run_bulk_resume(heating_resumes, rollback_zones)
        if heating_overlays:
            await self._run_bulk_overlay(heating_overlays, rollback_zones)
        if hw_actions:
            await self._run_hw_actions(hw_actions, rollback_zones)

    def _group_zone_actions(self, actions: dict[int, dict[str, Any] | None]):
        """Separate actions by zone type and operation."""
        resumes, overlays, hw = [], [], {}
        for zid, data in actions.items():
            z = self.coordinator.zones_meta.get(zid)
            if z and z.type == "HOT_WATER":
                hw[zid] = data
            elif data is None:
                resumes.append(zid)
            else:
                overlays.append({"room": zid, "overlay": data})
        return resumes, overlays, hw

    def _rollback_zones(
        self, zone_ids: list[int], rollback_data: dict[int, Any]
    ) -> None:
        """Rollback local zone states to original snapshot."""
        restored = False
        for zid in zone_ids:
            if old_state := rollback_data.get(zid):
                if self.coordinator.data.zone_states:
                    str_id = str(zid)
                    self.coordinator.data.zone_states[str_id] = old_state
                    restored = True

            self.coordinator.optimistic.clear_zone(zid)

        if restored:
            _LOGGER.info("Rolled back local state for zones: %s", zone_ids)
            self.coordinator.async_update_listeners()

    async def _run_bulk_resume(
        self, zones: list[int], rollback_data: dict[int, Any]
    ) -> bool:
        """Execute bulk resume."""
        # [DUMMY_HOOK] Intercept dummy zones and get remaining real zones
        handler = self.coordinator.dummy_handler
        real_zones = handler.filter_and_intercept_resume(zones) if handler else zones

        if not real_zones:
            return True

        await self._maybe_apply_call_jitter()
        try:
            await self.coordinator.client.reset_all_zones_overlay(real_zones)
            return True
        except Exception as e:
            _LOGGER.error(
                "Failed to bulk resume: %s (type: %s). Zones: %s",
                e,
                type(e).__name__,
                real_zones,
            )
            self._rollback_zones(real_zones, rollback_data)
            return False

    async def _run_bulk_overlay(
        self, overlays: list[dict[str, Any]], rollback_data: dict[int, Any]
    ) -> bool:
        """Execute bulk overlay."""
        # [DUMMY_HOOK] Intercept dummy overlays and get remaining real overlays
        handler = self.coordinator.dummy_handler
        real_overlays = (
            handler.filter_and_intercept_overlays(overlays) if handler else overlays
        )

        if not real_overlays:
            return True

        await self._maybe_apply_call_jitter()
        try:
            await self.coordinator.client.set_all_zones_overlay(real_overlays)
            return True
        except Exception as e:
            _LOGGER.error(
                "Failed bulk overlay: %s (type: %s). Payload: %s",
                e,
                type(e).__name__,
                real_overlays,
                exc_info=True,
            )
            self._rollback_zones([ov["room"] for ov in real_overlays], rollback_data)
            return False

    async def _run_hw_actions(
        self,
        actions: dict[int, dict[str, Any] | None],
        rollback_data: dict[int, Any],
    ) -> bool:
        """Execute hot water actions individually."""
        any_success = False
        handler = self.coordinator.dummy_handler  # [DUMMY_HOOK]

        for zid, data in actions.items():
            # [DUMMY_HOOK]
            if handler and handler.intercept_command(zid, data):
                any_success = True
                continue

            await self._maybe_apply_call_jitter()
            try:
                if data is None:
                    await self.coordinator.client.reset_hot_water_zone_overlay(zid)
                else:
                    await self.coordinator.client.set_hot_water_zone_overlay(zid, data)
                any_success = True
            except Exception as e:
                _LOGGER.error(
                    "Failed hot water overlay for zone %d: %s (type: %s). Payload: %s",
                    zid,
                    e,
                    type(e).__name__,
                    data,
                    exc_info=True,
                )
                self._rollback_zones([zid], rollback_data)
        return any_success

    async def _maybe_apply_call_jitter(self, base_delay: float = 0.5) -> None:
        """Apply a random jitter delay before an API call (Proxy only)."""
        if not self.coordinator.config_entry.data.get(CONF_API_PROXY_URL):
            return

        if not self.coordinator.config_entry.data.get(CONF_CALL_JITTER_ENABLED):
            return

        jitter_percent = float(
            self.coordinator.config_entry.data.get(
                CONF_JITTER_PERCENT, DEFAULT_JITTER_PERCENT
            )
        )
        # Apply jitter to the base delay
        delay = apply_jitter(base_delay, jitter_percent)
        if delay > 0:
            _LOGGER.debug("Applying call jitter delay: %.3fs", delay)
            await asyncio.sleep(delay)
