"""Window-aware quota reset learning (issue #203 follow-up)."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.util import dt as dt_util

from custom_components.tado_hijack.helpers.reset_window_tracker import (
    ResetWindowTracker,
)


def _utc(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


def test_drifting_detections_with_windows_still_learn() -> None:
    """The #203 repro: sparse polling drifts the detection hour daily."""
    tracker = ResetWindowTracker()

    tracker.record_reset(_utc(16, 11, 52), observed_after=_utc(16, 10, 47))
    assert tracker.history_count == 1

    # Detection hour 12 != 11: the old detector trimmed here forever.
    tracker.record_reset(_utc(17, 12, 3), observed_after=_utc(17, 10, 12))
    assert tracker.history_count == 2

    # Third day narrows the window: poll shortly after the real 11:00 reset.
    tracker.record_reset(_utc(18, 11, 40), observed_after=_utc(18, 11, 5))

    assert tracker.history_count == 3
    assert tracker.is_learned
    window = tracker.get_expected_window()
    assert window.confidence == "learned"
    assert window.hour == 11


def test_detection_only_drift_keeps_trimming() -> None:
    """Legacy entries without a window cannot beat the drift (documents #203)."""
    tracker = ResetWindowTracker()

    tracker.record_reset(_utc(16, 11, 52))
    tracker.record_reset(_utc(17, 12, 3))

    assert tracker.history_count == 1
    assert not tracker.is_learned


def test_same_detection_hour_learns_without_window() -> None:
    tracker = ResetWindowTracker()

    tracker.record_reset(_utc(16, 11, 52))
    tracker.record_reset(_utc(17, 11, 40))

    assert tracker.is_learned
    assert tracker.get_expected_window().hour == 11


def test_disjoint_window_breaks_pattern_but_keeps_learned() -> None:
    tracker = ResetWindowTracker()
    tracker.record_reset(_utc(16, 11, 52), observed_after=_utc(16, 10, 47))
    tracker.record_reset(_utc(17, 11, 40), observed_after=_utc(17, 11, 5))
    assert tracker.is_learned

    # Reset genuinely moved: no shared hour with the previous entry.
    tracker.record_reset(_utc(18, 16, 10), observed_after=_utc(18, 15, 2))

    assert tracker.history_count == 1
    assert tracker.is_learned
    assert tracker.get_expected_window().hour == 11


def test_next_reset_time_uses_learned_window() -> None:
    tracker = ResetWindowTracker()
    tracker.record_reset(_utc(16, 23, 52), observed_after=_utc(16, 22, 47))
    tracker.record_reset(_utc(17, 23, 40), observed_after=_utc(17, 23, 5))
    assert tracker.is_learned

    next_reset = tracker.get_next_reset_time()
    next_utc = next_reset.astimezone(UTC)
    assert next_utc.hour == 23
    assert next_utc > dt_util.now().astimezone(UTC)


def test_window_roundtrip_survives_persistence() -> None:
    tracker = ResetWindowTracker()
    tracker.record_reset(_utc(16, 11, 52), observed_after=_utc(16, 10, 47))
    tracker.record_reset(_utc(17, 11, 40), observed_after=_utc(17, 11, 5))

    restored = ResetWindowTracker()
    restored.load_dict(tracker.to_dict())

    assert restored.is_learned
    assert restored.history_count == 2
    assert restored.get_expected_window().hour == 11


def test_legacy_storage_loads_without_windows() -> None:
    tracker = ResetWindowTracker()
    legacy = {
        "data_version": 2,
        "history": [_utc(16, 11, 52).isoformat()],
        "history_original": [_utc(16, 11, 52).isoformat()],
        "learned_window": None,
        "initial_target": None,
    }
    tracker.load_dict(legacy)

    assert tracker.history_count == 1
    assert not tracker.is_learned
    # The restored entry behaves like a fresh detection-only entry.
    tracker.record_reset(_utc(17, 11, 30), observed_after=_utc(17, 10, 0))
    assert tracker.history_count == 2
    assert tracker.is_learned


def test_straddling_arc_still_learns() -> None:
    """A stable two-hour-straddling arc must learn its midpoint hour.

    A same-hour majority rule would stall forever on this input.
    """
    tracker = ResetWindowTracker()
    # Aligned grid: window (10:30, 11:00] every day, true reset 10:45.
    tracker.record_reset(_utc(16, 11, 0), observed_after=_utc(16, 10, 30))
    tracker.record_reset(_utc(17, 11, 0), observed_after=_utc(17, 10, 30))

    assert tracker.is_learned
    assert tracker.get_expected_window().hour == 10


def test_midnight_wrapping_arc_learns_zero_hour() -> None:
    """An arc wrapping midnight centers into hour 0, not a stall."""
    tracker = ResetWindowTracker()
    tracker.record_reset(_utc(16, 0, 5), observed_after=_utc(15, 23, 55))
    tracker.record_reset(_utc(17, 0, 5), observed_after=_utc(16, 23, 55))

    assert tracker.is_learned
    window = tracker.get_expected_window()
    assert window.hour == 0
    assert window.minute == 0


def _time_utc(day: int, total_minutes: int) -> datetime:
    """UTC datetime from minutes of day, wrapping negatives past midnight."""
    hour, minute = divmod(total_minutes % (24 * 60), 60)
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


def test_gradual_drift_sheds_stale_history() -> None:
    """A creeping reset follows the newest regime, not a frozen window.

    Each day's window overlaps the previous one, so the adjacent-pair trim
    never fires, but the all-history intersection empties once the drift
    spans more than the window width. Before the fix the learner froze on
    the first regime; now it drops the stale oldest entries and follows.
    """
    tracker = ResetWindowTracker()
    for day, minute in ((16, 56), (17, 66), (18, 76), (19, 86), (20, 96)):
        tracker.record_reset(
            _time_utc(day, minute),
            observed_after=_time_utc(day, minute - 30),
        )

    window = tracker.get_expected_window()
    assert window.confidence == "learned"
    # Newest regime: (01:06, 01:36] intersected backwards as far as it
    # stays non-empty - must be hour 1 (midpoint of the latest entries),
    # not the frozen 00:30 from day 16's era.
    assert window.hour == 1


def test_gradual_drift_keeps_newest_entry() -> None:
    """Shedding stale history never drops the just-recorded entry."""
    tracker = ResetWindowTracker()
    for day, minute in ((16, 56), (17, 66), (18, 76), (19, 86), (20, 96)):
        tracker.record_reset(
            _time_utc(day, minute),
            observed_after=_time_utc(day, minute - 30),
        )
    assert tracker.history_count >= 1
    # The learner shed entries; the surviving history must intersect and
    # keep following the drift.
    tracker.record_reset(_time_utc(21, 106), observed_after=_time_utc(21, 76))
    assert tracker.history_count >= 2
    assert tracker.is_learned
    assert tracker.get_expected_window().hour == 1
