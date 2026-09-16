"""Manages API rate limits and throttling logic."""

from __future__ import annotations

from typing import Any, Protocol

from ..const import INITIAL_RATE_LIMIT_GUESS, RATELIMIT_SMOOTHING_ALPHA
from .logging_utils import get_redacted_logger

_LOGGER = get_redacted_logger(__name__)


class RateLimitSource(Protocol):
    """Protocol for the rate limit data source."""

    rate_limit_data: dict[str, Any]


class RateLimitManager:
    """Manages API quota tracking and throttling logic."""

    def __init__(
        self, throttle_threshold: int, data_source: RateLimitSource | None = None
    ) -> None:
        """Initialize the manager."""
        self._throttle_threshold = throttle_threshold
        self._internal_remaining: int = INITIAL_RATE_LIMIT_GUESS
        self._sources: list[RateLimitSource] = []
        if data_source is not None:
            self._sources.append(data_source)

        self._last_poll_cost: float = 2.0

    def add_source(self, source: RateLimitSource) -> None:
        """Watch another header source (v2 handler and Hops both count)."""
        if source not in self._sources:
            self._sources.append(source)

    def _latest_header_data(self) -> dict[str, Any] | None:
        latest: dict[str, Any] | None = None
        latest_ts = -1.0
        for source in self._sources:
            data = source.rate_limit_data
            if "remaining" not in data:
                continue
            ts = float(data.get("updated_at") or 0)
            if ts >= latest_ts:
                latest_ts = ts
                latest = data
        return latest

    @property
    def last_poll_cost(self) -> float:
        """Return the measured cost of the last successful polling cycle."""
        return max(1.0, self._last_poll_cost)

    @last_poll_cost.setter
    def last_poll_cost(self, value: float) -> None:
        """Update measured poll cost with light smoothing to avoid jitter."""
        if value > 0:
            # Smoothing (EMA) using constant alpha
            alpha = RATELIMIT_SMOOTHING_ALPHA
            self._last_poll_cost = (self._last_poll_cost * (1 - alpha)) + (
                value * alpha
            )
            _LOGGER.debug("Updated measured poll cost to %.2f", self._last_poll_cost)

    @property
    def is_throttled(self) -> bool:
        """Return True if throttling is active."""
        if self._throttle_threshold == 0:
            return False
        return self._internal_remaining < self._throttle_threshold

    @property
    def api_status(self) -> str:
        """Return current API status string."""
        if self._internal_remaining <= 0:
            return "rate_limited"
        return "throttled" if self.is_throttled else "connected"

    @property
    def throttle_threshold(self) -> int:
        """Return the configured throttle threshold."""
        return self._throttle_threshold

    @property
    def remaining(self) -> int:
        """Return estimated remaining calls."""
        return self._internal_remaining

    @property
    def limit(self) -> int:
        """Return total limit from the newest header source."""
        if data := self._latest_header_data():
            return int(data.get("limit") or 0)
        return 0

    def decrement(self, count: int = 1) -> None:
        """Decrement internal counter (e.g. during throttling)."""
        self._internal_remaining = max(0, self._internal_remaining - count)
        _LOGGER.debug("Internal remaining decremented to %d", self._internal_remaining)

    def sync_from_headers(self) -> None:
        """Sync internal counter from the most recently updated header source."""
        data = self._latest_header_data()
        if data is None:
            return
        header_remaining = int(data.get("remaining", self._internal_remaining))
        if header_remaining != self._internal_remaining:
            _LOGGER.debug(
                "Quota remaining %d -> %d (header source updated_at=%.3f)",
                self._internal_remaining,
                header_remaining,
                float(data.get("updated_at") or 0),
            )
            self._internal_remaining = header_remaining
