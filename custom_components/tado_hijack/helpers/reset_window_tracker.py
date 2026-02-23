"""Adaptive API quota reset window tracker.

Learns the actual daily quota reset time by observing reset patterns.
Tado's API reset time varies between users (7:30, 12:04, etc.) and this
tracker adapts to the user's specific reset schedule.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

from ..const import (
    API_RESET_HISTORY_SIZE,
    API_RESET_HOUR_START,
    API_RESET_MIDPOINT_MINUTE,
    API_RESET_PATTERN_THRESHOLD,
)


@dataclass
class ResetWindow:
    """Learned reset window configuration."""

    hour: int
    minute: int
    confidence: str  # "learned", "default", "single_observation"

    def __str__(self) -> str:
        """Human-readable representation."""
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
        """Initialize tracker.

        Args:
            default_hour: Default reset hour (from constants)
            default_minute: Default reset minute (from constants)
            history_size: Number of resets to keep in history (from constants)
            pattern_threshold: Consecutive resets needed to learn new window (from constants)

        """
        self._default_hour = default_hour
        self._default_minute = default_minute
        self._pattern_threshold = pattern_threshold

        # Circular buffer of last N reset times (most recent first)
        self._history: deque[datetime] = deque(maxlen=history_size)

        # Learned window (None = use default)
        self._learned_window: ResetWindow | None = None

    def record_reset(self, reset_time: datetime) -> None:
        """Record a detected quota reset.

        Normalizes reset time to X:30 (midpoint of hour X) to group
        resets that occur in the same hour (e.g., 7:03, 7:35 → both 7:30).

        Args:
            reset_time: When the reset was detected

        """
        berlin_tz = dt_util.get_time_zone("Europe/Berlin")
        reset_berlin = reset_time.astimezone(berlin_tz)

        # Normalize to X:30 (midpoint of the hour, from constants)
        normalized = reset_berlin.replace(
            minute=API_RESET_MIDPOINT_MINUTE, second=0, microsecond=0
        )

        # Add to history (newest first)
        self._history.appendleft(normalized)

        # Re-evaluate learned window
        self._update_learned_window()

    def _update_learned_window(self) -> None:
        """Analyze history and update learned window if pattern detected."""
        if len(self._history) < self._pattern_threshold:
            return  # Not enough data

        # Check if last N resets are at the same hour
        recent_resets = list(self._history)[: self._pattern_threshold]
        reset_hours = [r.hour for r in recent_resets]

        # Pattern detected: All recent resets at same hour
        if len(set(reset_hours)) == 1:
            pattern_hour = reset_hours[0]

            # Calculate average minute for this hour
            same_hour_resets = [r for r in recent_resets if r.hour == pattern_hour]
            avg_minute = sum(r.minute for r in same_hour_resets) // len(
                same_hour_resets
            )

            # Learn this window
            self._learned_window = ResetWindow(
                hour=pattern_hour,
                minute=avg_minute,
                confidence="learned",
            )
        elif len(self._history) == 1:
            # Single observation - note but don't adopt
            first = self._history[0]
            self._learned_window = ResetWindow(
                hour=first.hour,
                minute=first.minute,
                confidence="single_observation",
            )

    def get_expected_window(self) -> ResetWindow:
        """Get the expected reset window.

        Returns:
            ResetWindow with hour, minute, and confidence level

        """
        if self._learned_window and self._learned_window.confidence == "learned":
            return self._learned_window

        # No learned pattern, use default
        return ResetWindow(
            hour=self._default_hour,
            minute=self._default_minute,
            confidence="default",
        )

    def get_reset_history(self) -> list[datetime]:
        """Get reset history (newest first).

        Returns:
            List of recorded reset times

        """
        return list(self._history)

    def get_last_reset(self) -> datetime | None:
        """Get the most recent reset time.

        Returns:
            Most recent reset time or None if no history

        """
        return self._history[0] if self._history else None

    @property
    def history_count(self) -> int:
        """Number of resets in history."""
        return len(self._history)

    @property
    def is_learned(self) -> bool:
        """Check if reset window has been learned from observed patterns.

        Returns:
            True if pattern learned from 2+ consecutive resets, False otherwise

        """
        return (
            self._learned_window is not None
            and self._learned_window.confidence == "learned"
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize tracker state to dictionary."""
        return {
            "history": [dt.isoformat() for dt in self._history],
            "learned_window": (
                {
                    "hour": self._learned_window.hour,
                    "minute": self._learned_window.minute,
                    "confidence": self._learned_window.confidence,
                }
                if self._learned_window
                else None
            ),
        }

    def load_dict(self, data: dict[str, Any] | None) -> None:
        """Load tracker state from dictionary."""
        if not data:
            return

        self._history.clear()

        history_list = data.get("history", [])
        for iso_str in reversed(history_list):
            if dt := dt_util.parse_datetime(iso_str):
                self._history.appendleft(dt)

        if lw_data := data.get("learned_window"):
            self._learned_window = ResetWindow(
                hour=lw_data.get("hour", self._default_hour),
                minute=lw_data.get("minute", self._default_minute),
                confidence=lw_data.get("confidence", "default"),
            )
