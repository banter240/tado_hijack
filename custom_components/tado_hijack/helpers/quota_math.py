"""Mathematical helpers for API quota and polling interval calculations."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, cast

from homeassistant.util import dt as dt_util

from ..const import (
    API_RESET_BUFFER_MINUTES,
    API_RESET_HOUR,
    MIN_AUTO_QUOTA_INTERVAL_S,
    SECONDS_PER_DAY,
    SECONDS_PER_HOUR,
)


def get_next_reset_time() -> datetime:
    """Get the next API quota reset time (12:01 AM Berlin)."""
    berlin_tz = dt_util.get_time_zone("Europe/Berlin")
    now_berlin = dt_util.now().astimezone(berlin_tz)

    # Reset happens at 12:01 Berlin (CET/CEST)
    reset_berlin = now_berlin.replace(
        hour=API_RESET_HOUR,
        minute=API_RESET_BUFFER_MINUTES,
        second=0,
        microsecond=0,
    )

    if reset_berlin <= now_berlin:
        reset_berlin += timedelta(days=1)

    return cast(datetime, reset_berlin)


def get_seconds_until_reset() -> int:
    """Get seconds until next API quota reset."""
    reset_time = get_next_reset_time()
    return int((reset_time - dt_util.now()).total_seconds())


def calculate_remaining_polling_budget(
    limit: int,
    remaining: int,
    background_cost_24h: int,
    throttle_threshold: int,
    auto_quota_percent: int,
    seconds_until_reset: int,
) -> float:
    """Calculate the remaining API budget for the rest of the day."""
    progress_done = (SECONDS_PER_DAY - seconds_until_reset) / SECONDS_PER_DAY
    progress_remaining = seconds_until_reset / SECONDS_PER_DAY

    # Calculate user activity vs threshold
    expected_background_so_far = background_cost_24h * progress_done
    actual_used_total = max(0, limit - remaining)
    user_calls_so_far = max(0, actual_used_total - expected_background_so_far)

    # Everything used beyond the threshold is "excess" and reduces our daily pool
    user_excess = max(0, user_calls_so_far - throttle_threshold)

    # Calculate final available budget for the remaining day
    available_for_day = max(0, limit - background_cost_24h - user_excess)
    total_auto_quota_budget = available_for_day * auto_quota_percent / 100.0
    return max(0.0, total_auto_quota_budget * progress_remaining)


def calculate_weighted_interval(
    remaining_budget: float,
    predicted_poll_cost: float,
    is_in_reduced_window_func: Any,
    reduced_window_conf: dict[str, Any],
    min_floor: int,
) -> int:
    """Calculate weighted interval for performance hours (reinvesting savings)."""
    try:
        now = dt_util.now()
        next_reset = get_next_reset_time()

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
