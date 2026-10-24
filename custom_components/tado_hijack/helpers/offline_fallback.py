"""Drive linked climates from the cached plan while Tado cannot be called.

A valve that is unavailable is a different case and stays on LocalRecoveryQueue.
This path is no internet, or a spent daily quota: the HomeKit or Matter climate
still answers, and cloud calls wait. Heating follows the loaded week until
someone sets a manual setpoint. Auto clears that and follows the week again.
Hot water has no local actuator here, so only the intent is kept and sent when
calls are allowed again. The return is one batch: resume for schedule zones,
overlay for manual.
"""

from __future__ import annotations

import time
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import aiohttp
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.util import dt as dt_util

from ..const import (
    OFF_MAGIC_TEMP,
    POWER_OFF,
    POWER_ON,
    TEMP_TOLERANCE,
    ZONE_TYPE_HEATING,
    ZONE_TYPE_HOT_WATER,
)
from .local_climate import (
    async_apply_known_setpoint,
    climate_is_off,
    linked_climate_ids,
)
from .logging_utils import get_redacted_logger
from .optimistic_manager import ZoneOverlayFields
from .schedule import PlanSpan, cached_plan, current_plan_span
from .zone_utils import (
    get_zone_type,
    zone_follows_cloud_schedule,
    zone_id_for_serial,
)

if TYPE_CHECKING:
    from ..coordinator import TadoDataUpdateCoordinator

_LOGGER = get_redacted_logger(__name__)

_MODE_SCHEDULE = "schedule"
_MODE_MANUAL = "manual"
_UNREACHABLE_TEXT = ("timeout", "connect", "network", "unreachable", "dns")
_QUIET_S = 5.0
_HTTP_SERVER_ERROR = 500
_FAILURES_BEFORE_OFFLINE = 2


def _same_setpoint(
    power: str,
    temperature: float | None,
    other_power: str,
    other_temperature: float | None,
) -> bool:
    """True when both sides are off, or both are the same heat target."""
    if POWER_OFF in (power, other_power):
        return power == other_power
    if temperature is None or other_temperature is None:
        return False
    return abs(float(temperature) - float(other_temperature)) < TEMP_TOLERANCE


def _http_status(err: BaseException) -> int | None:
    for attr in ("status", "status_code"):
        value = getattr(err, attr, None)
        if isinstance(value, int):
            return value
    return None


def _is_quota_exhausted(err: BaseException) -> bool:
    """True when Tado refused the call because the daily quota is spent."""
    return _http_status(err) == HTTPStatus.TOO_MANY_REQUESTS


def _is_cloud_unreachable(err: BaseException) -> bool:
    """True when the failure is transport, not a rejected Tado payload.

    A response status wins over the exception type. HTTP 4xx, including 429,
    is not a dead link. Connection errors have no status.
    """
    status = _http_status(err)
    if status is not None:
        return status >= _HTTP_SERVER_ERROR
    if isinstance(err, TimeoutError | aiohttp.ClientError | OSError):
        return True
    if type(err).__name__ != "TadoError":
        return False
    text = str(err).lower()
    return any(word in text for word in _UNREACHABLE_TEXT)


class OfflineFallback:
    """Per-zone schedule or manual intent for one coordinator while cloud is down."""

    def __init__(self, coordinator: TadoDataUpdateCoordinator) -> None:
        """Start online. Nothing is tracked until a call cannot reach Tado."""
        self._coordinator = coordinator
        self._offline = False
        self._flushing = False
        self._fails = 0
        self._mode: dict[int, str] = {}
        self._manual: dict[int, tuple[str, float | None]] = {}
        self._pending: dict[int, tuple[str, str | None, float | None]] = {}
        self._dirty: set[int] = set()
        self._quiet_until: dict[str, float] = {}
        self._listening = False

    @property
    def active(self) -> bool:
        """True while cloud calls wait, until a call is allowed again."""
        return self._offline

    def start(self) -> None:
        """Watch local climate changes so a hand turn leaves the schedule."""
        if self._listening:
            return
        self._coordinator.availability_tracker.register_on_state(self._on_climate)
        self._listening = True

    def shutdown(self) -> None:
        """Drop the climate listener."""
        if self._listening:
            self._coordinator.availability_tracker.unregister_on_state(self._on_climate)
            self._listening = False

    def remember_schedule(self, zone_id: int) -> None:
        """Keep a resume until the cloud call lands or calls have to wait."""
        self._pending[zone_id] = (_MODE_SCHEDULE, None, None)

    def remember_manual(
        self,
        zone_id: int,
        power: str | None = None,
        temperature: float | None = None,
    ) -> None:
        """Keep a manual setpoint until the cloud call lands or calls have to wait."""
        if temperature == OFF_MAGIC_TEMP:
            power = POWER_OFF
            temperature = None
        self._pending[zone_id] = (_MODE_MANUAL, power, temperature)

    def suppress_writes(self, entity_ids: list[str]) -> None:
        """Ignore our own climate writes so they are not a hand change."""
        until = time.monotonic() + _QUIET_S
        for entity_id in entity_ids:
            self._quiet_until[entity_id] = until

    def note_call_failed(self, err: BaseException) -> bool:
        """Hold calls for quota or transport. False when the payload was rejected."""
        if _is_quota_exhausted(err):
            self.note_quota_exhausted()
            return True
        if _is_cloud_unreachable(err):
            self.note_unreachable()
            return True
        return False

    def note_unreachable(self) -> None:
        """Enter offline after two transport failures, or one failed command."""
        self._fails += 1
        if self._offline:
            self._apply_fresh_pending()
            return
        if self._fails < _FAILURES_BEFORE_OFFLINE and not self._pending:
            return
        self._enter("Tado cloud unreachable.")

    def note_quota_exhausted(self) -> None:
        """Same local plan as a dead link. A reset flushes. Do not send now."""
        if self._flushing:
            self._offline = True
            return
        if self._offline:
            self._apply_fresh_pending()
            return
        self._enter("Tado quota is spent.")

    def note_reachable(self) -> None:
        """A call was allowed. Flush once, unless the quota counter is now empty."""
        self._fails = 0
        if self._coordinator.rate_limit.out_of_quota:
            self.note_quota_exhausted()
            return
        if not self._offline or self._flushing:
            self._pending.clear()
            return
        self._coordinator.hass.async_create_task(self.async_flush())

    def _apply_fresh_pending(self) -> None:
        if fresh := self._absorb_pending():
            self._coordinator.hass.async_create_task(self._async_apply_ids(fresh))

    def _enter(self, reason: str) -> None:
        self._offline = True
        self._absorb_pending()
        self._seed()
        _LOGGER.warning("%s Linked climates follow the cached plan.", reason)
        self._coordinator.hass.async_create_task(self.async_apply_entered())

    async def async_take_auto(self, zone_id: int) -> bool:
        """Handle auto locally. False when the cloud path should run."""
        if not self._offline:
            return False
        self._mode[zone_id] = _MODE_SCHEDULE
        self._manual.pop(zone_id, None)
        self._dirty.add(zone_id)
        self._mark_overlay(zone_id, overlay=False, operation_mode="auto")
        await self._async_apply_zone(zone_id)
        _LOGGER.info("Offline auto for zone %s uses the cached plan", zone_id)
        return True

    async def async_take_manual(
        self,
        zone_id: int,
        power: str,
        temperature: float | None,
    ) -> bool:
        """Handle a manual setpoint locally. False when the cloud path should run."""
        if not self._offline:
            return False
        self._mode[zone_id] = _MODE_MANUAL
        self._manual[zone_id] = (power, temperature)
        self._dirty.add(zone_id)
        self._mark_overlay(
            zone_id,
            overlay=True,
            power=power,
            temperature=temperature,
        )
        await self._async_apply_manual(zone_id, power, temperature)
        _LOGGER.info(
            "Offline manual zone %s (%s)",
            zone_id,
            "off" if power == POWER_OFF else temperature,
        )
        return True

    async def async_apply_schedules(self) -> None:
        """Move every schedule zone to the block that covers now."""
        if not self._offline:
            return
        for zone_id in list(self._mode):
            if self._mode.get(zone_id) == _MODE_SCHEDULE:
                await self._async_apply_zone(zone_id)

    async def note_plan_changed(self, zone_id: int) -> None:
        """Follow a schedule edit now. A manual zone keeps its setpoint.

        The current block may have a new temperature, or a new block may
        cover now. Later edges still come from the plan timer.
        """
        if not self._offline:
            return
        if self._mode.get(zone_id) == _MODE_MANUAL:
            return
        if self._mode.get(zone_id) != _MODE_SCHEDULE:
            if not zone_follows_cloud_schedule(self._coordinator, zone_id):
                return
            self._mode[zone_id] = _MODE_SCHEDULE
            if self._is_hot_water(zone_id):
                self._dirty.add(zone_id)
        await self._async_apply_zone(zone_id)

    async def async_apply_entered(self) -> None:
        """Paint the plan, and any manual intent captured as the link dropped."""
        if not self._offline:
            return
        await self._async_apply_ids(list(self._mode))

    async def async_flush(self) -> None:
        """Send one resume or overlay per dirty zone now that the cloud answers."""
        if self._flushing:
            return
        dirty = list(self._dirty)
        modes = dict(self._mode)
        manuals = dict(self._manual)
        held = self._coordinator.api_manager.held_zone_ids()
        self._flushing = True
        self._offline = False
        _LOGGER.info("Tado cloud is back. Flushing %d offline zone(s)", len(dirty))
        try:
            for zone_id in dirty:
                if zone_id in held:
                    continue
                if modes.get(zone_id) == _MODE_MANUAL:
                    power, temperature = manuals.get(zone_id, (POWER_ON, None))
                    await self._async_flush_manual(zone_id, power, temperature)
                else:
                    await self._async_flush_auto(zone_id)
        finally:
            self._flushing = False
        if self._offline:
            return
        self._dirty.clear()
        self._mode.clear()
        self._manual.clear()
        self._quiet_until.clear()
        self._coordinator.api_manager.release_held()

    def _absorb_pending(self) -> list[int]:
        zone_ids = list(self._pending)
        for zone_id, (mode, power, temperature) in self._pending.items():
            self._mode[zone_id] = mode
            self._dirty.add(zone_id)
            if mode == _MODE_MANUAL:
                self._manual[zone_id] = (power or POWER_ON, temperature)
            else:
                self._manual.pop(zone_id, None)
        self._pending.clear()
        return zone_ids

    def _seed(self) -> None:
        """Zones with a loaded plan keep schedule unless a manual overlay is on."""
        for zone_id in self._plan_zone_ids():
            if zone_id in self._mode:
                continue
            if zone_follows_cloud_schedule(self._coordinator, zone_id):
                self._mode[zone_id] = _MODE_SCHEDULE
                if self._is_hot_water(zone_id):
                    self._dirty.add(zone_id)
            else:
                self._mode[zone_id] = _MODE_MANUAL

    def _plan_zone_ids(self) -> list[int]:
        ids: list[int] = []
        cache = self._coordinator.data_manager.schedule_blocks_cache
        for key in cache:
            try:
                zone_id = int(key)
            except TypeError, ValueError:
                continue
            days, _timetable = cached_plan(cache, zone_id)
            if days:
                ids.append(zone_id)
        return ids

    def _known_power_temp(self, zone_id: int) -> tuple[str, float | None] | None:
        """Power and target already stored for a manual zone. None when unknown."""
        power = self._coordinator.optimistic.get_zone_power(zone_id)
        temperature = self._coordinator.optimistic.get_zone_temperature(zone_id)
        if power is None and self._coordinator.data is not None:
            state = self._coordinator.data.zone_states.get(str(zone_id))
            setting = getattr(state, "setting", None) if state else None
            power = getattr(setting, "power", None) if setting else None
            temp_obj = getattr(setting, "temperature", None) if setting else None
            raw = getattr(temp_obj, "celsius", None) if temp_obj else None
            temperature = float(raw) if isinstance(raw, int | float) else None
        if not isinstance(power, str):
            return None
        if temperature is not None and not isinstance(temperature, int | float):
            temperature = None
        return power, float(temperature) if temperature is not None else None

    def _is_hot_water(self, zone_id: int) -> bool:
        if self._coordinator._is_tadox_hot_water_zone(zone_id):
            return True
        zone = self._coordinator.zones_meta.get(zone_id)
        return get_zone_type(zone, None) == ZONE_TYPE_HOT_WATER

    def _is_local_heating(self, zone_id: int) -> bool:
        """Heating zone with a real metadata row. Hot water and missing rows are not."""
        if self._is_hot_water(zone_id):
            return False
        zone = self._coordinator.zones_meta.get(zone_id)
        return False if zone is None else get_zone_type(zone) == ZONE_TYPE_HEATING

    def _climates_to_paint(self, zone_id: int) -> list[str] | None:
        """Linked heating climates, or None when this zone must not be written."""
        if not self._is_local_heating(zone_id):
            return None
        if self._coordinator.window_controller.zone_window_is_open(zone_id):
            return None
        entity_ids = linked_climate_ids(self._coordinator, zone_id)
        return entity_ids or None

    def _on_climate(self, entity_id: str) -> None:
        if time.monotonic() < self._quiet_until.get(entity_id, 0.0):
            return
        if not self._offline:
            return
        serial = self._coordinator.availability_tracker.serial_for_entity(entity_id)
        if serial is None:
            return
        zone_id = zone_id_for_serial(self._coordinator.zones_meta, serial)
        if zone_id is None:
            return
        if self._coordinator.window_controller.zone_window_is_open(zone_id):
            return
        state = self._coordinator.hass.states.get(entity_id)
        if state is None or state.state in {"unavailable", "unknown"}:
            return
        if climate_is_off(state):
            power, temperature = POWER_OFF, None
        else:
            raw = state.attributes.get(ATTR_TEMPERATURE)
            temperature = float(raw) if isinstance(raw, int | float) else None
            power = POWER_ON
        if self._remember_known_manual(zone_id, power, temperature):
            return
        if self._setpoint_matches(zone_id, power, temperature):
            return
        self._manual[zone_id] = (power, temperature)
        self._mode[zone_id] = _MODE_MANUAL
        self._dirty.add(zone_id)
        self._mark_overlay(
            zone_id,
            overlay=True,
            power=power,
            temperature=temperature,
        )
        _LOGGER.info(
            "Offline hand change on %s marks zone %s manual", entity_id, zone_id
        )

    def _remember_known_manual(
        self, zone_id: int, power: str, temperature: float | None
    ) -> bool:
        """Store the cloud manual setpoint the first time we see it. No flush."""
        if self._mode.get(zone_id) != _MODE_MANUAL or zone_id in self._manual:
            return False
        known = self._known_power_temp(zone_id)
        if known is None or not _same_setpoint(power, temperature, known[0], known[1]):
            return False
        self._manual[zone_id] = (power, temperature)
        return True

    def _setpoint_matches(
        self, zone_id: int, power: str, temperature: float | None
    ) -> bool:
        """True when this reading is the plan or the manual intent, not a new hand change.

        Current-temperature updates fire the same listener. A zone we do not
        track stays untouched.
        """
        mode = self._mode.get(zone_id)
        if mode is None:
            return True
        if mode == _MODE_MANUAL and zone_id in self._manual:
            stored_power, stored_temp = self._manual[zone_id]
            return _same_setpoint(power, temperature, stored_power, stored_temp)
        if mode != _MODE_SCHEDULE:
            return False
        span = self._cached_span(zone_id)
        if span is None:
            return False
        return _same_setpoint(power, temperature, span.power, span.temperature)

    def _cached_span(self, zone_id: int) -> PlanSpan | None:
        """Block that covers now, or None when the cache has no block there."""
        days, timetable = cached_plan(
            self._coordinator.data_manager.schedule_blocks_cache, zone_id
        )
        return current_plan_span(days, dt_util.now(), timetable) if days else None

    async def async_paint_cached_block(self, zone_id: int) -> bool:
        """Set linked climates to the cached block that covers now.

        No Tado call. Hot water, a missing zone, an empty plan, a gap, an open
        window, and a climate that is unavailable or unknown do not write.
        """
        entity_ids = self._climates_to_paint(zone_id)
        if entity_ids is None:
            return False
        span = self._cached_span(zone_id)
        if span is None or (span.power == POWER_ON and span.temperature is None):
            return False
        self.suppress_writes(entity_ids)
        _LOGGER.debug(
            "Cached block on zone %s (%s)",
            zone_id,
            "off" if span.power == POWER_OFF else span.temperature,
        )
        await async_apply_known_setpoint(
            self._coordinator.hass,
            entity_ids,
            power=span.power,
            temperature=span.temperature,
        )
        return True

    async def _async_apply_zone(self, zone_id: int) -> None:
        """Paint one heating zone. Hot water has nothing local to paint."""
        if await self.async_paint_cached_block(zone_id):
            self._dirty.add(zone_id)

    async def _async_apply_ids(self, zone_ids: list[int]) -> None:
        if not self._offline:
            return
        for zone_id in zone_ids:
            mode = self._mode.get(zone_id)
            if mode == _MODE_SCHEDULE:
                await self._async_apply_zone(zone_id)
            elif mode == _MODE_MANUAL and zone_id in self._manual:
                power, temperature = self._manual[zone_id]
                await self._async_apply_manual(zone_id, power, temperature)

    async def _async_apply_manual(
        self, zone_id: int, power: str, temperature: float | None
    ) -> None:
        entity_ids = self._climates_to_paint(zone_id)
        if entity_ids is None:
            return
        self.suppress_writes(entity_ids)
        await async_apply_known_setpoint(
            self._coordinator.hass,
            entity_ids,
            power=power,
            temperature=temperature,
        )

    def _mark_overlay(self, zone_id: int, **fields: Any) -> None:
        overlay = bool(fields.pop("overlay"))
        self._coordinator.optimistic.apply_zone_state(
            zone_id,
            overlay,
            fields=ZoneOverlayFields(**fields),
        )
        self._coordinator.async_update_listeners()

    async def _async_flush_auto(self, zone_id: int) -> None:
        if self._is_hot_water(zone_id):
            await self._coordinator.async_set_hot_water_auto(zone_id)
            return
        await self._coordinator.async_set_zone_auto(zone_id)

    async def _async_flush_manual(
        self, zone_id: int, power: str, temperature: float | None
    ) -> None:
        if self._is_hot_water(zone_id):
            if power == POWER_OFF:
                await self._coordinator.async_set_hot_water_off(zone_id)
            else:
                await self._coordinator.async_set_hot_water_heat(
                    zone_id, temperature=temperature
                )
            return
        if power != POWER_OFF and temperature is None:
            return
        await self._coordinator.async_set_zone_overlay(
            zone_id,
            power=power,
            temperature=temperature,
        )
