"""Offset-cal config: bridge master, per-zone overrides, scheduler."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

if TYPE_CHECKING:
    from .. import TadoConfigEntry

from ..const import (
    CONF_OFFSET_CAL_INTERVAL,
    CONF_OFFSET_CAL_SPREAD_THRESHOLD,
    CONF_ZONE_OFFSET_CAL_INTERVALS,
    CONF_ZONE_OFFSET_CAL_THRESHOLDS,
    CONF_ZONE_TEMP_ENTITIES,
    DEFAULT_OFFSET_CAL_INTERVAL,
    DEFAULT_OFFSET_CAL_SPREAD_THRESHOLD,
)

_LOGGER = logging.getLogger(__name__)


class OffsetCalConfigMixin:
    """Offset-cal config access split off the coordinator.

    Host must provide: hass, config_entry, _offset_cal_unsub,
    async_calibrate_offsets, async_update_interval_local, async_update_listeners.
    """

    if TYPE_CHECKING:
        hass: HomeAssistant
        config_entry: TadoConfigEntry
        _offset_cal_unsub: Callable[[], None] | None

        def async_calibrate_offsets(
            self, trigger: str, zone_id: int | None = None
        ) -> Any: ...
        def async_update_interval_local(self) -> None: ...
        def async_update_listeners(self) -> None: ...

    def _offset_cal_option(self) -> str:
        """Bridge master interval."""
        return str(
            self.config_entry.data.get(
                CONF_OFFSET_CAL_INTERVAL, DEFAULT_OFFSET_CAL_INTERVAL
            )
        )

    def get_offset_cal_threshold(self) -> float:
        """Bridge master spread threshold."""
        return float(
            self.config_entry.data.get(
                CONF_OFFSET_CAL_SPREAD_THRESHOLD, DEFAULT_OFFSET_CAL_SPREAD_THRESHOLD
            )
        )

    def get_zone_offset_cal_interval(self, zone_id: int) -> str:
        """Zone interval override, else the bridge master option."""
        overrides = self.config_entry.data.get(CONF_ZONE_OFFSET_CAL_INTERVALS) or {}
        if isinstance(overrides, dict):
            if value := overrides.get(str(zone_id)):
                return str(value)
        return self._offset_cal_option()

    def get_zone_offset_cal_threshold(self, zone_id: int) -> float:
        """Zone threshold override, else the bridge default."""
        overrides = self.config_entry.data.get(CONF_ZONE_OFFSET_CAL_THRESHOLDS) or {}
        if isinstance(overrides, dict):
            value = overrides.get(str(zone_id))
            if value is not None and float(value) > 0:
                return float(value)
        return self.get_offset_cal_threshold()

    def zone_offset_cal_hours(self, zone_id: int) -> list[int]:
        """Clock slots for one zone based on its effective interval."""
        from .offset_calibrate import hours_from_midnight

        return hours_from_midnight(self.get_zone_offset_cal_interval(zone_id)) or []

    def _linked_zone_ids(self) -> list[int]:
        """Zone ids with a linked temperature source."""
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
        """Union of bridge + zone interval hours (feeds the scheduler)."""
        from .offset_calibrate import hours_from_midnight

        all_hours: set[int] = set(hours_from_midnight(self._offset_cal_option()) or [])
        for zone_id in self._linked_zone_ids():
            all_hours.update(self.zone_offset_cal_hours(zone_id))
        return all_hours


class OffsetCalSchedulerMixin(OffsetCalConfigMixin):
    """Clock timer and persistence on top of the config mixin."""

    def _schedule_offset_cal_timer(self) -> None:
        """One clock timer for the union of bridge + zone interval hours."""
        from homeassistant.helpers.event import async_track_time_change

        if self._offset_cal_unsub:
            self._offset_cal_unsub()
            self._offset_cal_unsub = None
        hours = sorted(self._all_offset_cal_hours())
        if not hours:
            return
        self._offset_cal_unsub = async_track_time_change(
            self.hass,
            self._on_offset_cal_tick,
            hour=hours,
            minute=0,
            second=0,
        )
        _LOGGER.info("Offset auto-cal scheduled at local hours %s", hours)

    async def _on_offset_cal_tick(self, now: datetime) -> None:
        """Calibrate each zone whose own interval covers this hour."""
        for zone_id in self._linked_zone_ids():
            if now.hour in self.zone_offset_cal_hours(zone_id):
                await self.async_calibrate_offsets("interval", zone_id=zone_id)

    async def async_set_offset_cal_interval(self, option: str) -> None:
        """Persist the bridge master interval and reschedule."""
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
        """Persist a zone interval override ('inherit' clears it)."""
        from .offset_calibrate import OFFSET_CAL_OPTIONS

        key = option.strip().lower()
        if key != "inherit" and key not in OFFSET_CAL_OPTIONS:
            raise HomeAssistantError(f"Unknown offset cal interval '{option}'.")
        overrides = dict(
            self.config_entry.data.get(CONF_ZONE_OFFSET_CAL_INTERVALS) or {}
        )
        if key == "inherit":
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
        """Persist bridge threshold (zone_id=None) or a zone override (<=0 clears)."""
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
        """Persist config changes in one place."""
        new_data = {**self.config_entry.data, **updates}
        self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)
