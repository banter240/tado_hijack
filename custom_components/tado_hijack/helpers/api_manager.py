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
from .executor_unified import TadoUnifiedExecutor
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
        if command.cmd_type == CommandType.SET_OVERLAY:
            if command.zone_id and command.data:
                setting = command.data.get("setting", {})
                power = setting.get("power", "?")
                temp = setting.get("temperature", {}).get("celsius", "?")
                return f"(zone={command.zone_id}, power={power}, temp={temp}°C)"
            return f"(zone={command.zone_id})"
        elif command.cmd_type == CommandType.RESUME_SCHEDULE:
            return f"(zone={command.zone_id})"
        elif command.cmd_type == CommandType.SET_PRESENCE:
            presence = command.data.get("presence") if command.data else "?"
            return f"(presence={presence})"
        elif command.cmd_type in (CommandType.SET_CHILD_LOCK, CommandType.SET_OFFSET):
            serial = command.data.get("serial", "?") if command.data else "?"
            value = (
                (
                    command.data.get("child_lock")
                    if command.cmd_type == CommandType.SET_CHILD_LOCK
                    else command.data.get("offset")
                )
                if command.data
                else "?"
            )
            return f"(serial={serial}, value={value})"
        elif command.cmd_type == CommandType.IDENTIFY:
            serial = command.data.get("serial", "?") if command.data else "?"
            return f"(serial={serial})"
        elif command.cmd_type == CommandType.MANUAL_POLL:
            poll_type = command.data.get("type", "all") if command.data else "all"
            return f"(type={poll_type})"
        else:
            return f"(zone={command.zone_id})" if command.zone_id else ""

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
        was_replaced = False
        if cancel_fn := self._pending_timers.pop(key, None):
            cancel_fn()
            was_replaced = True

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

        # Log merged result with full payloads for debugging
        _LOGGER.debug(
            "Merged batch payloads: presence=%s, zones=%s, child_lock=%s, offsets=%s, "
            "away_temps=%s, dazzle=%s, early_start=%s, open_window=%s, identifies=%s",
            merged.get("presence"),
            merged.get("zones", {}),
            merged.get("child_lock", {}),
            merged.get("offsets", {}),
            merged.get("away_temps", {}),
            merged.get("dazzle_modes", {}),
            merged.get("early_starts", {}),
            merged.get("open_windows", {}),
            merged.get("identifies", []),
        )

        # Filter redundant operations BEFORE sending (Toggle 1 - State Changes)
        from .redundancy_checker import filter_redundant_merged_data

        suppress_enabled = getattr(self.coordinator, "_suppress_redundant_calls", False)
        if suppress_enabled and hasattr(self.coordinator, "action_provider"):
            merged = filter_redundant_merged_data(
                merged,
                self.coordinator.action_provider,
                self.coordinator.optimistic,
                suppress_enabled,
            )

            # Check if payload is empty after filtering - if so, skip sending
            is_empty = not any(
                [
                    merged.get("presence"),
                    merged.get("zones"),
                    merged.get("child_lock"),
                    merged.get("offsets"),
                    merged.get("away_temps"),
                    merged.get("dazzle_modes"),
                    merged.get("early_starts"),
                    merged.get("open_windows"),
                    merged.get("identifies"),
                ]
            )
            if is_empty:
                _LOGGER.info(
                    "All operations redundant after filtering, skipping API call"
                )
                return

        # Delegate execution to the Unified Executor
        await self._executor.execute_batch(merged)

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
