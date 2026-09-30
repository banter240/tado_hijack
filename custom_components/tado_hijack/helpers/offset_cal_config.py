"""Offset-cal config: bridge master, per-zone overrides, scheduler."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .logging_utils import get_redacted_logger

if TYPE_CHECKING:
    from .. import TadoConfigEntry

from ..const import (
    CONF_OFFSET_CAL_INTERVAL,
    CONF_OFFSET_CAL_SEND_COOLDOWN_S,
    CONF_OFFSET_CAL_SPREAD_THRESHOLD,
    CONF_OFFSET_CAL_WINDOW_SETTLE_S,
    CONF_ZONE_OFFSET_CAL_INTERVALS,
    CONF_ZONE_OFFSET_CAL_THRESHOLDS,
    CONF_ZONE_TEMP_ENTITIES,
    CONF_ZONE_WINDOW_ENTITIES,
    DEFAULT_OFFSET_CAL_INTERVAL,
    DEFAULT_OFFSET_CAL_SEND_COOLDOWN_S,
    DEFAULT_OFFSET_CAL_SPREAD_THRESHOLD,
    DEFAULT_OFFSET_CAL_WINDOW_SETTLE_S,
)

_LOGGER = get_redacted_logger(__name__)


class OffsetCalConfigMixin:
    """Offset-cal config access split off the coordinator.

    Host must provide: hass, config_entry, _offset_cal_unsub,
    _offset_cal_threshold_unsubs, _offset_cal_threshold_handle,
    _offset_cal_threshold_retry, async_calibrate_offsets,
    async_update_interval_local, async_update_listeners.
    """

    if TYPE_CHECKING:
        hass: HomeAssistant
        config_entry: TadoConfigEntry
        _offset_cal_unsub: Callable[[], None] | None
        _offset_cal_threshold_unsubs: list[Callable[[], None]]
        _offset_cal_threshold_handle: Callable[[], None] | None
        _offset_cal_threshold_retry: Callable[[], None] | None
        _offset_cal_send_ready_at: dict[int, datetime]
        _offset_cal_window_settle_until: dict[int, datetime]
        _offset_cal_window_was_open: set[int]
        _offset_cal_interval_pending: set[int]
        _offset_cal_interval_unsubs: list[Callable[[], None]]
        _offset_cal_interval_watched: tuple[str, ...]
        _offset_cal_interval_retry: Callable[[], None] | None
        _offset_cal_interval_flushing: bool
        _offset_cal_interval_flush_again: bool

        def async_calibrate_offsets(
            self, trigger: str, zone_id: int | None = None
        ) -> Any: ...
        def async_update_interval_local(self) -> None: ...
        def async_update_listeners(self) -> None: ...

    def _offset_cal_option(self) -> str:
        return str(
            self.config_entry.data.get(
                CONF_OFFSET_CAL_INTERVAL, DEFAULT_OFFSET_CAL_INTERVAL
            )
        )

    def get_offset_cal_threshold(self) -> float:
        return float(
            self.config_entry.data.get(
                CONF_OFFSET_CAL_SPREAD_THRESHOLD, DEFAULT_OFFSET_CAL_SPREAD_THRESHOLD
            )
        )

    def get_zone_offset_cal_interval(self, zone_id: int) -> str:
        # Unset stays inherit so the select does not copy the bridge interval.
        from .offset_calibrate import OFFSET_CAL_INHERIT

        overrides = self.config_entry.data.get(CONF_ZONE_OFFSET_CAL_INTERVALS) or {}
        if isinstance(overrides, dict) and (value := overrides.get(str(zone_id))):
            return str(value)
        return OFFSET_CAL_INHERIT

    def effective_zone_offset_cal_interval(self, zone_id: int) -> str:
        from .offset_calibrate import OFFSET_CAL_INHERIT

        option = self.get_zone_offset_cal_interval(zone_id)
        return self._offset_cal_option() if option == OFFSET_CAL_INHERIT else option

    def get_zone_offset_cal_threshold(self, zone_id: int) -> float:
        overrides = self.config_entry.data.get(CONF_ZONE_OFFSET_CAL_THRESHOLDS) or {}
        if isinstance(overrides, dict):
            value = overrides.get(str(zone_id))
            if value is not None and float(value) > 0:
                return float(value)
        return self.get_offset_cal_threshold()

    def zone_offset_cal_hours(self, zone_id: int) -> list[int]:
        from .offset_calibrate import hours_from_midnight

        return (
            hours_from_midnight(self.effective_zone_offset_cal_interval(zone_id)) or []
        )

    def _linked_zone_ids(self) -> list[int]:
        linked = self.config_entry.data.get(CONF_ZONE_TEMP_ENTITIES) or {}
        if not isinstance(linked, dict):
            return []
        zone_ids: list[int] = []
        for zid in linked:
            try:
                zone_ids.append(int(zid))
            except TypeError, ValueError:
                continue
        return zone_ids

    def _all_offset_cal_hours(self) -> set[int]:
        from .offset_calibrate import hours_from_midnight

        all_hours: set[int] = set(hours_from_midnight(self._offset_cal_option()) or [])
        for zone_id in self._linked_zone_ids():
            all_hours.update(self.zone_offset_cal_hours(zone_id))
        return all_hours


class OffsetCalSchedulerMixin(OffsetCalConfigMixin):
    def _schedule_offset_cal_timer(self) -> None:
        from homeassistant.helpers.event import async_track_time_change

        if self._offset_cal_unsub:
            self._offset_cal_unsub()
            self._offset_cal_unsub = None
        hours = sorted(self._all_offset_cal_hours())
        self._drop_stale_interval_holds()
        if not hours:
            self._schedule_offset_cal_threshold_watch()
            return
        self._offset_cal_unsub = async_track_time_change(
            self.hass,
            self._on_offset_cal_tick,
            hour=hours,
            minute=0,
            second=0,
        )
        _LOGGER.info("Offset auto-cal scheduled at local hours %s", hours)
        self._schedule_offset_cal_threshold_watch()

    async def _on_offset_cal_tick(self, now: datetime) -> None:
        held = False
        for zone_id in self._linked_zone_ids():
            if now.hour not in self.zone_offset_cal_hours(zone_id):
                continue
            if self._interval_cal_must_wait(zone_id):
                self._hold_interval_cal(zone_id)
                held = True
                continue
            await self.async_calibrate_offsets("interval", zone_id=zone_id)
        if held:
            self._sync_interval_window_watch()
            await self._async_flush_interval_cal()

    def _offset_cal_window_open(self, zone_id: int) -> bool:
        window = getattr(self, "window_controller", None)
        return bool(window and window.zone_window_is_open(zone_id))

    def _interval_cal_must_wait(self, zone_id: int) -> bool:
        if self._offset_cal_window_open(zone_id):
            return True
        now = dt_util.utcnow()
        settle_until = self._offset_cal_window_settle_until.get(zone_id)
        if settle_until is not None and now < settle_until:
            return True
        ready_at = self._offset_cal_send_ready_at.get(zone_id)
        return ready_at is not None and now < ready_at

    def _hold_interval_cal(self, zone_id: int) -> None:
        if zone_id in self._offset_cal_interval_pending:
            return
        self._offset_cal_interval_pending.add(zone_id)
        if self._offset_cal_window_open(zone_id):
            self._offset_cal_window_was_open.add(zone_id)
        _LOGGER.info(
            "Offset auto-cal for zone %s waits for the window and cooldown",
            zone_id,
        )

    def _drop_stale_interval_holds(self) -> None:
        for zone_id in list(self._offset_cal_interval_pending):
            if self.zone_offset_cal_hours(zone_id):
                continue
            self._offset_cal_interval_pending.discard(zone_id)
            self._offset_cal_window_was_open.discard(zone_id)
        if not self._offset_cal_interval_pending:
            self._cancel_interval_cal_hold()
            return
        self._sync_interval_window_watch()

    def _cancel_interval_cal_hold(self) -> None:
        self._offset_cal_interval_pending.clear()
        if self._offset_cal_interval_retry is not None:
            self._offset_cal_interval_retry()
            self._offset_cal_interval_retry = None
        for unsub in self._offset_cal_interval_unsubs:
            unsub()
        self._offset_cal_interval_unsubs = []
        self._offset_cal_interval_watched = ()

    def _sync_interval_window_watch(self) -> None:
        from homeassistant.helpers.event import async_track_state_change_event

        windows = self.config_entry.data.get(CONF_ZONE_WINDOW_ENTITIES) or {}
        wanted: list[str] = []
        if isinstance(windows, dict):
            for zone_id in sorted(self._offset_cal_interval_pending):
                if entity_id := windows.get(str(zone_id)):
                    wanted.append(str(entity_id))
        watched = tuple(wanted)
        if watched == self._offset_cal_interval_watched:
            return
        for unsub in self._offset_cal_interval_unsubs:
            unsub()
        self._offset_cal_interval_unsubs = []
        self._offset_cal_interval_watched = watched
        if not watched:
            return
        self._offset_cal_interval_unsubs.append(
            async_track_state_change_event(
                self.hass, list(watched), self._on_interval_window
            )
        )

    def _on_interval_window(self, _event: Any) -> None:
        self.hass.async_create_task(self._async_flush_interval_cal())

    def _arm_interval_cal_retry(self, when: datetime | None) -> None:
        if self._offset_cal_interval_retry is not None:
            self._offset_cal_interval_retry()
            self._offset_cal_interval_retry = None
        if when is None:
            return
        delay = (when - dt_util.utcnow()).total_seconds()
        if delay <= 0:
            return
        from homeassistant.helpers.event import async_call_later

        self._offset_cal_interval_retry = async_call_later(
            self.hass, delay, self._async_interval_cal_retry
        )

    async def _async_interval_cal_retry(self, _now: datetime) -> None:
        self._offset_cal_interval_retry = None
        await self._async_flush_interval_cal()

    async def _async_flush_interval_cal(self, _now: datetime | None = None) -> None:
        if self._offset_cal_interval_flushing:
            self._offset_cal_interval_flush_again = True
            return
        self._offset_cal_interval_flushing = True
        try:
            await self._flush_interval_cal_once()
        finally:
            self._offset_cal_interval_flushing = False
            if self._offset_cal_interval_flush_again:
                self._offset_cal_interval_flush_again = False
                await self._async_flush_interval_cal()

    async def _flush_interval_cal_once(self) -> None:
        now = dt_util.utcnow()
        settle_wait = timedelta(
            seconds=self._offset_cal_cooldown_s(
                CONF_OFFSET_CAL_WINDOW_SETTLE_S, DEFAULT_OFFSET_CAL_WINDOW_SETTLE_S
            )
        )
        retry_at: datetime | None = None
        ready: list[int] = []
        for zone_id in list(self._offset_cal_interval_pending):
            if not self.zone_offset_cal_hours(zone_id):
                self._offset_cal_interval_pending.discard(zone_id)
                self._offset_cal_window_was_open.discard(zone_id)
                continue
            if self._offset_cal_window_open(zone_id):
                self._offset_cal_window_was_open.add(zone_id)
                continue
            if zone_id in self._offset_cal_window_was_open:
                self._offset_cal_window_was_open.discard(zone_id)
                if settle_wait.total_seconds() > 0:
                    settle_until = now + settle_wait
                    self._offset_cal_window_settle_until[zone_id] = settle_until
                    retry_at = (
                        settle_until
                        if retry_at is None
                        else min(retry_at, settle_until)
                    )
                    continue
            settle_until = self._offset_cal_window_settle_until.get(zone_id)
            if settle_until is not None and now < settle_until:
                retry_at = (
                    settle_until if retry_at is None else min(retry_at, settle_until)
                )
                continue
            send_ready = self._offset_cal_send_ready_at.get(zone_id)
            if send_ready is not None and now < send_ready:
                retry_at = send_ready if retry_at is None else min(retry_at, send_ready)
                continue
            ready.append(zone_id)
        for zone_id in ready:
            self._offset_cal_interval_pending.discard(zone_id)
        for zone_id in ready:
            await self.async_calibrate_offsets("interval", zone_id=zone_id)
        if not self._offset_cal_interval_pending:
            self._cancel_interval_cal_hold()
            return
        self._sync_interval_window_watch()
        self._arm_interval_cal_retry(retry_at)

    def _zones_on_threshold(self) -> list[int]:
        from .offset_calibrate import OFFSET_CAL_THRESHOLD

        return [
            zone_id
            for zone_id in self._linked_zone_ids()
            if self.effective_zone_offset_cal_interval(zone_id) == OFFSET_CAL_THRESHOLD
        ]

    def _schedule_offset_cal_threshold_watch(self) -> None:
        from homeassistant.helpers.event import async_track_state_change_event

        for unsub in self._offset_cal_threshold_unsubs:
            unsub()
        self._offset_cal_threshold_unsubs = []
        if self._offset_cal_threshold_handle:
            self._offset_cal_threshold_handle()
            self._offset_cal_threshold_handle = None
        if self._offset_cal_threshold_retry:
            self._offset_cal_threshold_retry()
            self._offset_cal_threshold_retry = None

        zones = self._zones_on_threshold()
        if not zones:
            return
        linked = self.config_entry.data.get(CONF_ZONE_TEMP_ENTITIES) or {}
        windows = self.config_entry.data.get(CONF_ZONE_WINDOW_ENTITIES) or {}
        entity_ids: list[str] = []
        for zone_id in zones:
            if isinstance(linked, dict) and (entity_id := linked.get(str(zone_id))):
                entity_ids.append(str(entity_id))
            if isinstance(windows, dict) and (window_id := windows.get(str(zone_id))):
                entity_ids.append(str(window_id))
        if not entity_ids:
            return
        self._offset_cal_threshold_unsubs.append(
            async_track_state_change_event(
                self.hass, entity_ids, self._on_threshold_sensor
            )
        )

    def _on_threshold_sensor(self, _event: Any) -> None:
        if self._offset_cal_threshold_handle is not None:
            return
        from homeassistant.helpers.event import async_call_later

        self._offset_cal_threshold_handle = async_call_later(
            self.hass, 5, self._async_run_threshold_cal
        )

    def _offset_cal_cooldown_s(self, key: str, default: int) -> int:
        try:
            return max(0, int(self.config_entry.data.get(key, default)))
        except TypeError, ValueError:
            return default

    async def _async_run_threshold_cal(self, _now: datetime) -> None:
        self._offset_cal_threshold_handle = None
        now = dt_util.utcnow()
        send_wait = timedelta(
            seconds=self._offset_cal_cooldown_s(
                CONF_OFFSET_CAL_SEND_COOLDOWN_S, DEFAULT_OFFSET_CAL_SEND_COOLDOWN_S
            )
        )
        settle_wait = timedelta(
            seconds=self._offset_cal_cooldown_s(
                CONF_OFFSET_CAL_WINDOW_SETTLE_S, DEFAULT_OFFSET_CAL_WINDOW_SETTLE_S
            )
        )
        window = getattr(self, "window_controller", None)
        retry_at: datetime | None = None
        for zone_id in self._zones_on_threshold():
            window_open = bool(window and window.zone_window_is_open(zone_id))
            if window_open:
                self._offset_cal_window_was_open.add(zone_id)
                continue
            if zone_id in self._offset_cal_window_was_open:
                self._offset_cal_window_was_open.discard(zone_id)
                settle_until = now + settle_wait
                self._offset_cal_window_settle_until[zone_id] = settle_until
                retry_at = (
                    settle_until if retry_at is None else min(retry_at, settle_until)
                )
                continue
            settle_until = self._offset_cal_window_settle_until.get(zone_id)
            if settle_until is not None and now < settle_until:
                retry_at = (
                    settle_until if retry_at is None else min(retry_at, settle_until)
                )
                continue
            ready_at = self._offset_cal_send_ready_at.get(zone_id)
            if ready_at is not None and now < ready_at:
                retry_at = ready_at if retry_at is None else min(retry_at, ready_at)
                continue
            wrote = await self.async_calibrate_offsets("threshold", zone_id=zone_id)
            if wrote:
                ready_at = now + send_wait
                self._offset_cal_send_ready_at[zone_id] = ready_at
                retry_at = ready_at if retry_at is None else min(retry_at, ready_at)
        self._arm_threshold_retry(retry_at)

    def _arm_threshold_retry(self, when: datetime | None) -> None:
        if when is None:
            return
        delay = (when - dt_util.utcnow()).total_seconds()
        if delay <= 0:
            return
        if self._offset_cal_threshold_retry is not None:
            self._offset_cal_threshold_retry()
        from homeassistant.helpers.event import async_call_later

        self._offset_cal_threshold_retry = async_call_later(
            self.hass, delay, self._async_threshold_retry
        )

    async def _async_threshold_retry(self, _now: datetime) -> None:
        self._offset_cal_threshold_retry = None
        self._on_threshold_sensor(None)

    def note_offset_sources_changed(self) -> None:
        self._schedule_offset_cal_threshold_watch()

    async def async_set_offset_cal_interval(self, option: str) -> None:
        from .offset_calibrate import OFFSET_CAL_OPTIONS

        key = option.strip().lower()
        if key not in OFFSET_CAL_OPTIONS:
            raise HomeAssistantError(f"Unknown offset cal interval '{option}'.")
        self._update_entry_data({CONF_OFFSET_CAL_INTERVAL: key})
        self._schedule_offset_cal_timer()
        self.async_update_interval_local()
        self.async_update_listeners()
        _LOGGER.info("Offset auto-cal interval set to %s", key)

    async def async_set_zone_offset_cal_interval(
        self, zone_id: int, option: str
    ) -> None:
        from .offset_calibrate import OFFSET_CAL_INHERIT, OFFSET_CAL_OPTIONS

        key = option.strip().lower()
        if key != OFFSET_CAL_INHERIT and key not in OFFSET_CAL_OPTIONS:
            raise HomeAssistantError(f"Unknown offset cal interval '{option}'.")
        overrides = dict(
            self.config_entry.data.get(CONF_ZONE_OFFSET_CAL_INTERVALS) or {}
        )
        if key == OFFSET_CAL_INHERIT:
            overrides.pop(str(zone_id), None)
        else:
            overrides[str(zone_id)] = key
        self._update_entry_data({CONF_ZONE_OFFSET_CAL_INTERVALS: overrides})
        self._schedule_offset_cal_timer()
        self.async_update_interval_local()
        self.async_update_listeners()
        _LOGGER.info("Offset cal interval for zone %s set to %s", zone_id, key)

    async def async_set_offset_cal_threshold(
        self, value: float, zone_id: int | None = None
    ) -> None:
        if zone_id is None:
            updates: dict[str, object] = {
                CONF_OFFSET_CAL_SPREAD_THRESHOLD: round(value, 1)
            }
        else:
            overrides = dict(
                self.config_entry.data.get(CONF_ZONE_OFFSET_CAL_THRESHOLDS) or {}
            )
            if value <= 0:
                overrides.pop(str(zone_id), None)
            else:
                overrides[str(zone_id)] = round(value, 1)
            updates = {CONF_ZONE_OFFSET_CAL_THRESHOLDS: overrides}
        self._update_entry_data(updates)
        self.async_update_listeners()
        _LOGGER.info("Offset cal threshold (zone %s) set to %s", zone_id, value)

    def _update_entry_data(self, updates: dict[str, object]) -> None:
        new_data = {**self.config_entry.data, **updates}
        self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)
