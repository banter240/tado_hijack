"""Adaptive API quota reset window tracker.

Learns the actual daily quota reset time by observing reset patterns.
Tado's API reset time varies between users (7:30, 12:04, etc.) and this
tracker adapts to the user's specific reset schedule.

History is stored in UTC to remain stable across DST transitions. The
learned window hour/minute are UTC values. Display conversions to Berlin
local time happen only in __str__ and sensor value_fn.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from ..const import (
    API_RESET_DEFAULT_UTC_HOUR,
    API_RESET_HISTORY_SIZE,
    API_RESET_MIDPOINT_MINUTE,
    API_RESET_MIN_PLANNING_HOURS,
    API_RESET_PATTERN_THRESHOLD,
)


@dataclass
class ResetWindow:
    """Learned reset window configuration.

    hour/minute are in UTC. __str__ converts to Berlin local time for display.
    """

    hour: int
    minute: int
    confidence: str

    def __str__(self) -> str:
        """Return formatted reset window string in Berlin local time."""
        try:
            berlin_tz = dt_util.get_time_zone("Europe/Berlin")
            now_utc = dt_util.now().astimezone(UTC)
            ref = now_utc.replace(
                hour=self.hour, minute=self.minute, second=0, microsecond=0
            )
            ref_berlin = ref.astimezone(berlin_tz)
            return f"{ref_berlin.hour:02d}:{ref_berlin.minute:02d} ({self.confidence})"
        except Exception:
            return f"{self.hour:02d}:{self.minute:02d} UTC ({self.confidence})"


class ResetWindowTracker:
    """Tracks quota reset patterns and learns the actual reset window.

    Tado's API quota resets daily but the exact time varies by user.
    This tracker observes reset events and learns the pattern:

    - 2+ consecutive resets at same UTC hour: Pattern confirmed, _learned_window updated
    - Single reset or pattern break: _learned_window kept unchanged (outlier protection)
    - No confirmed pattern: Falls back to default UTC hour (API_RESET_DEFAULT_UTC_HOUR)

    A confirmed learned window is only replaced once a NEW pattern accumulates
    >= pattern_threshold consecutive resets at the new hour. This prevents a
    one-off outlier reset from disrupting a stable, confirmed schedule.

    """

    def __init__(
        self,
        default_hour: int = API_RESET_DEFAULT_UTC_HOUR,
        default_minute: int = API_RESET_MIDPOINT_MINUTE,
        history_size: int = API_RESET_HISTORY_SIZE,
        pattern_threshold: int = API_RESET_PATTERN_THRESHOLD,
    ) -> None:
        """Initialize reset window tracker."""
        self._default_hour = default_hour
        self._default_minute = default_minute
        self._pattern_threshold = pattern_threshold

        self._history: deque[datetime] = deque(maxlen=history_size)
        self._history_original: deque[datetime] = deque(maxlen=history_size)

        self._learned_window: ResetWindow | None = None
        self._initial_target: datetime | None = None

    def get_initial_target(self) -> datetime:
        """Get or compute a future initial target for setups without reset history.

        Re-computes whenever the cached value is in the past (e.g. after loading
        stale persistent state or when HA was offline for over 24 h).
        """
        berlin_tz = dt_util.get_time_zone("Europe/Berlin")
        now_utc = dt_util.now().astimezone(UTC)

        if (
            self._initial_target is not None
            and self._initial_target.astimezone(UTC) > now_utc
        ):
            return self._initial_target

        target_utc = now_utc.replace(
            hour=self._default_hour,
            minute=self._default_minute,
            second=0,
            microsecond=0,
        )

        if target_utc <= now_utc:
            target_utc += timedelta(days=1)

        if (target_utc - now_utc).total_seconds() < (
            API_RESET_MIN_PLANNING_HOURS * 3600
        ):
            target_utc += timedelta(days=1)

        self._initial_target = target_utc.astimezone(berlin_tz)
        return self._initial_target

    def record_reset(self, reset_time: datetime) -> None:
        """Record a detected quota reset.

        Stores original time in Berlin tz (for display) and normalized UTC
        time (for pattern learning). Normalizing in UTC keeps the learned
        hour stable across DST transitions.
        """
        berlin_tz = dt_util.get_time_zone("Europe/Berlin")
        reset_berlin = reset_time.astimezone(berlin_tz)
        self._history_original.appendleft(reset_berlin)

        # Normalize in UTC so DST transitions don't shift the learned hour
        reset_utc = reset_time.astimezone(UTC)
        normalized_utc = reset_utc.replace(
            minute=API_RESET_MIDPOINT_MINUTE, second=0, microsecond=0
        )
        self._history.appendleft(normalized_utc)
        self._update_learned_window()

    def _update_learned_window(self) -> None:
        """Analyze history and update learned window only when pattern is confirmed.

        A confirmed _learned_window is never overwritten by a single outlier.
        On a pattern break the history is trimmed to the newest entry so the
        tracker can accumulate fresh confirmations, but _learned_window is left
        untouched until >= pattern_threshold consecutive resets agree on a new hour.
        """
        if not self._history:
            return

        recent = list(self._history)[: self._pattern_threshold]
        first = recent[0]

        if len(recent) >= self._pattern_threshold and first.hour != recent[1].hour:
            newest_original = (
                self._history_original[0] if self._history_original else None
            )
            self._history.clear()
            self._history_original.clear()
            self._history.appendleft(first)
            if newest_original is not None:
                self._history_original.appendleft(newest_original)
            return

        if len(self._history) < self._pattern_threshold:
            return

        reset_hours = [r.hour for r in recent]
        if len(set(reset_hours)) == 1:
            # minute is always 30 — record_reset normalizes all UTC entries to :30
            self._learned_window = ResetWindow(
                hour=reset_hours[0], minute=recent[0].minute, confidence="learned"
            )

    def _default_utc_window(self) -> tuple[int, int]:
        """Return the default UTC reset hour and minute."""
        return self._default_hour, self._default_minute

    def get_expected_window(self) -> ResetWindow:
        """Get the expected reset window (hour/minute in UTC)."""
        if self._learned_window and self._learned_window.confidence == "learned":
            return self._learned_window
        hour_utc, minute_utc = self._default_utc_window()
        return ResetWindow(hour=hour_utc, minute=minute_utc, confidence="default")

    def get_reset_history(self) -> list[datetime]:
        """Get reset history (newest first)."""
        return list(self._history)

    def get_last_reset(self) -> datetime | None:
        """Get most recent reset time (normalized UTC)."""
        return self._history[0] if self._history else None

    def get_last_reset_original(self) -> datetime | None:
        """Get most recent reset time (original Berlin tz)."""
        return self._history_original[0] if self._history_original else None

    def get_next_reset_time(self) -> datetime:
        """Get the absolute next expected reset time in Berlin tz."""
        berlin_tz = dt_util.get_time_zone("Europe/Berlin")
        now_utc = dt_util.now().astimezone(UTC)

        if not self._history:
            return self.get_initial_target()

        next_reset_utc = self._history[0] + timedelta(days=1)
        while next_reset_utc <= now_utc:
            next_reset_utc += timedelta(days=1)

        return next_reset_utc.astimezone(berlin_tz)

    @property
    def history_count(self) -> int:
        """Return number of recorded resets."""
        return len(self._history)

    @property
    def is_learned(self) -> bool:
        """Check if reset window has been learned from observed patterns."""
        return (
            self._learned_window is not None
            and self._learned_window.confidence == "learned"
        )

    # Bump this when the storage format changes incompatibly.
    # v1 → v2: history entries migrated from Berlin-local tz to UTC.
    DATA_VERSION = 2

    def to_dict(self) -> dict[str, Any]:
        """Serialize tracker state to dictionary."""
        return {
            "data_version": self.DATA_VERSION,
            "history": [dt.isoformat() for dt in self._history],
            "history_original": [dt.isoformat() for dt in self._history_original],
            "learned_window": (
                {
                    "hour": self._learned_window.hour,
                    "minute": self._learned_window.minute,
                }
                if self._learned_window
                else None
            ),
            "initial_target": self._initial_target.isoformat()
            if self._initial_target
            else None,
        }

    def _load_history_from_list(
        self,
        history_list: list[str],
        target_deque: deque[datetime],
    ) -> None:
        """Load history from ISO string list into deque."""
        for iso_str in reversed(history_list):
            if dt := dt_util.parse_datetime(iso_str):
                target_deque.appendleft(dt)

    def load_dict(self, data: dict[str, Any] | None) -> None:
        """Load tracker state from dictionary.

        History is expected to be in UTC format (v2+). The one-time migration
        from Berlin local time to UTC is handled by config entry migration v10
        in helpers/migration.py, which runs before the coordinator loads.
        """
        if not data:
            return

        self._history.clear()
        self._history_original.clear()

        history_list = data.get("history", [])
        self._load_history_from_list(history_list, self._history)

        history_original_list = data.get("history_original", history_list)
        self._load_history_from_list(history_original_list, self._history_original)

        if lw := data.get("learned_window"):
            if isinstance(lw, dict) and "hour" in lw and "minute" in lw:
                self._learned_window = ResetWindow(
                    hour=lw["hour"], minute=lw["minute"], confidence="learned"
                )

        if initial_target_str := data.get("initial_target"):
            self._initial_target = dt_util.parse_datetime(initial_target_str) or None

        self._update_learned_window()
