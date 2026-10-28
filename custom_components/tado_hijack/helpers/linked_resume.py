"""Hold a cloud resume until a linked climate's setpoint can finish uploading."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from ..const import (
    CONF_LINKED_RESUME_DELAY_S,
    DEFAULT_LINKED_RESUME_DELAY_S,
    MAX_LINKED_RESUME_DELAY_S,
    POWER_OFF,
    POWER_ON,
)
from .local_climate import climate_power_temp, linked_climate_ids
from .logging_utils import get_redacted_logger
from .optimistic_manager import ZoneOverlayFields
from .overlay_power import map_magic_temp_to_power
from .parsers import zone_setting_power_temp
from .schedule import cached_current_span
from .zone_utils import known_zone_power_temp, local_heating_zone, same_setpoint

if TYPE_CHECKING:
    from ..coordinator import TadoDataUpdateCoordinator

_LOGGER = get_redacted_logger(__name__)

# That upload can still land after the delayed resume.
_TAIL_S = 180.0
_CHECK_LEAD_S = 30.0


class _Hold:
    def __init__(
        self,
        expected: tuple[tuple[str, float | None], ...],
        baseline_overlay: bool,
        baseline: tuple[str, float | None] | None,
        until: float,
    ) -> None:
        self.expected = expected
        self.baseline_overlay = baseline_overlay
        self.baseline = baseline
        self.until = until
        self.sent = False
        self.corrected = False
        self.checks = 0
        self.tail_due: float | None = None
        self.cancel: Callable[[], None] | None = None


def _as_echo(power: str, temperature: float | None) -> tuple[str, float | None]:
    if power == POWER_OFF:
        return POWER_OFF, None
    temp, resolved = map_magic_temp_to_power(temperature)
    return resolved, None if temp is None else float(temp)


def _echo_of(
    reading: tuple[str, float | None] | None,
) -> tuple[str, float | None] | None:
    return None if reading is None else _as_echo(reading[0], reading[1])


def _matches(
    reading: tuple[str, float | None],
    expected: tuple[tuple[str, float | None], ...],
) -> bool:
    power, temperature = reading
    return any(
        same_setpoint(power, temperature, other_power, other_temperature)
        for other_power, other_temperature in expected
    )


def _is_new_manual(
    reading: tuple[str, float | None],
    *,
    baseline_overlay: bool,
    baseline: tuple[str, float | None] | None,
) -> bool:
    """True when this manual was not already the setpoint at arm time."""
    if not baseline_overlay or baseline is None:
        return not baseline_overlay
    return not same_setpoint(reading[0], reading[1], baseline[0], baseline[1])


def _poll_action(
    *,
    sent: bool,
    corrected: bool,
    expired: bool,
    pending: bool,
    overlay: bool,
    matches_expected: bool,
    new_manual: bool,
) -> str:
    """First cloud resume, or the one later resume. A queued command is stale."""
    if expired:
        return "drop"
    if pending:
        return "wait"
    if not sent:
        return "resume" if overlay and matches_expected and new_manual else "wait"
    if corrected or not overlay or not matches_expected:
        return "wait"
    return "correct"


def _overlay_active(state: Any) -> bool:
    return bool(state is not None and getattr(state, "overlay_active", False))


class LinkedResume:
    """One coordinator's delayed resumes for linked heating zones."""

    def __init__(self, coordinator: TadoDataUpdateCoordinator) -> None:
        self._coordinator = coordinator
        self._holds: dict[int, _Hold] = {}
        self._tail_cancel: Callable[[], None] | None = None
        self._tail_due_at: float | None = None

    def delay_s(self) -> float:
        """Seconds before the cloud resume. Missing or junk stays at the default."""
        raw = self._coordinator.config_entry.data.get(
            CONF_LINKED_RESUME_DELAY_S, DEFAULT_LINKED_RESUME_DELAY_S
        )
        try:
            seconds = float(raw)
        except TypeError, ValueError:
            return float(DEFAULT_LINKED_RESUME_DELAY_S)
        return float(min(MAX_LINKED_RESUME_DELAY_S, max(0.0, seconds)))

    async def async_set_delay(self, seconds: float) -> None:
        """Store the wait. 0 resumes at once. No Tado call."""
        stored = int(min(MAX_LINKED_RESUME_DELAY_S, max(0, round(seconds))))
        entry = self._coordinator.config_entry
        self._coordinator.hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_LINKED_RESUME_DELAY_S: stored},
        )
        self._coordinator.async_update_listeners()

    def shutdown(self) -> None:
        self._cancel_tail()
        for zone_id in list(self._holds):
            self.drop(zone_id)

    def drop(self, zone_id: int) -> None:
        hold = self._holds.pop(zone_id, None)
        if hold is not None and hold.cancel is not None:
            hold.cancel()
        if not self._holds:
            self._cancel_tail()
        elif hold is not None and hold.tail_due is not None:
            self._ensure_tail()

    def hold(self, zone_id: int) -> bool:
        """Delay the cloud resume so the bridge upload does not undo it.

        The resume waits for that upload, then runs once more if the same
        setpoint comes back. One zone poll near the end of the wait is the
        look. The regular zone poll is much slower.
        """
        if not local_heating_zone(self._coordinator, zone_id):
            return False
        entity_ids = linked_climate_ids(self._coordinator, zone_id)
        if not entity_ids:
            return False
        self.drop(zone_id)
        baseline_overlay, baseline = self._baseline(zone_id)
        delay = self.delay_s()
        wait = delay + _TAIL_S
        self._holds[zone_id] = _Hold(
            self._expected(zone_id, entity_ids),
            baseline_overlay,
            baseline,
            time.monotonic() + wait,
        )
        self._show_schedule(zone_id, wait)
        self._arm(zone_id, delay, self._on_due)
        _LOGGER.debug("Delaying cloud resume for zone %s by %s s", zone_id, delay)
        return True

    def note_zone_poll(self, states: dict[str, Any]) -> None:
        """Apply holds to a fresh zone poll. Optimistic state is not read."""
        if not self._holds:
            return
        now = time.monotonic()
        pending = self._coordinator.api_manager.pending_keys
        for zone_id in list(self._holds):
            hold = self._holds.get(zone_id)
            if hold is None:
                continue
            state = states.get(str(zone_id))
            reading = _echo_of(zone_setting_power_temp(state))
            action = _poll_action(
                sent=hold.sent,
                corrected=hold.corrected,
                expired=now >= hold.until,
                pending=f"zone_{zone_id}" in pending,
                overlay=_overlay_active(state),
                matches_expected=reading is not None
                and _matches(reading, hold.expected),
                new_manual=reading is not None
                and _is_new_manual(
                    reading,
                    baseline_overlay=hold.baseline_overlay,
                    baseline=hold.baseline,
                ),
            )
            if action == "drop":
                self.drop(zone_id)
            elif action == "resume":
                self._finish(zone_id)
            elif action == "correct":
                hold.corrected = True
                _LOGGER.debug(
                    "Cloud resume for zone %s repeated after the local setpoint returned",
                    zone_id,
                )
                self._send(zone_id)

    def _show_schedule(self, zone_id: int, grace: float) -> None:
        self._coordinator.optimistic.apply_zone_state(
            zone_id,
            overlay=False,
            fields=ZoneOverlayFields(),
            grace_period=grace,
        )
        self._coordinator.async_update_listeners()

    def _send(self, zone_id: int) -> None:
        hold = self._holds.get(zone_id)
        remaining = 0.0 if hold is None else hold.until - time.monotonic()
        self._coordinator._execute_resume_command(
            zone_id,
            grace_period=remaining if remaining > 0 else None,
        )

    def _cancel_tail(self) -> None:
        if self._tail_cancel is not None:
            self._tail_cancel()
            self._tail_cancel = None
        self._tail_due_at = None

    def _arm(
        self,
        zone_id: int,
        delay: float,
        action: Callable[[int], Awaitable[None]],
    ) -> None:
        hold = self._holds.get(zone_id)
        if hold is None:
            return
        if hold.cancel is not None:
            hold.cancel()
            hold.cancel = None

        async def _fire(_now: object) -> None:
            current = self._holds.get(zone_id)
            if current is not None:
                current.cancel = None
            await action(zone_id)

        hold.cancel = async_call_later(self._coordinator.hass, delay, _fire)

    async def _on_due(self, zone_id: int) -> None:
        self._finish(zone_id)

    def _finish(self, zone_id: int) -> None:
        hold = self._holds.get(zone_id)
        if hold is None or hold.sent:
            return
        if hold.cancel is not None:
            hold.cancel()
            hold.cancel = None
        hold.sent = True
        self._send(zone_id)
        self._arm_tail(zone_id)

    def _arm_tail(self, zone_id: int) -> None:
        hold = self._holds.get(zone_id)
        if hold is None or hold.corrected:
            return
        remaining = hold.until - time.monotonic()
        if remaining <= _CHECK_LEAD_S:
            delay = max(1.0, remaining * 0.5)
        else:
            delay = remaining - _CHECK_LEAD_S
        hold.tail_due = time.monotonic() + delay
        self._ensure_tail()

    def _ensure_tail(self) -> None:
        now = time.monotonic()
        due_at: float | None = None
        for hold in self._holds.values():
            if hold.tail_due is None or hold.corrected:
                continue
            if due_at is None or hold.tail_due < due_at:
                due_at = hold.tail_due
        if due_at is None:
            self._cancel_tail()
            return
        if self._tail_due_at is not None and abs(self._tail_due_at - due_at) < 1.0:
            return
        self._cancel_tail()
        self._tail_due_at = due_at

        async def _fire(_now: object) -> None:
            self._tail_cancel = None
            self._tail_due_at = None
            await self._on_tail()

        self._tail_cancel = async_call_later(
            self._coordinator.hass, max(0.0, due_at - now), _fire
        )

    async def _on_tail(self) -> None:
        now = time.monotonic()
        due = [
            zone_id
            for zone_id, hold in self._holds.items()
            if hold.tail_due is not None
            and not hold.corrected
            and hold.tail_due <= now + 2.0
        ]
        for zone_id in due:
            current = self._holds.get(zone_id)
            if current is not None:
                current.tail_due = None
        if not due:
            self._ensure_tail()
            return
        pending = self._coordinator.api_manager.pending_keys
        blocked = [zone_id for zone_id in due if f"zone_{zone_id}" in pending]
        if ready := [zone_id for zone_id in due if zone_id not in blocked]:
            try:
                await self._coordinator.data_manager._fetch_zones(time.monotonic())
            except Exception:
                _LOGGER.debug("Linked resume check failed", exc_info=True)
                blocked.extend(ready)
        for zone_id in blocked:
            hold = self._holds.get(zone_id)
            if hold is None or hold.corrected or hold.checks >= 1:
                continue
            hold.checks += 1
            hold.tail_due = time.monotonic() + 15.0
        self._ensure_tail()

    def _expected(
        self, zone_id: int, entity_ids: list[str]
    ) -> tuple[tuple[str, float | None], ...]:
        found: list[tuple[str, float | None]] = []

        def add(reading: tuple[str, float | None] | None) -> None:
            echo = _echo_of(reading)
            if echo is None or (echo[0] == POWER_ON and echo[1] is None):
                return
            if any(
                same_setpoint(echo[0], echo[1], power, temperature)
                for power, temperature in found
            ):
                return
            found.append(echo)

        span = cached_current_span(
            self._coordinator.data_manager.schedule_blocks_cache,
            zone_id,
            dt_util.now(),
        )
        if span is not None and not (
            span.power == POWER_ON and span.temperature is None
        ):
            add((span.power, span.temperature))
        add(known_zone_power_temp(self._coordinator, zone_id))
        states = self._coordinator.hass.states
        for entity_id in entity_ids:
            add(climate_power_temp(states.get(entity_id)))
        return tuple(found)

    def _baseline(self, zone_id: int) -> tuple[bool, tuple[str, float | None] | None]:
        """Manual setpoint already true. An optimistic heat still in grace counts."""
        optimistic = self._coordinator.optimistic.get_zone_overlay(zone_id)
        state = None
        data = self._coordinator.data
        if data is not None:
            state = data.zone_states.get(str(zone_id))
        if optimistic is True:
            return True, _echo_of(known_zone_power_temp(self._coordinator, zone_id))
        if _overlay_active(state):
            return True, _echo_of(zone_setting_power_temp(state))
        return False, None
