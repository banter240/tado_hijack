"""Adaptive API quota reset window tracker.

Learns the actual daily quota reset time by observing reset patterns.
Tado's API reset time varies between users (7:30, 12:04, etc.) and this
tracker adapts to the user's specific reset schedule.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from ..const import (
    API_RESET_HISTORY_SIZE,
    API_RESET_HOUR_START,
    API_RESET_MIDPOINT_MINUTE,
    API_RESET_MIN_PLANNING_HOURS,
    API_RESET_PATTERN_THRESHOLD,
)


@dataclass
class ResetWindow:
    """Learned reset window configuration."""

    hour: int
    minute: int
    confidence: str

    def __str__(self) -> str:
        """Return formatted reset window string."""
        return f"{self.hour:02d}:{self.minute:02d} ({self.confidence})"


class ResetWindowTracker:
    """Tracks quota reset patterns and learns the actual reset window.

    Tado's API quota resets daily but the exact time varies by user.
    This tracker observes reset events and learns the pattern:

    - Single reset: Noted but not adopted (might be anomaly)
    - 2+ consecutive resets at same hour: Pattern learned, window updated
    - No pattern: Falls back to default 12:30

    """

    def __init__(
        self,
        default_hour: int = API_RESET_HOUR_START,
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
        """Get or create a static initial target for new setups."""
        if self._initial_target is None:
            berlin_tz = dt_util.get_time_zone("Europe/Berlin")
            now_berlin = dt_util.now().astimezone(berlin_tz)

            target = now_berlin.replace(
                hour=self._default_hour,
                minute=self._default_minute,
                second=0,
                microsecond=0,
            )

            if target <= now_berlin:
                target += timedelta(days=1)

            if (target - now_berlin).total_seconds() < (
                API_RESET_MIN_PLANNING_HOURS * 3600
            ):
                target += timedelta(days=1)

            self._initial_target = target

        return self._initial_target

    def record_reset(self, reset_time: datetime) -> None:
        """Record a detected quota reset.

        Stores both original time (for display) and normalized time (for pattern learning).
        Normalizes to X:30 to group resets in the same hour (e.g., 7:03, 7:35 → both 7:30).
        """
        berlin_tz = dt_util.get_time_zone("Europe/Berlin")
        reset_berlin = reset_time.astimezone(berlin_tz)

        self._history_original.appendleft(reset_berlin)

        normalized = reset_berlin.replace(
            minute=API_RESET_MIDPOINT_MINUTE, second=0, microsecond=0
        )

        self._history.appendleft(normalized)
        self._update_learned_window()

    def _update_learned_window(self) -> None:
        """Analyze history and update learned window if pattern detected."""
        if len(self._history) == 0:
            return

        if len(self._history) < self._pattern_threshold:
            first = self._history[0]
            self._learned_window = ResetWindow(
                hour=first.hour,
                minute=first.minute,
                confidence="single_observation",
            )
            return

        recent_resets = list(self._history)[: self._pattern_threshold]
        reset_hours = [r.hour for r in recent_resets]

        if len(set(reset_hours)) == 1:
            pattern_hour = reset_hours[0]
            same_hour_resets = [r for r in recent_resets if r.hour == pattern_hour]
            avg_minute = sum(r.minute for r in same_hour_resets) // len(
                same_hour_resets
            )

            self._learned_window = ResetWindow(
                hour=pattern_hour,
                minute=avg_minute,
                confidence="learned",
            )

    def get_expected_window(self) -> ResetWindow:
        """Get the expected reset window."""
        if self._learned_window and self._learned_window.confidence == "learned":
            return self._learned_window

        return ResetWindow(
            hour=self._default_hour,
            minute=self._default_minute,
            confidence="default",
        )

    def get_reset_history(self) -> list[datetime]:
        """Get reset history (newest first)."""
        return list(self._history)

    def get_last_reset(self) -> datetime | None:
        """Get most recent reset time (normalized)."""
        return self._history[0] if self._history else None

    def get_last_reset_original(self) -> datetime | None:
        """Get most recent reset time (original)."""
        return self._history_original[0] if self._history_original else None

    def get_next_reset_time(self) -> datetime:
        """Get the absolute next expected reset time."""
        berlin_tz = dt_util.get_time_zone("Europe/Berlin")
        now_berlin = dt_util.now().astimezone(berlin_tz)

        window = self.get_expected_window()
        last_reset = self.get_last_reset_original()

        if last_reset is None:
            return self.get_initial_target()

        last_reset_berlin = last_reset.astimezone(berlin_tz)
        next_reset = (last_reset_berlin + timedelta(days=1)).replace(
            hour=window.hour,
            minute=window.minute,
            second=0,
            microsecond=0,
        )

        if next_reset <= now_berlin:
            next_reset += timedelta(days=1)

        return next_reset

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

    def to_dict(self) -> dict[str, Any]:
        """Serialize tracker state to dictionary."""
        return {
            "history": [dt.isoformat() for dt in self._history],
            "history_original": [dt.isoformat() for dt in self._history_original],
            "learned_window": (
                {
                    "hour": self._learned_window.hour,
                    "minute": self._learned_window.minute,
                    "confidence": self._learned_window.confidence,
                }
                if self._learned_window
                else None
            ),
            "initial_target": self._initial_target.isoformat()
            if self._initial_target
            else None,
        }

    def _load_history_from_list(
        self, history_list: list[str], target_deque: deque[datetime]
    ) -> None:
        """Load history from ISO string list into deque."""
        for iso_str in reversed(history_list):
            if dt := dt_util.parse_datetime(iso_str):
                target_deque.appendleft(dt)

    def load_dict(self, data: dict[str, Any] | None) -> None:
        """Load tracker state from dictionary."""
        if not data:
            return

        self._history.clear()
        self._history_original.clear()

        history_list = data.get("history", [])
        self._load_history_from_list(history_list, self._history)

        # Fallback to normalized if not present for backwards compat
        history_original_list = data.get("history_original", history_list)
        self._load_history_from_list(history_original_list, self._history_original)

        if lw_data := data.get("learned_window"):
            self._learned_window = ResetWindow(
                hour=lw_data.get("hour", self._default_hour),
                minute=lw_data.get("minute", self._default_minute),
                confidence=lw_data.get("confidence", "default"),
            )

        if initial_target_str := data.get("initial_target"):
            self._initial_target = dt_util.parse_datetime(initial_target_str)
