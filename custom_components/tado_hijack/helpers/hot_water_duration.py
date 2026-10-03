"""Local Tado X hot-water duration.

Tado ends a boost after 60 minutes and ignores a timer in the boost body.
Off stays until the schedule is resumed. This holds either state until a
deadline, repeats a boost before that 60 minute window closes, and then
returns to the programmer state from before the hold.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from .logging_utils import get_redacted_logger

_LOGGER = get_redacted_logger(__name__)

# Refresh inside the 60 minute boost so a delayed call still lands before it ends.
_BOOST_REFRESH = timedelta(minutes=50)
_RETRY = timedelta(seconds=60)
_STORAGE_KEY = "hot_water_duration"

HoldMode = Literal["boost", "off"]
ReturnMode = Literal["resume", "off"]
_Action = Literal["boost", "off", "resume"]


@dataclass
class _Plan:
    mode: HoldMode
    return_mode: ReturnMode
    deadline: datetime
    applied_at: datetime | None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "mode": self.mode,
            "return_mode": self.return_mode,
            "deadline": self.deadline.isoformat(),
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
        }


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    parsed: datetime | None = dt_util.parse_datetime(value)
    if not isinstance(parsed, datetime):
        return None
    utc: datetime = dt_util.as_utc(parsed)
    return utc


def _programmer_state(state: Any) -> str:
    return str(getattr(state, "state", "") or "").strip().upper()


def programmer_return_mode(state: Any) -> ReturnMode:
    """Schedule, unless the programmer was already forced off."""
    return "off" if _programmer_state(state) == "BOOST_OFF" else "resume"


def programmer_next_block(state: Any, now: datetime) -> datetime | None:
    """Next schedule change while the programmer is following the schedule.

    During a boost, nextStateChange is the boost expiry.
    """
    if not _programmer_state(state).startswith("SCHEDULE_"):
        return None
    deadline = _parse_dt(getattr(state, "next_state_change", None))
    return None if deadline is None or deadline <= now else deadline


def _plan_from_storage(raw: Any) -> _Plan | None:
    if not isinstance(raw, dict):
        return None
    mode = raw.get("mode")
    if mode not in ("boost", "off"):
        return None
    return_mode = raw.get("return_mode", "resume")
    if return_mode not in ("resume", "off"):
        return None
    deadline = _parse_dt(raw.get("deadline"))
    if deadline is None:
        return None
    applied = raw.get("applied_at")
    applied_at = None if applied is None else _parse_dt(applied)
    if applied is not None and applied_at is None:
        return None
    return _Plan(
        cast("HoldMode", mode),
        cast("ReturnMode", return_mode),
        deadline,
        applied_at,
    )


class HotWaterDuration:
    """Persist a hot-water hold and finish it after a restart."""

    def __init__(
        self,
        hass: HomeAssistant,
        storage: Any,
        *,
        send_boost: Callable[[], Awaitable[bool]],
        send_off: Callable[[], Awaitable[bool]],
        send_resume: Callable[[], Awaitable[bool]],
    ) -> None:
        self._hass = hass
        self._storage = storage
        self._send_boost = send_boost
        self._send_off = send_off
        self._send_resume = send_resume
        self._lock = asyncio.Lock()
        self._plan: _Plan | None = None
        self._unsub: Callable[[], None] | None = None
        self._stopped = False

    async def async_restore(self) -> None:
        """Arm a hold that was saved before the last shutdown."""
        async with self._lock:
            if self._stopped or self._plan is not None:
                return
            raw = await self._storage.async_get(_STORAGE_KEY)
            plan = _plan_from_storage(raw)
            if plan is None:
                if raw:
                    await self._storage.async_update(_STORAGE_KEY, None)
                return
            self._plan = plan
            await self._async_act_locked()

    async def async_start(
        self,
        mode: HoldMode,
        *,
        minutes: int | None = None,
        deadline: datetime | None = None,
        return_mode: ReturnMode = "resume",
    ) -> None:
        """Replace any hold and keep this mode until the deadline."""
        if deadline is None:
            if minutes is None:
                return
            deadline = dt_util.utcnow() + timedelta(minutes=minutes)
        async with self._lock:
            self._disarm()
            plan = _Plan(mode, return_mode, dt_util.as_utc(deadline), None)
            self._plan = plan
            await self._persist_locked()
            _LOGGER.info(
                "Holding Tado X hot water %s until %s, then %s",
                mode,
                plan.deadline.isoformat(timespec="minutes"),
                plan.return_mode,
            )
            await self._async_act_locked()

    async def async_cancel(self) -> None:
        """Drop a hold without sending a hot-water command."""
        async with self._lock:
            await self._clear_locked()

    def shutdown(self) -> None:
        """Stop the in-memory timer. The saved hold stays for the next start."""
        self._stopped = True
        self._disarm()

    async def _on_timer(self, _now: datetime) -> None:
        """Stay on the event loop. A sync callback runs in the executor and drops the wake."""
        self._unsub = None
        if self._stopped:
            return
        await self._async_fire()

    async def _async_fire(self) -> None:
        async with self._lock:
            await self._async_act_locked()

    async def _async_act_locked(self) -> None:
        plan = self._plan
        if self._stopped or plan is None:
            return
        now = dt_util.utcnow()
        if now >= plan.deadline:
            if await self._send(plan.return_mode):
                if self._stopped:
                    return
                await self._clear_locked()
                _LOGGER.info(
                    "Tado X hot water returned to %s",
                    "off" if plan.return_mode == "off" else "the schedule",
                )
                return
            self._arm(now + _RETRY)
            return

        if _hold_due(plan, now):
            sent = await self._send(plan.mode)
            if self._stopped:
                return
            if not sent:
                self._arm(now + _RETRY)
                return
            plan.applied_at = dt_util.utcnow()
            await self._persist_locked()
        if self._stopped or self._plan is None:
            return
        self._arm(_next_wake(plan, dt_util.utcnow()))

    async def _send(self, action: _Action) -> bool:
        if action == "boost":
            return bool(await self._send_boost())
        if action == "resume":
            return bool(await self._send_resume())
        return bool(await self._send_off())

    async def _persist_locked(self) -> None:
        payload = self._plan.to_dict() if self._plan else None
        await self._storage.async_update(_STORAGE_KEY, payload)

    async def _clear_locked(self) -> None:
        self._disarm()
        self._plan = None
        await self._persist_locked()

    def _arm(self, when: datetime) -> None:
        if self._stopped:
            return
        self._disarm()
        self._unsub = async_track_point_in_utc_time(self._hass, self._on_timer, when)

    def _disarm(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None


def _hold_due(plan: _Plan, now: datetime) -> bool:
    if plan.applied_at is None:
        return True
    if plan.mode != "boost":
        return False
    refresh_at = plan.applied_at + _BOOST_REFRESH
    return now >= refresh_at and refresh_at < plan.deadline


def _next_wake(plan: _Plan, now: datetime) -> datetime:
    wake = plan.deadline
    if plan.mode == "boost" and plan.applied_at is not None:
        refresh_at = plan.applied_at + _BOOST_REFRESH
        wake = min(wake, refresh_at)
    return max(wake, now)
