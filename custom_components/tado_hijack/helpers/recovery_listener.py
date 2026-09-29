"""Replay queued intents when a local TRV (HomeKit / Matter) recovers."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later

from ..const import (
    OFF_MAGIC_TEMP,
    POWER_OFF,
    POWER_ON,
    RECOVERY_BATCH_DEBOUNCE_S,
)
from .local_climate import async_set_off, async_set_temperature
from .logging_utils import get_redacted_logger

if TYPE_CHECKING:
    from ..coordinator import TadoDataUpdateCoordinator
    from .availability_tracker import AvailabilityTracker
    from .recovery_queue import LocalRecoveryQueue, QueuedIntent

_LOGGER = get_redacted_logger(__name__)


class LocalRecoveryListener:
    """Replay the last intent when a local device recovers.

    Simultaneous recoveries share one batch so a flap does not replay N times.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: TadoDataUpdateCoordinator,
        tracker: AvailabilityTracker,
        queue: LocalRecoveryQueue,
    ) -> None:
        """Initialize with HA, coordinator, tracker and queue references."""
        self._hass = hass
        self._coordinator = coordinator
        self._tracker = tracker
        self._queue = queue
        self._pending_batch: set[str] = set()
        self._batch_handle: Callable[[], None] | None = None

    async def async_start(self) -> None:
        """Register the recovery callback with the availability tracker."""
        self._tracker.register_on_available(self._on_device_recovery)
        _LOGGER.info("LocalRecoveryListener started")

    def shutdown(self) -> None:
        """Unregister the recovery callback and cancel a pending batch."""
        self._tracker.unregister_on_available(self._on_device_recovery)
        if self._batch_handle is not None:
            self._batch_handle()
            self._batch_handle = None
        self._pending_batch.clear()

    def _on_device_recovery(self, serial: str) -> None:
        """Collect a recovered serial into the current batch."""
        self._pending_batch.add(serial)

        if self._batch_handle is None:
            self._batch_handle = async_call_later(
                self._hass, RECOVERY_BATCH_DEBOUNCE_S, self._async_flush_batch
            )

    @callback
    def _async_flush_batch(self, _now: datetime) -> None:
        """Flush the collected batch (debounce timer fired)."""
        self._batch_handle = None
        self._hass.async_create_task(self._async_process_batch())

    async def _async_process_batch(self) -> None:
        """Replay queued intents. An expired overlay resumes the schedule instead."""
        if not self._pending_batch:
            return

        serials = list(self._pending_batch)
        self._pending_batch.clear()

        _LOGGER.info("Processing recovery batch for %d serial(s)", len(serials))

        resume_zones: dict[int, list[str]] = {}
        replay_tasks: list[Any] = []

        for serial in serials:
            intent = self._queue.pop(serial)
            if intent is None:
                _LOGGER.debug("Recovery for serial=%s without queued intent", serial)
                continue

            if intent.resume_schedule or intent.is_expired():
                _LOGGER.info(
                    "Queued intent for serial=%s (zone=%s) %s; resuming schedule",
                    serial,
                    intent.zone_id,
                    "(resume)" if intent.resume_schedule else "expired while offline",
                )
                resume_zones.setdefault(intent.zone_id, []).append(serial)
                continue

            remaining = intent.remaining_s()
            effective_state = "overlay" if intent.temperature is not None else "off"
            _LOGGER.info(
                "Replaying queued intent for serial=%s (zone=%s, %s,"
                " power=%s, temperature=%s%s)",
                serial,
                intent.zone_id,
                effective_state,
                intent.power,
                intent.temperature,
                f", remaining={remaining:.0f}s" if remaining is not None else "",
            )
            replay_tasks.append(self._async_replay(serial, intent))

        if resume_zones:
            if self._recovery_cloud_replay_enabled():
                for zone_id, members in resume_zones.items():
                    _LOGGER.debug(
                        "Resending resume schedule via cloud for zone=%s (%d serial(s))",
                        zone_id,
                        len(members),
                    )
                    replay_tasks.append(self._coordinator.async_set_zone_auto(zone_id))
            else:
                _LOGGER.debug(
                    "Skipping cloud resend for resume schedule"
                    " (recovery_cloud_replay=False) zones=%s",
                    sorted(resume_zones),
                )

        if replay_tasks:
            await asyncio.gather(*replay_tasks)

    def _recovery_cloud_replay_enabled(self) -> bool:
        """Config gate: whether resume schedules are resent via the cloud."""
        return bool(getattr(self._coordinator, "_recovery_cloud_replay", True))

    async def _async_replay(self, serial: str, intent: QueuedIntent) -> None:
        """Apply one non-expired overlay to the recovered local climate entity."""
        entity_id = self._tracker.get_entity_id(serial)
        if entity_id is None:
            _LOGGER.warning(
                "No local climate entity for serial=%s; skipping local replay",
                serial,
            )
            return

        if intent.power == POWER_OFF or (
            intent.power == POWER_ON and intent.temperature == OFF_MAGIC_TEMP
        ):
            await async_set_off(self._hass, entity_id, blocking=True)
        elif intent.temperature is not None:
            await async_set_temperature(
                self._hass, entity_id, intent.temperature, blocking=True
            )
        else:
            _LOGGER.debug(
                "Nothing to replay for serial=%s (power=%s, temperature=None)",
                serial,
                intent.power,
            )
