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

    def queue_command(self, key: str, command: TadoCommand) -> None:
        """Add a command to the debounce queue (per-key debounce)."""
        _LOGGER.debug("Queue: Requesting command '%s' (%s)", key, command.cmd_type)
        # Cancel existing timer for THIS key
        if key in self._pending_timers:
            _LOGGER.debug("Queue: Cancelling existing timer for '%s'", key)
            self._pending_timers.pop(key)()

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
                # Fetch first item (blocking)
                cmd = await self._api_queue.get()
                batch.append(cmd)
                self._api_queue.task_done()

                # Linger to catch stragglers
                await asyncio.sleep(BATCH_LINGER_S)

                # Drain queue (non-blocking)
                while not self._api_queue.empty():
                    cmd = self._api_queue.get_nowait()
                    batch.append(cmd)
                    self._api_queue.task_done()

                # Process the batch
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
        merger = CommandMerger(self.coordinator.zones_meta)
        for cmd in commands:
            merger.add(cmd)

        merged = merger.result

        # Execute Presence (Global, independent)
        if merged["presence"]:
            _LOGGER.debug("Worker: Setting presence to %s", merged["presence"])
            try:
                await self.coordinator.client.set_presence(merged["presence"])
            except Exception as e:
                _LOGGER.error("Failed to set presence: %s", e)

        # Execute Child Lock Actions
        await self._execute_child_locks(merged["child_lock"])

        # Execute Offset Actions
        await self._execute_offset_actions(merged["offsets"])

        # Execute Away Temp Actions
        await self._execute_away_actions(merged["away_temps"])

        # Execute Dazzle Actions
        await self._execute_dazzle_actions(merged["dazzle_modes"])

        # Execute Early Start Actions
        await self._execute_early_start_actions(merged["early_starts"])

        # Execute Open Window Actions
        await self._execute_open_window_actions(merged["open_windows"])

        # Execute Identify Actions
        await self._execute_identify_actions(merged["identifies"])

        # Execute Zone Actions (Bulk)
        await self._execute_zone_actions(merged["zones"])

        # Manual Poll / Update Rate Limit
        self.coordinator.update_rate_limit_local(silent=False)

        if merged["manual_poll"]:
            _LOGGER.debug("Worker: Executing manual poll (%s)", merged["manual_poll"])
            await self.coordinator._execute_manual_poll(merged["manual_poll"])
        elif self.coordinator.rate_limit.is_throttled:
            self.coordinator.rate_limit.decrement(len(commands))

    async def _execute_child_locks(self, actions: dict[str, bool]) -> None:
        """Execute child lock actions sequentially."""
        for serial, enabled in actions.items():
            _LOGGER.debug("Worker: Setting child lock for %s to %s", serial, enabled)
            try:
                await self.coordinator.client.set_child_lock(serial, child_lock=enabled)
            except Exception as e:
                _LOGGER.error("Failed to set child lock for %s: %s", serial, e)

    async def _execute_offset_actions(self, actions: dict[str, float]) -> None:
        """Execute offset actions sequentially."""
        for serial, offset in actions.items():
            _LOGGER.debug(
                "Worker: Setting temperature offset for %s to %.1f", serial, offset
            )
            try:
                await self.coordinator.client.set_temperature_offset(serial, offset)
            except Exception as e:
                _LOGGER.error("Failed to set temperature offset for %s: %s", serial, e)

    async def _execute_away_actions(self, actions: dict[int, float]) -> None:
        """Execute away temperature actions sequentially."""
        for zone_id, temp in actions.items():
            _LOGGER.debug(
                "Worker: Setting away temperature for zone %d to %.1f", zone_id, temp
            )
            try:
                await self.coordinator.client.set_away_configuration(zone_id, temp)
            except Exception as e:
                _LOGGER.error(
                    "Failed to set away temperature for zone %d: %s", zone_id, e
                )

    async def _execute_dazzle_actions(self, actions: dict[int, bool]) -> None:
        """Execute dazzle mode actions sequentially."""
        for zone_id, enabled in actions.items():
            _LOGGER.debug(
                "Worker: Setting dazzle mode for zone %d to %s", zone_id, enabled
            )
            try:
                await self.coordinator.client.set_dazzle_mode(zone_id, enabled)
            except Exception as e:
                _LOGGER.error("Failed to set dazzle mode for zone %d: %s", zone_id, e)

    async def _execute_early_start_actions(self, actions: dict[int, bool]) -> None:
        """Execute early start actions sequentially."""
        for zone_id, enabled in actions.items():
            _LOGGER.debug(
                "Worker: Setting early start for zone %d to %s", zone_id, enabled
            )
            try:
                await self.coordinator.client.set_early_start(zone_id, enabled)
            except Exception as e:
                _LOGGER.error("Failed to set early start for zone %d: %s", zone_id, e)

    async def _execute_open_window_actions(self, actions: dict[int, bool]) -> None:
        """Execute open window detection actions sequentially."""
        for zone_id, enabled in actions.items():
            _LOGGER.debug(
                "Worker: Setting open window detection for zone %d to %s",
                zone_id,
                enabled,
            )
            try:
                await self.coordinator.client.set_open_window_detection(
                    zone_id, enabled
                )
            except Exception as e:
                _LOGGER.error(
                    "Failed to set open window detection for zone %d: %s", zone_id, e
                )

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

        if overlays:
            _LOGGER.debug("Worker: Bulk setting %d overlays", len(overlays))
            try:
                await self.coordinator.client.set_all_zones_overlay(overlays)
            except Exception as e:
                _LOGGER.error("Failed to bulk overlay: %s", e)
