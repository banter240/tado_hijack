"""Last intended zone state per offline local TRV serial.

The cloud command is still sent. This queue only exists so a HomeKit or Matter
device that was unavailable can be caught up when it returns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.util import dt as dt_util

from .logging_utils import get_redacted_logger
from .zone_utils import trv_serials

if TYPE_CHECKING:
    from ..coordinator import TadoDataUpdateCoordinator
    from .availability_tracker import AvailabilityTracker

_LOGGER = get_redacted_logger(__name__)


@dataclass(frozen=True)
class QueuedIntent:
    """One captured intent. expires_at is when it should already be back on schedule."""

    zone_id: int
    enqueued_at: datetime = field(default_factory=dt_util.utcnow)
    power: str | None = None
    temperature: float | None = None
    resume_schedule: bool = False
    expires_at: datetime | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def is_expired(self, now: datetime | None = None) -> bool:
        """True if the intent's deadline has passed (should be on schedule now)."""
        if self.expires_at is None:
            return False
        if now is None:
            now = dt_util.utcnow()
        return now >= self.expires_at

    def remaining_s(self, now: datetime | None = None) -> float | None:
        """Remaining seconds until expiry, or None if no deadline."""
        if self.expires_at is None:
            return None
        if now is None:
            now = dt_util.utcnow()
        return max(0.0, (self.expires_at - now).total_seconds())


class LocalRecoveryQueue:
    """Per-serial last-wins store. Only unavailable local serials get an entry."""

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        availability_tracker: AvailabilityTracker,
    ) -> None:
        """Initialize the queue with its coordinator and tracker."""
        self._coordinator = coordinator
        self._tracker = availability_tracker
        self._entries: dict[str, QueuedIntent] = {}

    def capture(
        self,
        zone_id: int,
        *,
        power: str | None = None,
        temperature: float | None = None,
        resume_schedule: bool = False,
        expiry_s: float | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Store the latest intent for every unavailable serial of the zone.

        expiry_s is the open-window or overlay duration. After it passes, recovery
        resumes the schedule instead of replaying the stale overlay.
        """
        now = dt_util.utcnow()
        expires_at = now + timedelta(seconds=expiry_s) if expiry_s is not None else None
        intent = QueuedIntent(
            zone_id=zone_id,
            enqueued_at=now,
            power=power,
            temperature=temperature,
            resume_schedule=resume_schedule,
            expires_at=expires_at,
            meta=dict(meta or {}),
        )

        for serial in self.zone_serials(zone_id):
            if self._tracker.is_available(serial):
                self._entries.pop(serial, None)
                continue
            prev = self._entries.get(serial)
            self._entries[serial] = intent
            if prev is not None and prev.resume_schedule and not intent.resume_schedule:
                _LOGGER.debug(
                    "Recovery queue serial=%s: replaced resume intent with overlay intent",
                    serial,
                )

    def capture_overlay(
        self,
        zone_id: int,
        power: str | None,
        temperature: float | None,
        expiry_s: float | None = None,
    ) -> None:
        """Convenience wrapper for overlay intents (temp/off/window-off/timer)."""
        self.capture(
            zone_id,
            power=power,
            temperature=temperature,
            expiry_s=expiry_s,
        )

    def capture_resume(self, zone_id: int) -> None:
        """Convenience wrapper for resume-schedule intents (cloud-only)."""
        self.capture(zone_id, resume_schedule=True)

    def zone_serials(self, zone_id: int) -> list[str]:
        """Return all TRV serials of a zone."""
        return trv_serials(self._coordinator.zones_meta, zone_id)

    def pop(self, serial: str) -> QueuedIntent | None:
        """Remove and return the latest intent for a serial (None if empty)."""
        return self._entries.pop(serial, None)

    def peek(self, serial: str) -> QueuedIntent | None:
        """Return the latest intent for a serial without removing it."""
        return self._entries.get(serial)

    @property
    def pending_serials(self) -> set[str]:
        """Return serials with a queued intent."""
        return set(self._entries)

    def clear(self) -> None:
        """Drop all queued intents (e.g. on shutdown)."""
        self._entries.clear()
