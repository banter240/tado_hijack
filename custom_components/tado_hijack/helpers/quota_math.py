"""Mathematical helpers for API quota and polling interval calculations."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, cast

from homeassistant.util import dt as dt_util

from ..const import (
    API_RESET_HOUR_START,
    API_RESET_MIN_PERCENT,
    API_RESET_MIN_PLANNING_HOURS,
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
    last_remaining: int | None,
    min_reset_percent: float = API_RESET_MIN_PERCENT,
) -> bool:
    """Check if a quota reset occurred by detecting any increase in remaining quota.

    Since API quota can only decrease through usage, any upward movement
    unambiguously signals a reset. The min_reset_percent guard prevents false
    positives from throttled (0→1) edge cases.

    Args:
        limit: API quota limit
        remaining: Current remaining quota
        last_remaining: Previous remaining quota (None = first observation)
        min_reset_percent: Minimum % the new remaining must reach to count as reset

    Returns:
        True if a quota reset was detected

    """
    if limit <= 0 or last_remaining is None:
        return False

    return remaining > last_remaining and (remaining / limit) >= min_reset_percent


def get_next_reset_time(
    expected_hour: int | None = None,
    expected_minute: int | None = None,
    last_reset: datetime | None = None,
) -> datetime:
    """Get the next expected quota reset time.

    Strategy:
    - If last_reset exists: Calculate based on last_reset + 24h with learned window
    - If no last_reset (new installation): Use now + MIN_PLANNING_HOURS as initial value

    Args:
        expected_hour: Learned reset hour (None = use default 12)
        expected_minute: Learned reset minute (None = use default 30)
        last_reset: Last detected quota reset time (original, not normalized)

    Returns:
        Next expected quota reset time

    """
    berlin_tz = dt_util.get_time_zone("Europe/Berlin")
    now_berlin = dt_util.now().astimezone(berlin_tz)

    # Use learned window or fallback to default
    reset_hour = expected_hour if expected_hour is not None else API_RESET_HOUR_START
    reset_minute = (
        expected_minute if expected_minute is not None else API_RESET_MIDPOINT_MINUTE
    )

    # No last reset (new installation): Use conservative initial estimate
    if last_reset is None:
        initial_estimate = now_berlin + timedelta(hours=API_RESET_MIN_PLANNING_HOURS)
        return cast(
            datetime,
            initial_estimate.replace(minute=reset_minute, second=0, microsecond=0),
        )

    # Have last reset: Calculate next reset based on it
    last_reset_berlin = last_reset.astimezone(berlin_tz)

    # Next reset is last_reset + 24h, adjusted to learned window time
    next_reset = (last_reset_berlin + timedelta(days=1)).replace(
        hour=reset_hour,
        minute=reset_minute,
        second=0,
        microsecond=0,
    )

    # If next reset already passed, add another day
    if next_reset <= now_berlin:
        next_reset = next_reset + timedelta(days=1)

    return next_reset


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
    """Calculate remaining API budget for the rest of the day.

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
    if remaining <= 0 or limit <= 0:
        return 0.0

    progress_remaining = seconds_until_reset / SECONDS_PER_DAY

    base_daily_budget = (limit - background_cost_24h - throttle_threshold) * (
        auto_quota_percent / 100.0
    )
    if base_daily_budget <= 0:
        return 0.0

    calls_consumed = max(0, limit - remaining)
    background_consumed = background_cost_24h * (1.0 - progress_remaining)

    # Raise the floor when external usage has consumed more than the reserved threshold.
    expected_polling_consumed = base_daily_budget * (1.0 - progress_remaining)
    inferred_external = max(
        0.0, float(calls_consumed) - background_consumed - expected_polling_consumed
    )
    effective_threshold = max(float(throttle_threshold), inferred_external)

    max_daily_poll_budget = max(
        0.0,
        (limit - background_cost_24h - effective_threshold)
        * (auto_quota_percent / 100.0),
    )
    if max_daily_poll_budget <= 0:
        return 0.0

    polling_consumed = max(0.0, float(calls_consumed) - background_consumed)
    planned_budget = max(0.0, max_daily_poll_budget - polling_consumed)

    future_bg = background_cost_24h * progress_remaining
    available_now = max(0.0, remaining - throttle_threshold - future_bg)

    budget = min(planned_budget, available_now)
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
