"""Mathematical helpers for API quota and polling interval calculations."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, cast

from homeassistant.util import dt as dt_util

from ..const import (
    API_RESET_HOUR_START,
    API_RESET_MIN_PERCENT,
    API_RESET_MIN_PLANNING_HOURS,
    API_RESET_MAX_PLANNING_HOURS,
    API_RESET_MIDPOINT_MINUTE,
    MIN_AUTO_QUOTA_INTERVAL_S,
    SECONDS_PER_DAY,
    SECONDS_PER_HOUR,
)


def is_in_reset_safe_window(expected_hour: int | None = None) -> bool:
    """Check if current time (Berlin) is in the reset safe window.

    Args:
        expected_hour: Expected reset hour (default: 12 from constants)

    Returns:
        True if current hour matches expected reset hour (+/- 1h tolerance)

    """
    berlin_tz = dt_util.get_time_zone("Europe/Berlin")
    now_berlin = dt_util.now().astimezone(berlin_tz)
    hour: int = now_berlin.hour

    if expected_hour is None:
        expected_hour = API_RESET_HOUR_START

    # Allow +/- 1 hour tolerance (e.g., 11-13 for expected hour 12)
    return hour >= (expected_hour - 1) and hour <= (expected_hour + 1)


def check_quota_reset(
    limit: int,
    remaining: int,
    last_percent: float,
    threshold: float,
    min_reset_percent: float = API_RESET_MIN_PERCENT,
) -> tuple[bool, float]:
    """Check if a quota reset occurred based on percentage jump.

    Detects resets by observing a significant percentage jump, independent
    of time of day. This allows the system to learn different reset schedules.

    Args:
        limit: API quota limit
        remaining: Current remaining quota
        last_percent: Previous remaining percentage
        threshold: Recovery threshold to detect jump
        min_reset_percent: Minimum % to consider valid reset (default 80%)

    Returns:
        (is_detected, current_percent)

    """
    if limit <= 0:
        return False, 1.0

    current_percent = remaining / limit

    # Detect reset: percentage jumped above threshold AND is high enough
    # to be a real reset (prevents false positives from small fluctuations)
    is_detected = (
        last_percent < threshold
        and current_percent >= threshold
        and current_percent >= min_reset_percent
    )
    return is_detected, current_percent


def get_next_reset_time(
    expected_hour: int | None = None,
    expected_minute: int | None = None,
    last_reset: datetime | None = None,
) -> datetime:
    """Get the next expected quota reset time.

    Conservative strategy: Plan for MINIMUM 24h ahead. Finds the next expected
    reset window, but if it's less than 24h away, uses the following window.
    Better to poll too slowly and have quota remaining than to burn through
    quota too quickly.

    Args:
        expected_hour: Learned reset hour (None = use default 12)
        expected_minute: Learned reset minute (None = use default 30)
        last_reset: Last detected quota reset time (unused, kept for compatibility)

    Returns:
        Next expected quota reset time (minimum 24h in the future)

    """
    berlin_tz = dt_util.get_time_zone("Europe/Berlin")
    now_berlin = dt_util.now().astimezone(berlin_tz)

    # Use learned window or fallback to default
    reset_hour = expected_hour if expected_hour is not None else API_RESET_HOUR_START
    reset_minute = (
        expected_minute if expected_minute is not None else API_RESET_MIDPOINT_MINUTE
    )

    # Find next expected reset (today or tomorrow)
    expected_reset_today = now_berlin.replace(
        hour=reset_hour,
        minute=reset_minute,
        second=0,
        microsecond=0,
    )

    if expected_reset_today <= now_berlin:
        # Today's window already passed, use tomorrow
        next_expected = expected_reset_today + timedelta(days=1)
    else:
        # Today's window still ahead
        next_expected = expected_reset_today

    # Ensure MINIMUM planning horizon (conservative but not excessive)
    min_future = now_berlin + timedelta(hours=API_RESET_MIN_PLANNING_HOURS)

    if next_expected < min_future:
        candidate = next_expected + timedelta(days=1)
        max_future = now_berlin + timedelta(hours=API_RESET_MAX_PLANNING_HOURS)
        return cast(datetime, min(candidate, max_future))

    return cast(datetime, next_expected)


def get_seconds_until_reset(
    expected_hour: int | None = None,
    expected_minute: int | None = None,
    last_reset: datetime | None = None,
) -> int:
    """Get seconds until next API quota reset.

    Args:
        expected_hour: Learned reset hour (None = use default)
        expected_minute: Learned reset minute (None = use default)
        last_reset: Last detected quota reset time (if any)

    Returns:
        Seconds until next reset

    """
    reset_time = get_next_reset_time(expected_hour, expected_minute, last_reset)
    return int((reset_time - dt_util.now()).total_seconds())


def calculate_remaining_polling_budget(
    limit: int,
    remaining: int,
    background_cost_24h: int,
    throttle_threshold: int,
    auto_quota_percent: int,
    seconds_until_reset: int,
    safety_reserve: int = 0,
) -> float:
    """Calculate the remaining API budget for the rest of the day.

    Args:
        limit: Daily API quota limit
        remaining: Current remaining quota
        background_cost_24h: Estimated background cost for 24h
        throttle_threshold: Reserve threshold for external use
        auto_quota_percent: Percentage of quota to use for polling
        seconds_until_reset: Seconds until next quota reset
        safety_reserve: API calls reserved for reset window (12-13h)

    Returns:
        Remaining budget for adaptive polling (excludes safety reserve)

    """
    if remaining <= 0:
        return 0.0

    progress_remaining = seconds_until_reset / SECONDS_PER_DAY

    reserved_background = background_cost_24h * progress_remaining
    potentially_free = remaining - reserved_background - throttle_threshold

    if potentially_free <= 0:
        return 0.0

    # Calculate budget from quota percentage, then subtract safety reserve
    budget = potentially_free * (auto_quota_percent / 100.0)
    return max(0.0, budget - safety_reserve)


def calculate_safety_reserve_interval(safety_reserve: int) -> int:
    """Calculate polling interval during reset window using safety reserve.

    Safety reserve is distributed evenly during the reset window (12:00-13:00).

    Args:
        safety_reserve: Number of API calls reserved for reset window

    Returns:
        Interval in seconds between safety reserve polls

    """
    if safety_reserve <= 0:
        return SECONDS_PER_HOUR  # No safety reserve, use max interval

    # Distribute safety reserve over 1 hour (reset window duration)
    return SECONDS_PER_HOUR // safety_reserve


def calculate_weighted_interval(
    remaining_budget: float,
    predicted_poll_cost: float,
    is_in_reduced_window_func: Any,
    reduced_window_conf: dict[str, Any],
    min_floor: int,
    expected_hour: int | None = None,
    expected_minute: int | None = None,
    last_reset: datetime | None = None,
) -> int:
    """Calculate weighted interval for performance hours (reinvesting savings).

    Args:
        remaining_budget: Available API budget
        predicted_poll_cost: Estimated cost per poll
        is_in_reduced_window_func: Function to check reduced window
        reduced_window_conf: Reduced polling configuration
        min_floor: Minimum allowed interval
        expected_hour: Learned reset hour (None = use default)
        expected_minute: Learned reset minute (None = use default)
        last_reset: Last detected quota reset time (if any)

    Returns:
        Calculated polling interval in seconds

    """
    try:
        now = dt_util.now()
        next_reset = get_next_reset_time(expected_hour, expected_minute, last_reset)

        # Calculate total normal and reduced seconds until next reset
        normal_seconds = 0
        reduced_seconds = 0
        test_dt = now
        while test_dt < next_reset:
            chunk = max(
                MIN_AUTO_QUOTA_INTERVAL_S,
                min(SECONDS_PER_HOUR, int((next_reset - test_dt).total_seconds())),
            )
            if is_in_reduced_window_func(test_dt, reduced_window_conf):
                reduced_seconds += chunk
            else:
                normal_seconds += chunk
            test_dt += timedelta(seconds=chunk)

        reduced_interval = reduced_window_conf["interval"]

        if reduced_interval == 0:
            reduced_budget_cost = 0.0
        else:
            reduced_polls_needed = reduced_seconds / reduced_interval
            reduced_budget_cost = reduced_polls_needed * predicted_poll_cost

        # All remaining budget goes to performance (normal) hours
        normal_budget = max(0, remaining_budget - reduced_budget_cost)

        if normal_budget > 0:
            normal_polls = normal_budget / predicted_poll_cost
            if normal_polls > 0:
                adaptive_interval = normal_seconds / normal_polls
                cap = reduced_interval if reduced_interval > 0 else SECONDS_PER_HOUR
                return int(max(min_floor, min(cap, adaptive_interval)))

        return SECONDS_PER_HOUR

    except Exception:
        return int(max(min_floor, SECONDS_PER_HOUR))
