"""Reset detection must read the real headers, not the simulated limit."""

from __future__ import annotations

from typing import Any

from custom_components.tado_hijack.helpers.quota_math import check_quota_reset
from custom_components.tado_hijack.helpers.rate_limit_manager import RateLimitManager


class _HeaderSource:
    def __init__(self, limit: int, remaining: int, updated_at: float = 1.0) -> None:
        self.rate_limit_data: dict[str, Any] = {
            "limit": limit,
            "remaining": remaining,
            "updated_at": updated_at,
        }


def test_raising_simulated_limit_is_not_a_reset() -> None:
    source = _HeaderSource(600, 550)
    before = RateLimitManager(20, source, simulated_limit=100)
    before.sync_from_headers()
    last = before.header_remaining

    after = RateLimitManager(20, source, simulated_limit=500)
    after.sync_from_headers()

    assert after.remaining > before.remaining
    assert after.header_remaining == 550
    assert not check_quota_reset(after.header_limit, after.header_remaining, last)


def test_real_reset_detected_with_simulation_on() -> None:
    source = _HeaderSource(600, 540)
    before = RateLimitManager(20, source, simulated_limit=100)
    before.sync_from_headers()
    last = before.header_remaining

    source.rate_limit_data = {
        "limit": 600,
        "remaining": 600,
        "updated_at": 2.0,
    }
    after = RateLimitManager(20, source, simulated_limit=100)
    after.sync_from_headers()

    assert check_quota_reset(after.header_limit, after.header_remaining, last)


def test_header_properties_follow_latest_source() -> None:
    stale = _HeaderSource(600, 100, updated_at=1.0)
    fresh = _HeaderSource(600, 500, updated_at=2.0)
    manager = RateLimitManager(20, stale)
    manager.add_source(fresh)

    assert manager.header_limit == 600
    assert manager.header_remaining == 500
