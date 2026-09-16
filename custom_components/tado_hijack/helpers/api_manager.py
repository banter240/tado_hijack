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
from .command_merger import (
    CommandMerger,
    format_executor_payload,
    merged_has_executor_work,
)
from .executor_unified import TadoUnifiedExecutor
from .logging_utils import get_redacted_logger
from .schedule import schedule_queue_key_for_command
from .timetable import queue_key_for_command
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
        self._worker_task: asyncio.Task[Any] | None = None
        self._pending_keys: set[str] = set()  # Track in-flight commands

        # Modular Executor Gateway
        self._executor = TadoUnifiedExecutor(coordinator)

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

    def _describe_command(self, command: TadoCommand) -> str:
        """Return a human-readable description of the command action."""
        data = command.data or {}
        if command.cmd_type == CommandType.SET_OVERLAY:
            return self._describe_overlay(command, data)
        if command.cmd_type in (CommandType.SET_CHILD_LOCK, CommandType.SET_OFFSET):
            field = (
                "child_lock"
                if command.cmd_type == CommandType.SET_CHILD_LOCK
                else "offset"
            )
            return f"(serial={data.get('serial', '?')}, value={data.get(field, '?')})"
        if command.cmd_type in (
            CommandType.REFRESH_TIMETABLE,
            CommandType.REFRESH_SCHEDULE,
        ):
            if command.zone_id is not None:
                return f"(zone={command.zone_id})"
            return f"(zones={data.get('zone_ids', [])})"

        descriptions = {
            CommandType.RESUME_SCHEDULE: f"(zone={command.zone_id})",
            CommandType.SET_PRESENCE: f"(presence={data.get('presence', '?')})",
            CommandType.IDENTIFY: f"(serial={data.get('serial', '?')})",
            CommandType.MANUAL_POLL: f"(type={data.get('type', 'all')})",
            CommandType.SET_TIMETABLE: (
                f"(zone={command.zone_id}, timetable_id={data.get('timetable_id', '?')})"
            ),
            CommandType.SET_SCHEDULE: (
                f"(zone={command.zone_id}, day={data.get('day_type', '?')}, "
                f"timetable_id={data.get('timetable_id', '?')})"
            ),
            CommandType.QUICK_ACTION: f"(action={data.get('action', '?')})",
        }
        if command.cmd_type in descriptions:
            return descriptions[command.cmd_type]
        return f"(zone={command.zone_id})" if command.zone_id else ""

    @staticmethod
    def _describe_overlay(command: TadoCommand, data: dict[str, Any]) -> str:
        """Describe a SET_OVERLAY command."""
        if command.zone_id and data:
            setting = data.get("setting", {})
            power = setting.get("power", "?")
            temp = setting.get("temperature", {}).get("celsius", "?")
            return f"(zone={command.zone_id}, power={power}, temp={temp}°C)"
        return f"(zone={command.zone_id})"

    def _get_command_key(self, command: TadoCommand) -> str:
        """Reconstruct the key for a command (reverse of queue_command key logic)."""
        if command.cmd_type == CommandType.MANUAL_POLL:
            data = command.data or {}
            refresh_type = data.get("type", "all")
            if entity_id := data.get("entity_id"):
                return f"manual_poll_{refresh_type}_{entity_id}"
            if refresh_type == "capabilities":
                zid = (
                    command.zone_id
                    if command.zone_id is not None
                    else data.get("zone_id")
                )
                if zid is not None:
                    return f"manual_poll_capabilities_{zid}"
            return f"manual_poll_{refresh_type}"
        if command.cmd_type == CommandType.QUICK_ACTION:
            return "x_quick_action"
        if command.cmd_type == CommandType.SET_PRESENCE:
            return "presence"
        if command.cmd_type == CommandType.IDENTIFY:
            serial = command.data.get("serial", "") if command.data else ""
            return f"identify_{serial}"
        if key := queue_key_for_command(command):
            return key
        if key := schedule_queue_key_for_command(command):
            return key
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

    @property
    def _suppress_calls(self) -> bool:
        return getattr(self.coordinator, "_suppress_redundant_calls", False)

    @property
    def _suppress_buttons(self) -> bool:
        return getattr(self.coordinator, "_suppress_redundant_buttons", False)

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
        was_replaced = False
        if cancel_fn := self._pending_timers.pop(key, None):
            cancel_fn()
            was_replaced = True

        if was_replaced and self._suppress_calls:
            if existing := self._action_queue.get(key):
                from .redundancy_checker import preserve_rollback_state

                preserve_rollback_state(existing, command)

        self._action_queue[key] = command
        self._pending_keys.add(key)  # Mark key as pending

        # Log queuing details
        action_desc = self._describe_command(command)
        status = "replaced pending" if was_replaced else "queued"
        _LOGGER.debug(
            "Command %s: %s [key=%s, debounce=%ds] %s",
            status,
            command.cmd_type.value,
            key,
            self._debounce_time,
            action_desc,
        )

        self._rearm_pending_debounce()

    def _arm_key_timer(self, key: str) -> None:
        """Start or reset the debounce timer that flushes this queue key."""
        if cancel_fn := self._pending_timers.pop(key, None):
            cancel_fn()

        @callback
        def _move_to_worker(_now: Any = None, target_key: str = key) -> None:
            self._pending_timers.pop(target_key, None)
            if cmd := self._action_queue.pop(target_key, None):
                self._api_queue.put_nowait(cmd)

        self._pending_timers[key] = async_call_later(
            self.hass,
            float(self._debounce_time),
            HassJob(_move_to_worker, cancel_on_shutdown=True),
        )

    def _rearm_pending_debounce(self) -> None:
        """Hold every pending command until debounce after the last queue."""
        keys = list(self._action_queue)
        for key in keys:
            self._arm_key_timer(key)
        if len(keys) > 1:
            _LOGGER.debug(
                "Rearmed shared debounce for %d command(s): %s",
                len(keys),
                keys,
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

        # Log batch composition
        _LOGGER.debug(
            "Processing batch of %d commands: %s",
            len(commands),
            [cmd.cmd_type.value for cmd in commands],
        )

        merger = CommandMerger(self.coordinator.zones_meta)
        for cmd in commands:
            merger.add(cmd)
        merged = merger.result

        # Named fields, generated from merger payload keys so a new command
        # type cannot drop out of the debug line.
        _LOGGER.debug("Merged batch payloads: %s", format_executor_payload(merged))

        # Filter redundant operations BEFORE sending (Toggle 1 - State Changes)
        from .redundancy_checker import filter_redundant_merged_data

        if suppress_enabled := self._suppress_calls:
            # Use pre-patch states from rollback_context: zone_states in coordinator.data
            # are already mutated by state_patcher before queuing, so they reflect the
            # target — not the device state we should compare against.
            pre_patch_states: dict[str, Any] = {
                str(cmd.zone_id): cmd.rollback_context
                for cmd in commands
                if cmd.cmd_type
                in (CommandType.SET_OVERLAY, CommandType.RESUME_SCHEDULE)
                and cmd.zone_id is not None
                and cmd.rollback_context is not None
            }
            merged = filter_redundant_merged_data(
                merged,
                pre_patch_states,
                suppress_enabled,
                self._suppress_buttons,
            )

            # Check if payload is empty after filtering - if so, skip sending
            if not merged_has_executor_work(merged):
                _LOGGER.info(
                    "Skipping API call: all %d command(s) redundant after filtering (%s)",
                    len(commands),
                    [cmd.cmd_type.value for cmd in commands],
                )
                return
            _LOGGER.debug(
                "Merged batch payloads after redundancy filter: %s",
                format_executor_payload(merged),
            )

        # Delegate execution to the Unified Executor
        await self._executor.execute_batch(merged)

        # Clear pending keys after batch execution
        for key in batch_keys:
            self._pending_keys.discard(key)

        self.coordinator.update_rate_limit_local(silent=False)
        if (
            merged["manual_poll"]
            or merged.get("capability_zone_ids")
            or merged.get("targeted_polls")
        ):
            await self._maybe_apply_call_jitter()
            await self.coordinator._execute_manual_poll(
                merged["manual_poll"],
                capability_zone_ids=merged.get("capability_zone_ids") or (),
                targeted_polls=merged.get("targeted_polls") or (),
            )
        elif self.coordinator.rate_limit.is_throttled:
            self.coordinator.rate_limit.decrement(len(commands))

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
