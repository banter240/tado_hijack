"""Unit tests for helpers/quota_math.py."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util

from custom_components.tado_hijack.const import (
    API_RESET_DEFAULT_UTC_HOUR,
    API_RESET_MIN_PERCENT,
    SECONDS_PER_HOUR,
)
from custom_components.tado_hijack.helpers import quota_math


class TestCheckQuotaReset:
    def test_first_observation_never_resets(self) -> None:
        assert quota_math.check_quota_reset(100, 90, None) is False

    def test_nonpositive_limit_never_resets(self) -> None:
        assert quota_math.check_quota_reset(0, 90, 10) is False
        assert quota_math.check_quota_reset(-1, 90, 10) is False

    def test_increase_above_min_percent_resets(self) -> None:
        assert quota_math.check_quota_reset(100, 90, 10) is True

    def test_increase_below_min_percent_is_no_reset(self) -> None:
        # 0->1 throttled edge case: 1% remaining is below the 80% guard
        assert quota_math.check_quota_reset(100, 1, 0) is False

    def test_exact_min_percent_counts(self) -> None:
        limit = 100
        remaining = int(limit * API_RESET_MIN_PERCENT)
        assert quota_math.check_quota_reset(limit, remaining, 10) is True

    def test_decrease_is_no_reset(self) -> None:
        assert quota_math.check_quota_reset(100, 50, 90) is False

    def test_equal_remaining_is_no_reset(self) -> None:
        assert quota_math.check_quota_reset(100, 50, 50) is False


class TestIsInResetSafeWindow:
    def test_current_hour_and_both_neighbors_match(self) -> None:
        hour = dt_util.now().hour
        assert quota_math.is_in_reset_safe_window(hour)
        assert quota_math.is_in_reset_safe_window((hour + 1) % 24)
        assert quota_math.is_in_reset_safe_window((hour - 1) % 24)

    def test_distant_hour_does_not_match(self) -> None:
        # expected hour +5 means accepted hours are +4/+5/+6, never the current one
        hour = dt_util.now().hour
        assert quota_math.is_in_reset_safe_window((hour + 5) % 24) is False

    def test_default_hour_constant(self) -> None:
        assert API_RESET_DEFAULT_UTC_HOUR == 11


class TestGetSecondsUntilReset:
    def test_future_reset_positive(self) -> None:
        next_reset = dt_util.now() + timedelta(hours=2)
        seconds = quota_math.get_seconds_until_reset(next_reset)
        assert 0 < seconds <= 2 * SECONDS_PER_HOUR

    def test_past_reset_negative(self) -> None:
        next_reset = dt_util.now() - timedelta(hours=1)
        assert quota_math.get_seconds_until_reset(next_reset) < 0


class TestCalculateRemainingPollingBudget:
    def test_zero_remaining_returns_zero(self) -> None:
        assert (
            quota_math.calculate_remaining_polling_budget(
                limit=100,
                remaining=0,
                background_cost_24h=10,
                throttle_threshold=5,
                auto_quota_percent=50,
                seconds_until_reset=43200,
            )
            == 0.0
        )

    def test_nonpositive_limit_returns_zero(self) -> None:
        assert (
            quota_math.calculate_remaining_polling_budget(
                limit=0,
                remaining=50,
                background_cost_24h=10,
                throttle_threshold=5,
                auto_quota_percent=50,
                seconds_until_reset=43200,
            )
            == 0.0
        )

    def test_fresh_day_simple_budget(self) -> None:
        # limit 100, bg 10, threshold 5, 50% -> base budget 42.5 calls
        budget = quota_math.calculate_remaining_polling_budget(
            limit=100,
            remaining=100,
            background_cost_24h=10,
            throttle_threshold=5,
            auto_quota_percent=50,
            seconds_until_reset=86400,
        )
        assert budget == 42.5

    def test_half_day_consumed_shrinks_budget(self) -> None:
        full = quota_math.calculate_remaining_polling_budget(
            limit=100,
            remaining=100,
            background_cost_24h=10,
            throttle_threshold=5,
            auto_quota_percent=50,
            seconds_until_reset=86400,
        )
        half = quota_math.calculate_remaining_polling_budget(
            limit=100,
            remaining=80,
            background_cost_24h=10,
            throttle_threshold=5,
            auto_quota_percent=50,
            seconds_until_reset=43200,
        )
        assert 0 < half < full

    def test_never_negative(self) -> None:
        budget = quota_math.calculate_remaining_polling_budget(
            limit=100,
            remaining=3,
            background_cost_24h=50,
            throttle_threshold=20,
            auto_quota_percent=50,
            seconds_until_reset=3600,
        )
        assert budget >= 0.0

    def test_safety_reserve_subtracted(self) -> None:
        without = quota_math.calculate_remaining_polling_budget(
            limit=100,
            remaining=100,
            background_cost_24h=10,
            throttle_threshold=5,
            auto_quota_percent=50,
            seconds_until_reset=86400,
        )
        with_reserve = quota_math.calculate_remaining_polling_budget(
            limit=100,
            remaining=100,
            background_cost_24h=10,
            throttle_threshold=5,
            auto_quota_percent=50,
            seconds_until_reset=86400,
            safety_reserve=5,
        )
        assert with_reserve == without - 5


class TestCalculateSafetyReserveInterval:
    def test_no_reserve_uses_hour_interval(self) -> None:
        assert quota_math.calculate_safety_reserve_interval(0) == SECONDS_PER_HOUR
        assert quota_math.calculate_safety_reserve_interval(-3) == SECONDS_PER_HOUR

    def test_reserve_spread_over_three_hours(self) -> None:
        # 3h window, e.g. reserve 3 -> one call per hour
        assert quota_math.calculate_safety_reserve_interval(3) == SECONDS_PER_HOUR
        assert quota_math.calculate_safety_reserve_interval(6) == SECONDS_PER_HOUR // 2

    def test_large_reserve_hits_floor(self) -> None:
        # 3600*3 // 1000 = 10s, small but positive
        assert quota_math.calculate_safety_reserve_interval(1000) == 10


class TestCalculateWeightedInterval:
    def _no_reduced_window(self, _dt: object, _conf: object) -> bool:
        return False

    def _always_reduced(self, _dt: object, _conf: object) -> bool:
        return True

    def _next_reset(self, hours: float = 3) -> datetime:
        return dt_util.now() + timedelta(hours=hours)

    def test_all_normal_hours_divide_budget(self) -> None:
        conf = {"interval": 1800}
        interval = quota_math.calculate_weighted_interval(
            remaining_budget=60.0,
            predicted_poll_cost=0.5,
            is_in_reduced_window_func=self._no_reduced_window,
            reduced_window_conf=conf,
            min_floor=20,
            next_reset=self._next_reset(hours=3),
        )
        # 60 calls / 0.5 cost = 120 polls over 3h = 90s, capped at 1800
        assert 20 <= interval <= 1800

    def test_reduced_interval_zero_means_free_reduced_time(self) -> None:
        conf = {"interval": 0}
        interval = quota_math.calculate_weighted_interval(
            remaining_budget=60.0,
            predicted_poll_cost=0.5,
            is_in_reduced_window_func=self._no_reduced_window,
            reduced_window_conf=conf,
            min_floor=20,
            next_reset=self._next_reset(hours=3),
        )
        assert interval >= 20

    def test_budget_error_falls_back_to_hour(self) -> None:
        # predicted_poll_cost=0 raises ZeroDivisionError inside; fallback expected
        conf = {"interval": 1800}
        interval = quota_math.calculate_weighted_interval(
            remaining_budget=60.0,
            predicted_poll_cost=0,
            is_in_reduced_window_func=self._no_reduced_window,
            reduced_window_conf=conf,
            min_floor=20,
            next_reset=self._next_reset(hours=1),
        )
        assert interval == max(20, SECONDS_PER_HOUR)

    def test_small_budget_caps_at_reduced_interval(self) -> None:
        conf = {"interval": 1800}
        interval = quota_math.calculate_weighted_interval(
            remaining_budget=0.01,
            predicted_poll_cost=0.5,
            is_in_reduced_window_func=self._no_reduced_window,
            reduced_window_conf=conf,
            min_floor=300,
            next_reset=self._next_reset(hours=3),
        )
        # 0.02 polls spread over ~3h -> huge interval, but capped at 1800
        assert interval == 1800
