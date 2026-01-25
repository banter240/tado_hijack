"""Manages prioritized and debounced API access for Tado Hijack."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HassJob, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later

from ..const import BATCH_LINGER_S
from ..models import TadoCommand
from .command_merger import CommandMerger
from .logging_utils import get_redacted_logger

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

    def start(self, entry: ConfigEntry) -> None:
        """Start the background worker task using Home Assistant's background task handler."""
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = entry.async_create_background_task(
                self.hass, self._worker_loop(), name="tado_api_manager_worker"
            )
            _LOGGER.debug("TadoApiManager background worker task started")

    def shutdown(self) -> None:
        """Stop the worker task and cancel all pending timers."""
        # Cancel worker task
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            _LOGGER.debug("TadoApiManager worker task cancelled")

        # Cancel all pending timers
        for key, cancel_fn in list(self._pending_timers.items()):
            cancel_fn()
            _LOGGER.debug("Cancelled pending timer for '%s'", key)
        self._pending_timers.clear()
        self._action_queue.clear()

    def queue_command(self, key: str, command: TadoCommand) -> None:
        """Add a command to the debounce queue (per-key debounce)."""
        _LOGGER.debug("Queue: Requesting command '%s' (%s)", key, command.cmd_type)
        # Cancel existing timer for THIS key (defensive pop)
        if cancel_fn := self._pending_timers.pop(key, None):
            _LOGGER.debug("Queue: Cancelling existing timer for '%s'", key)
            cancel_fn()

        self._action_queue[key] = command
        _LOGGER.debug(
            "Queue: Action '%s' added/updated. Waiting %ds debounce.",
            key,
            self._debounce_time,
        )

        @callback
        def _move_to_worker(_now=None, target_key: str = key):
            self._pending_timers.pop(target_key, None)

            # Retrieve specific action
            if cmd := self._action_queue.pop(target_key, None):
                _LOGGER.debug(
                    "Queue: Debounce expired for '%s'. Moving to worker. Queue size before: %d",
                    target_key,
                    self._api_queue.qsize(),
                )
                self._api_queue.put_nowait(cmd)

        self._pending_timers[key] = async_call_later(
            self.hass,
            float(self._debounce_time),
            HassJob(_move_to_worker, cancel_on_shutdown=True),
        )

    async def _worker_loop(self) -> None:
        """Background loop to process the queue sequentially."""
        _LOGGER.debug("Worker: Loop started")
        batch: list[TadoCommand] = []

        while True:
            try:
                # 1. Fetch first item (blocking)
                cmd = await self._api_queue.get()
                batch.append(cmd)
                self._api_queue.task_done()

                # 2. Linger to catch stragglers
                # Wait briefly to see if more commands arrive
                await asyncio.sleep(BATCH_LINGER_S)

                # 3. Drain queue (non-blocking)
                while not self._api_queue.empty():
                    cmd = self._api_queue.get_nowait()
                    batch.append(cmd)
                    self._api_queue.task_done()

                # 4. Process the batch
                if batch:
                    _LOGGER.debug("Worker: Processing batch of %d commands", len(batch))
                    await self._process_batch(batch)
                    batch.clear()

            except asyncio.CancelledError:
                _LOGGER.debug("API worker loop cancelled")
                break
            except Exception as e:
                _LOGGER.exception("Unexpected error in worker loop: %s", e)
                await asyncio.sleep(float(self._debounce_time))

    async def _process_batch(self, commands: list[TadoCommand]) -> None:
        """Smartly merge and execute a batch of commands."""
        # 1. Consolidated state via merger
        merger = CommandMerger(self.coordinator.zones_meta)
        for cmd in commands:
            merger.add(cmd)

        merged = merger.result

        # 2. Execute Presence (Global, independent)
        if merged["presence"]:
            _LOGGER.debug("Worker: Setting presence to %s", merged["presence"])
            try:
                await self.coordinator.client.set_presence(merged["presence"])
            except Exception as e:
                _LOGGER.error("Failed to set presence: %s", e)
                # Rollback optimistic state on error
                self.coordinator.optimistic.clear_presence()
                self.coordinator.async_update_listeners()

        # 3. Execute Child Lock Actions
        await self._execute_child_locks(merged["child_lock"])

        # 4. Execute Offset Actions
        await self._execute_offset_actions(merged["offsets"])

        # 5. Execute Away Temp Actions
        await self._execute_zone_property_actions(
            merged["away_temps"],
            "away temp",
            self.coordinator.client.set_away_configuration,
            self.coordinator.optimistic.clear_away_temp,
        )

        # 6. Execute Dazzle Actions
        await self._execute_zone_property_actions(
            merged["dazzle_modes"],
            "dazzle",
            self.coordinator.client.set_dazzle_mode,
            self.coordinator.optimistic.clear_dazzle,
        )

        # 7. Execute Early Start Actions
        await self._execute_zone_property_actions(
            merged["early_starts"],
            "early start",
            self.coordinator.client.set_early_start,
            self.coordinator.optimistic.clear_early_start,
        )

        # 8. Execute Open Window Actions
        await self._execute_zone_property_actions(
            merged["open_windows"],
            "open window",
            self.coordinator.client.set_open_window_detection,
            self.coordinator.optimistic.clear_open_window,
        )

        # 9. Execute Identify Actions
        await self._execute_identify_actions(merged["identifies"])

        # 10. Execute Zone Actions (Bulk)
        await self._execute_zone_actions(merged["zones"])

        # 11. Post-execution sync & Rate limit update
        self.coordinator.update_rate_limit_local(silent=False)

        if merged["manual_poll"]:
            _LOGGER.debug("Worker: Executing manual poll (%s)", merged["manual_poll"])
            await self.coordinator._execute_manual_poll(merged["manual_poll"])
        elif self.coordinator.rate_limit.is_throttled:
            self.coordinator.rate_limit.decrement(len(commands))

    async def _execute_device_actions(
        self,
        actions: dict[str, Any],
        action_name: str,
        api_call: Any,
        rollback_fn: Any,
    ) -> None:
        """Execute device-specific actions with rollback (DRY helper).

        Args:
            actions: Dict mapping serial_no to value
            action_name: Human-readable action name for logging
            api_call: Async function to call for each action
            rollback_fn: Function to call on error for rollback

        """
        for serial, value in actions.items():
            _LOGGER.debug("Worker: %s for %s: %s", action_name, serial, value)
            try:
                await api_call(serial, value)
            except Exception as e:
                _LOGGER.error("Failed to %s for %s: %s", action_name, serial, e)
                rollback_fn(serial)
                self.coordinator.async_update_listeners()

    async def _execute_child_locks(self, actions: dict[str, bool]) -> None:
        """Execute child lock actions sequentially."""
        await self._execute_device_actions(
            actions=actions,
            action_name="set child lock",
            api_call=lambda serial, enabled: self.coordinator.client.set_child_lock(
                serial, child_lock=enabled
            ),
            rollback_fn=self.coordinator.optimistic.clear_child_lock,
        )

    async def _execute_offset_actions(self, actions: dict[str, float]) -> None:
        """Execute offset actions sequentially."""
        await self._execute_device_actions(
            actions=actions,
            action_name="set temperature offset",
            api_call=self.coordinator.client.set_temperature_offset,
            rollback_fn=self.coordinator.optimistic.clear_offset,
        )

    async def _execute_zone_property_actions(
        self,
        actions: dict[int, Any],
        action_name: str,
        api_call: Any,
        rollback_fn: Any,
    ) -> None:
        """Execute zone-specific property actions with rollback (DRY helper)."""
        for zone_id, value in actions.items():
            _LOGGER.debug("Worker: %s for zone %d: %s", action_name, zone_id, value)
            try:
                await api_call(zone_id, value)
            except Exception as e:
                _LOGGER.error("Failed to %s for zone %d: %s", action_name, zone_id, e)
                rollback_fn(zone_id)
                self.coordinator.async_update_listeners()

    async def _execute_identify_actions(self, actions: set[str]) -> None:
        """Execute identify actions sequentially."""
        for serial in actions:
            _LOGGER.debug("Worker: Identifying device %s", serial)
            try:
                await self.coordinator.client.identify_device(serial)
            except Exception as e:
                _LOGGER.error("Failed to identify device %s: %s", serial, e)

    async def _execute_zone_actions(
        self, actions: dict[int, dict[str, Any] | None]
    ) -> None:
        """Execute zone actions using bulk APIs where possible."""
        resumes: list[int] = []
        overlays: list[dict[str, Any]] = []

        for zone_id, data in actions.items():
            if data is None:
                resumes.append(zone_id)
            else:
                overlays.append({"room": zone_id, "overlay": data})

        if resumes:
            _LOGGER.debug("Worker: Bulk resuming %d zones: %s", len(resumes), resumes)
            try:
                await self.coordinator.client.reset_all_zones_overlay(resumes)
            except Exception as e:
                _LOGGER.error("Failed to bulk resume: %s", e)
                # Rollback optimistic state on error
                for zone_id in resumes:
                    self.coordinator.optimistic.clear_zone(zone_id)
                self.coordinator.async_update_listeners()

        if overlays:
            _LOGGER.debug("Worker: Bulk setting %d overlays", len(overlays))
            _LOGGER.debug("Overlay payload: %s", overlays)
            try:
                await self.coordinator.client.set_all_zones_overlay(overlays)
            except Exception as e:
                _LOGGER.error("Failed to bulk overlay: %s", e)
                _LOGGER.error("Failed overlays payload: %s", overlays)
                # Rollback optimistic state on error
                for overlay in overlays:
                    self.coordinator.optimistic.clear_zone(overlay["room"])
                self.coordinator.async_update_listeners()
