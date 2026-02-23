"""Timer scheduling for Tado Hijack coordinator polls."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from .logging_utils import get_redacted_logger

_LOGGER = get_redacted_logger(__name__)

type AsyncCallback = Callable[[], Coroutine[Any, Any, None]]


class PollScheduler:
    """Manages deferred poll timers for the coordinator.

    Owns all asyncio timer handles so the coordinator is free of timer
    bookkeeping. Three independent timer concerns are handled:

    - expiry_poll: fires once (with buffer) when an overlay timer expires
    - queued_refresh: debounced single-shot after a resume/off action
    - reset_poll: fires once at the daily quota reset (rescheduled by callback)
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise with a HomeAssistant instance."""
        self._hass = hass
        self._expiry_timers: set[asyncio.TimerHandle] = set()
        self._post_action_poll_timer: asyncio.TimerHandle | None = None
        self._reset_poll_unsub: asyncio.TimerHandle | None = None

    # ------------------------------------------------------------------
    # Expiry poll (one-shot, multiple may be active simultaneously)
    # ------------------------------------------------------------------

    def schedule_expiry_poll(self, delay_s: int, manual_poll_cb: AsyncCallback) -> None:
        """Schedule a poll to fire *delay_s* seconds after an overlay expires."""
        _LOGGER.debug("Scheduling expiry poll in %d seconds (plus buffer)", delay_s)
        handle = self._hass.loop.call_later(
            delay_s + 2,
            self._execute_expiry_poll,
            manual_poll_cb,
        )
        self._expiry_timers.add(handle)

    def _execute_expiry_poll(self, manual_poll_cb: AsyncCallback) -> None:
        self._expiry_timers = {h for h in self._expiry_timers if not h.cancelled()}
        _LOGGER.debug("Timer expired: Triggering post-action poll")
        self._hass.async_create_task(manual_poll_cb())

    # ------------------------------------------------------------------
    # Queued refresh (debounced: replaces previous timer if pending)
    # ------------------------------------------------------------------

    def schedule_queued_refresh(
        self, delay_s: float, manual_poll_cb: AsyncCallback
    ) -> None:
        """Schedule a debounced post-action refresh with a grace period."""
        if self._post_action_poll_timer is not None:
            self._post_action_poll_timer.cancel()
        self._post_action_poll_timer = self._hass.loop.call_later(
            delay_s,
            self._execute_queued_refresh,
            manual_poll_cb,
        )

    def _execute_queued_refresh(self, manual_poll_cb: AsyncCallback) -> None:
        self._post_action_poll_timer = None
        _LOGGER.debug("Grace period expired: Triggering post-action poll")
        self._hass.async_create_task(manual_poll_cb())

    # ------------------------------------------------------------------
    # Reset poll (single-shot, callback reschedules itself)
    # ------------------------------------------------------------------

    def schedule_reset_poll(self, delay_s: float, callback: AsyncCallback) -> None:
        """Schedule a one-shot timer that fires *callback* after *delay_s* seconds."""
        if self._reset_poll_unsub:
            self._reset_poll_unsub.cancel()
        self._reset_poll_unsub = self._hass.loop.call_later(
            max(1.0, delay_s),
            lambda: self._hass.async_create_task(callback()),
        )

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Cancel all pending timers."""
        if self._reset_poll_unsub:
            self._reset_poll_unsub.cancel()
            self._reset_poll_unsub = None

        if self._post_action_poll_timer:
            self._post_action_poll_timer.cancel()
            self._post_action_poll_timer = None

        for handle in self._expiry_timers:
            handle.cancel()
        self._expiry_timers.clear()
