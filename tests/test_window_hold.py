"""Regression tests for issue #212: window hold survives sensor dropout.

When a contact sensor goes unknown/unavailable during an active window
episode, the zone must stay guarded: the re-off watchdog keeps running,
the offline fallback must not paint the schedule onto the room, and the
episode must not be erased. On reconnect the off is re-applied.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from custom_components.tado_hijack.helpers.window_controller import (
    WindowController,
)


def _controller(contacts: dict[int, list[str]]) -> WindowController:
    """A controller with mocked coordinator plumbing; no HA event loop."""
    coord = MagicMock()
    coord.config_entry.data = {}
    coord.storage.async_get = NotImplemented  # unused in these tests
    controller = WindowController(coord)
    controller._contacts_by_zone = lambda: {  # type: ignore[method-assign]
        str(zid): list(ids) for zid, ids in contacts.items()
    }
    return controller


def _state(controller: WindowController, entity: str, state: str | None) -> None:
    """Pin one entity's reported state; None means the entity is gone."""
    controller._hass.states.get = MagicMock()  # type: ignore[method-assign]
    controller._hass.states.get.return_value = (
        None if state is None else MagicMock(state=state)
    )


def test_guards_writes_open_episode_unknown_contact() -> None:
    """Episode active + sensor gone: guard stays up (#212)."""
    wc = _controller({1: ["binary_sensor.win"]})
    _state(wc, "binary_sensor.win", "unavailable")
    wc._off_active.add(1)
    wc._snaps[1] = MagicMock()
    assert wc.zone_window_guards_writes(1)


def test_guards_writes_closed_lifts_guard() -> None:
    """A contact reporting closed ends the guard even mid-episode."""
    wc = _controller({1: ["binary_sensor.win"]})
    _state(wc, "binary_sensor.win", "off")
    wc._off_active.add(1)
    wc._snaps[1] = MagicMock()
    assert not wc.zone_window_guards_writes(1)


def test_guards_writes_open_contact_without_episode() -> None:
    """No episode: plain open check (legacy behaviour)."""
    wc = _controller({1: ["binary_sensor.win"]})
    _state(wc, "binary_sensor.win", "on")
    assert wc.zone_window_guards_writes(1)


def test_guards_writes_closed_contact_without_episode() -> None:
    wc = _controller({1: ["binary_sensor.win"]})
    _state(wc, "binary_sensor.win", "off")
    assert not wc.zone_window_guards_writes(1)


def test_guards_writes_no_contacts() -> None:
    wc = _controller({})
    assert not wc.zone_window_guards_writes(1)


def test_hold_active_survives_unknown_contact() -> None:
    """The re-off watchdog must not die with the sensor (#212)."""
    wc = _controller({1: ["binary_sensor.win"]})
    _state(wc, "binary_sensor.win", "unavailable")
    wc._off_active.add(1)
    wc._snaps[1] = MagicMock(released=False)
    assert wc._hold_active(1)


def test_hold_active_ends_when_released() -> None:
    wc = _controller({1: ["binary_sensor.win"]})
    _state(wc, "binary_sensor.win", "on")
    wc._off_active.add(1)
    wc._snaps[1] = MagicMock(released=True)
    assert not wc._hold_active(1)


def test_note_cloud_sent_keeps_snap_when_contact_unknown() -> None:
    """Mid-episode batch flush must not erase the episode (#212)."""
    wc = _controller({1: ["binary_sensor.win"]})
    _state(wc, "binary_sensor.win", "unknown")
    wc._off_active.add(1)
    snap = MagicMock()
    wc._snaps[1] = snap
    wc._note_cloud_sent(1)
    assert 1 in wc._snaps
    assert snap.released is True
    assert snap.cloud_off_sent is False


def test_note_cloud_sent_pops_snap_when_contact_closed() -> None:
    wc = _controller({1: ["binary_sensor.win"]})
    _state(wc, "binary_sensor.win", "off")
    wc._off_active.add(1)
    wc._snaps[1] = MagicMock()
    wc._note_cloud_sent(1)
    assert 1 not in wc._snaps


def test_open_delay_commits_on_unknown_contact() -> None:
    """Sensor drops during the open-delay wait: still commit the off (#212)."""
    wc = _controller({1: ["binary_sensor.win"]})
    _state(wc, "binary_sensor.win", "unavailable")
    spy = _AsyncSpy()
    wc.__dict__["_async_commit_open"] = spy
    asyncio.run(wc._make_delay_action(1, opened=True)())
    assert spy.calls == [(1,)]


def test_open_delay_skips_when_closed() -> None:
    wc = _controller({1: ["binary_sensor.win"]})
    _state(wc, "binary_sensor.win", "off")
    spy = _AsyncSpy()
    wc.__dict__["_async_commit_open"] = spy
    asyncio.run(wc._make_delay_action(1, opened=True)())
    assert spy.calls == []


class _AsyncSpy:
    """Awaitable stand-in recording call args."""

    calls: list[tuple[int]]

    def __init__(self) -> None:
        self.calls = []

    async def __call__(self, zone_id: int) -> None:
        self.calls.append((zone_id,))


@pytest.mark.parametrize(
    ("episode", "expected"),
    [
        (True, True),
        (False, False),
    ],
)
def test_first_event_after_restart_reevaluates_episode(
    episode: bool, expected: bool
) -> None:
    """old_state is None (HA restart): zones with an episode are re-checked."""
    wc = _controller({1: ["binary_sensor.win"]})
    _state(wc, "binary_sensor.win", "on")
    wc._zones_by_sensor["binary_sensor.win"].add(1)
    if episode:
        wc._snaps[1] = MagicMock()
        wc._off_active.add(1)
    seen: list[int] = []

    async def _fake_startup(zone_id: int) -> None:
        seen.append(zone_id)

    wc.__dict__["_async_evaluate_zone_startup"] = _fake_startup
    event = MagicMock()
    event.data = {
        "entity_id": "binary_sensor.win",
        "new_state": MagicMock(state="on"),
        "old_state": None,
    }
    asyncio.run(wc._async_on_sensor_event(event))
    assert bool(seen) is expected
