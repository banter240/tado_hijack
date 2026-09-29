"""External window sensor handling for Tado zones."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.const import (
    STATE_ON,
    STATE_OPEN,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, callback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
)

from ..const import (
    CONF_WINDOW_RESUME_BATCH,
    CONF_WINDOW_RESUME_BATCH_S,
    CONF_ZONE_WINDOW_ENTITIES,
    CONF_ZONE_WINDOW_MODES,
    DEFAULT_WINDOW_RESUME_BATCH,
    DEFAULT_WINDOW_RESUME_BATCH_S,
    MAX_WINDOW_RESUME_BATCH_S,
    MIN_WINDOW_RESUME_BATCH_S,
    OFF_MAGIC_TEMP,
    POWER_OFF,
    POWER_ON,
    WINDOW_MODE_DIRECT,
    WINDOW_MODE_TIMEOUT,
    WINDOW_MODES,
    WINDOW_SENSOR_NONE,
)
from .local_climate import (
    async_apply_available,
    async_set_off,
    async_set_temperature,
)
from .logging_utils import get_redacted_logger
from .optimistic_manager import ZoneOverlayFields
from .zone_utils import trv_serials

if TYPE_CHECKING:
    from ..coordinator import TadoDataUpdateCoordinator

_LOGGER = get_redacted_logger(__name__)

# Contact sensors report "on" (binary_sensor convention) or "open" (covers).
_OPEN_STATES = {STATE_ON, STATE_OPEN}
_STORE_KEY = "window_pre_states"
_PENDING_RESUME = "resume"
_PENDING_RESTORE = "restore"
# Manual local-only off has no cloud command to refresh the UI.
_MANUAL_HOLD_GRACE_S = 7 * 24 * 3600
# Cloud resume is queued after the hold; keep AUTO on screen until then.
_RESUME_GRACE_PAD_S = 90


@dataclass
class _WindowPreState:
    """Zone state from before this window episode turned it off."""

    schedule_active: bool
    temperature: float | None
    power: str | None
    cloud_off_sent: bool = False
    pending: str | None = None
    assume_schedule: bool = False
    released: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> _WindowPreState:
        temp = raw.get("temperature")
        power = raw.get("power")
        pending = raw.get("pending")
        if pending not in {_PENDING_RESUME, _PENDING_RESTORE}:
            pending = None
        return cls(
            schedule_active=bool(raw.get("schedule_active")),
            temperature=float(temp) if isinstance(temp, int | float) else None,
            power=str(power) if power else None,
            cloud_off_sent=bool(raw.get("cloud_off_sent")),
            pending=pending,
            assume_schedule=bool(raw.get("assume_schedule")),
            released=bool(raw.get("released")),
        )


class WindowController:
    """Drive zone off and resume from linked contact sensors.

    Timeout mode also resumes when the open-window timer ends while the
    sensor is still open, so a dead battery cannot hold the zone off.
    """

    def __init__(self, coordinator: TadoDataUpdateCoordinator) -> None:
        self._coordinator = coordinator
        self._hass = coordinator.hass
        self._subs: dict[str, Callable[[], None]] = {}
        self._zones_by_sensor: dict[str, set[int]] = defaultdict(set)
        self._timers: dict[int, Callable[..., Any]] = {}
        # Close or the self-heal timer resumes only if this zone was turned off.
        self._off_active: set[int] = set()
        self._snaps: dict[int, _WindowPreState] = {}
        self._epoch: dict[int, int] = {}
        self._batch_handle: Callable[[], None] | None = None
        self._persist_lock = asyncio.Lock()
        self._persist_task: asyncio.Task[None] | None = None
        self._persist_again = False

    def zone_window_is_open(self, zone_id: int) -> bool:
        entity_id = self._sensor_map().get(str(zone_id))
        if not entity_id:
            return False
        state = self._hass.states.get(entity_id)
        return bool(state and state.state in _OPEN_STATES)

    def _sensor_map(self) -> dict[str, str]:
        raw = self._coordinator.config_entry.data.get(CONF_ZONE_WINDOW_ENTITIES) or {}
        return {str(zid): eid for zid, eid in raw.items() if eid}

    def get_zone_window_mode(self, zone_id: int) -> str:
        modes = self._coordinator.config_entry.data.get(CONF_ZONE_WINDOW_MODES) or {}
        mode = str(modes.get(str(zone_id), ""))
        return mode if mode in WINDOW_MODES else WINDOW_MODE_DIRECT

    def _batch_enabled(self) -> bool:
        return bool(
            self._coordinator.config_entry.data.get(
                CONF_WINDOW_RESUME_BATCH, DEFAULT_WINDOW_RESUME_BATCH
            )
        )

    def _batch_seconds(self) -> float:
        raw = self._coordinator.config_entry.data.get(
            CONF_WINDOW_RESUME_BATCH_S, DEFAULT_WINDOW_RESUME_BATCH_S
        )
        try:
            seconds = float(raw)
        except TypeError, ValueError:
            seconds = float(DEFAULT_WINDOW_RESUME_BATCH_S)
        return float(
            min(MAX_WINDOW_RESUME_BATCH_S, max(MIN_WINDOW_RESUME_BATCH_S, seconds))
        )

    def _local_entity_ids(self, zone_id: int) -> list[str]:
        if self._coordinator.full_cloud_mode:
            return []
        tracker = self._coordinator.availability_tracker
        return [
            entity_id
            for serial in trv_serials(self._coordinator.zones_meta, zone_id)
            if (entity_id := tracker.get_entity_id(serial))
        ]

    def _bump(self, zone_id: int) -> int:
        epoch = self._epoch.get(zone_id, 0) + 1
        self._epoch[zone_id] = epoch
        return epoch

    def _schedule_persist(self) -> None:
        if self._persist_task and not self._persist_task.done():
            self._persist_again = True
            return
        self._persist_task = self._hass.async_create_task(self._async_persist())

    async def _async_persist(self) -> None:
        async with self._persist_lock:
            while True:
                self._persist_again = False
                payload = {
                    str(zone_id): snap.to_dict()
                    for zone_id, snap in self._snaps.items()
                }
                await self._coordinator.storage.async_update(_STORE_KEY, payload)
                if not self._persist_again:
                    return

    async def _async_load_snaps(self) -> None:
        raw = await self._coordinator.storage.async_get(_STORE_KEY, {})
        if not isinstance(raw, dict):
            return
        for key, value in raw.items():
            if not isinstance(value, dict):
                continue
            try:
                zone_id = int(key)
            except TypeError, ValueError:
                continue
            self._snaps[zone_id] = _WindowPreState.from_dict(value)

    async def async_set_zone_window_sensor(self, zone_id: int, entity_id: str) -> None:
        current = dict(self._sensor_map())
        if entity_id in (WINDOW_SENSOR_NONE, ""):
            current.pop(str(zone_id), None)
            self._forget_zone(zone_id)
        else:
            current[str(zone_id)] = entity_id
        self._update_entry_data({CONF_ZONE_WINDOW_ENTITIES: current})
        self.reload_subscriptions()
        await self._async_evaluate_zone_startup(zone_id)

    async def async_set_zone_window_mode(self, zone_id: int, mode: str) -> None:
        if mode not in WINDOW_MODES:
            raise ValueError(f"Unknown window mode '{mode}'")
        modes = dict(
            self._coordinator.config_entry.data.get(CONF_ZONE_WINDOW_MODES) or {}
        )
        if mode == WINDOW_MODE_DIRECT:
            modes.pop(str(zone_id), None)
        else:
            modes[str(zone_id)] = mode
        self._update_entry_data({CONF_ZONE_WINDOW_MODES: modes})
        self._cancel_timer(zone_id)

    def _update_entry_data(self, patch: dict[str, dict[str, str]]) -> None:
        entry = self._coordinator.config_entry
        self._hass.config_entries.async_update_entry(
            entry, data={**entry.data, **patch}
        )

    def _forget_zone(self, zone_id: int) -> None:
        """Drop a zone whose sensor was unlinked. Do not invent a cloud resume."""
        self._cancel_timer(zone_id)
        self._off_active.discard(zone_id)
        self._bump(zone_id)
        snap = self._snaps.pop(zone_id, None)
        if snap and not snap.cloud_off_sent:
            self._coordinator.optimistic.clear_zone(zone_id)
            self._coordinator.async_update_listeners()
        self._disarm_if_idle()
        self._schedule_persist()

    @callback
    def reload_subscriptions(self) -> None:
        self._zones_by_sensor.clear()
        for zid, entity_id in self._sensor_map().items():
            self._zones_by_sensor[entity_id].add(int(zid))

        desired = set(self._zones_by_sensor)
        for entity_id, unsub in list(self._subs.items()):
            if entity_id not in desired:
                unsub()
                del self._subs[entity_id]
        for entity_id in desired:
            if entity_id not in self._subs:
                self._subs[entity_id] = async_track_state_change_event(
                    self._hass, [entity_id], self._async_on_sensor_event
                )

        active_zones = {int(zid) for zid in self._sensor_map()}
        for zone_id in list(self._timers):
            if zone_id not in active_zones:
                self._cancel_timer(zone_id)
                self._off_active.discard(zone_id)

        if desired:
            _LOGGER.debug("Window controller tracking sensors: %s", sorted(desired))

    async def async_start(self) -> None:
        # The local-vs-cloud choice needs the climate map. Starting the tracker
        # here is safe if recovery also starts it.
        if not self._coordinator.full_cloud_mode:
            await self._coordinator.availability_tracker.async_start()
        await self._async_load_snaps()
        if not self._batch_enabled() and any(
            snap.pending for snap in self._snaps.values()
        ):
            await self._async_flush()
        self.reload_subscriptions()
        for zone_id in {int(zid) for zid in self._sensor_map()}:
            await self._async_evaluate_zone_startup(zone_id)
        self._arm_batch()

    async def _async_evaluate_zone_startup(self, zone_id: int) -> None:
        """Apply an already-open window once. Closed windows wait for a transition."""
        entity_id = self._sensor_map().get(str(zone_id))
        if not entity_id:
            return
        state = self._hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return
        if state.state not in _OPEN_STATES:
            if self._batch_enabled():
                await self._async_startup_closed(zone_id)
            else:
                await self._async_legacy_startup_closed(zone_id)
            return

        snap = self._snaps.get(zone_id)
        if snap and snap.released:
            # Timeout already put this zone back. Do not off it again on startup.
            if not self._batch_enabled():
                self._snaps.pop(zone_id, None)
                self._schedule_persist()
            return

        if self._batch_enabled():
            await self._async_handle_open(zone_id, startup=True)
        else:
            self._snaps.pop(zone_id, None)
            await self._async_turn_off_legacy(zone_id)

        mode = self.get_zone_window_mode(zone_id)
        if mode == WINDOW_MODE_TIMEOUT and zone_id in self._off_active:
            self._start_timer(zone_id)

    async def _async_legacy_startup_closed(self, zone_id: int) -> None:
        """Option off: if a held episode left the cloud off, resume it now."""
        snap = self._snaps.pop(zone_id, None)
        self._schedule_persist()
        if snap is None or snap.released:
            return
        if snap.cloud_off_sent or snap.pending:
            _LOGGER.info("Window startup: resuming zone %s (batching off)", zone_id)
            await self._coordinator.async_set_zone_auto(zone_id)

    async def _async_startup_closed(self, zone_id: int) -> None:
        """Finish an episode whose close happened while HA was down."""
        snap = self._snaps.get(zone_id)
        if snap is None:
            return
        if snap.released:
            if not snap.pending:
                self._snaps.pop(zone_id, None)
                self._schedule_persist()
            return
        await self._async_resume(zone_id, still_open=False)

    def shutdown(self) -> None:
        """Release listeners and timers (unload / HA stop). Snapshots stay stored."""
        for unsub in self._subs.values():
            unsub()
        self._subs.clear()
        self._zones_by_sensor.clear()
        self._off_active.clear()
        for zone_id in list(self._timers):
            self._cancel_timer(zone_id)
        if self._batch_handle is not None:
            self._batch_handle()
            self._batch_handle = None

    async def _async_on_sensor_event(self, event: Event) -> None:
        entity_id = str(event.data.get("entity_id", ""))
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")

        if new_state is None or old_state is None:
            return
        if new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        is_open = new_state.state in _OPEN_STATES
        was_open = old_state.state in _OPEN_STATES
        if is_open == was_open:
            return

        for zone_id in self._zones_by_sensor.get(entity_id, set()):
            await self._async_dispatch_transition(zone_id, is_open)

    async def _async_dispatch_transition(self, zone_id: int, opened: bool) -> None:
        """Turn the zone off on open. Close resumes unless the self-heal already did."""
        mode = self.get_zone_window_mode(zone_id)

        if opened:
            self._cancel_timer(zone_id)
            await self._async_handle_open(zone_id, startup=False)
            if mode == WINDOW_MODE_TIMEOUT and zone_id in self._off_active:
                self._start_timer(zone_id)
            return

        self._cancel_timer(zone_id)
        if zone_id not in self._off_active and zone_id not in self._snaps:
            return
        await self._async_resume(zone_id, still_open=False)

    def _start_timer(self, zone_id: int) -> bool:
        self._cancel_timer(zone_id)
        timeout_s = self._coordinator.get_open_window_timeout_seconds(zone_id)
        if timeout_s <= 0:
            _LOGGER.debug(
                "Zone %s has open window detection disabled; skipping timer",
                zone_id,
            )
            return False
        self._timers[zone_id] = async_call_later(
            self._hass, timeout_s, self._make_timer_action(zone_id)
        )
        _LOGGER.debug("Window timer armed for zone %s (%ss)", zone_id, timeout_s)
        return True

    def _make_timer_action(self, zone_id: int) -> Callable[..., Any]:

        async def _expire(_now: object) -> None:
            self._timers.pop(zone_id, None)
            if zone_id not in self._off_active:
                return
            _LOGGER.warning(
                "Window timer expired for zone %s with the sensor still"
                " open; resuming heating (self-heal)",
                zone_id,
            )
            await self._async_resume(zone_id, still_open=True)

        return _expire

    @callback
    def _cancel_timer(self, zone_id: int) -> None:
        """Drop the zone's pending timer (flapping inside the window)."""
        if unsub := self._timers.pop(zone_id, None):
            unsub()

    async def _async_handle_open(self, zone_id: int, *, startup: bool) -> None:
        if not self._batch_enabled():
            await self._async_turn_off_legacy(zone_id)
            return
        snap = self._snaps.get(zone_id)
        if snap and snap.released:
            # New open after a timeout resume. Keep the original pre-state.
            # A resume that has not flushed yet must not land on top of this off.
            snap.pending = None
            snap.released = False
            self._disarm_if_idle()
        await self._async_ensure_off(
            zone_id, assume_schedule=startup and zone_id not in self._snaps
        )

    async def _async_turn_off_legacy(self, zone_id: int) -> None:
        _LOGGER.info("Window open: setting zone %s off", zone_id)
        self._off_active.add(zone_id)
        await self._coordinator.async_set_zone_off(
            zone_id, owd_timeout_s=self._cloud_owd(zone_id)
        )

    def _cloud_owd(self, zone_id: int) -> float | None:
        """Timeout handed to recovery so an offline off expires into resume."""
        if self.get_zone_window_mode(zone_id) != WINDOW_MODE_TIMEOUT:
            return None
        timeout_s = self._coordinator.get_open_window_timeout_seconds(zone_id)
        return float(timeout_s) if timeout_s > 0 else None

    def _capture_pre_state(
        self, zone_id: int, *, assume_schedule: bool
    ) -> _WindowPreState:
        coord = self._coordinator
        state = None
        if coord.data is not None:
            states = getattr(coord.data, "zone_states", None) or {}
            state = states.get(str(zone_id))
        opt_overlay = coord.optimistic.get_zone_overlay(zone_id)
        if opt_overlay is True:
            schedule = False
        elif opt_overlay is False:
            schedule = True
        else:
            schedule = not bool(state and getattr(state, "overlay_active", False))
        if assume_schedule:
            # Already open at startup: the live state may be our own previous off.
            schedule = True
        temp = coord.optimistic.get_zone_temperature(zone_id)
        setting = getattr(state, "setting", None) if state is not None else None
        if temp is None and setting is not None:
            temp_obj = getattr(setting, "temperature", None)
            celsius = getattr(temp_obj, "celsius", None) if temp_obj else None
            if celsius is not None:
                temp = float(celsius)
        power = coord.optimistic.get_zone_power(zone_id)
        if power is None and setting is not None:
            raw_power = getattr(setting, "power", None)
            power = str(raw_power) if raw_power else None
        return _WindowPreState(
            schedule_active=schedule,
            temperature=float(temp) if temp is not None else None,
            power=power,
            assume_schedule=assume_schedule,
        )

    async def _async_ensure_off(self, zone_id: int, *, assume_schedule: bool) -> None:
        if zone_id not in self._snaps:
            self._snaps[zone_id] = self._capture_pre_state(
                zone_id, assume_schedule=assume_schedule
            )
            self._schedule_persist()
        snap = self._snaps[zone_id]
        if snap.released:
            return
        self._off_active.add(zone_id)
        needs_cloud = snap.schedule_active or not self._local_entity_ids(zone_id)
        self._mark_off_optimistic(zone_id)
        epoch = self._bump(zone_id)
        await self._async_local_off(zone_id)
        if self._epoch.get(zone_id) != epoch:
            return
        if needs_cloud:
            if not snap.cloud_off_sent:
                _LOGGER.info(
                    "Window open: cloud off zone %s (schedule=%s)",
                    zone_id,
                    snap.schedule_active,
                )
                await self._coordinator.async_set_zone_off(
                    zone_id, owd_timeout_s=self._cloud_owd(zone_id)
                )
                snap.cloud_off_sent = True
                self._schedule_persist()
            return
        _LOGGER.info("Window open: local off zone %s (no schedule)", zone_id)
        self._coordinator.recovery_queue.capture_overlay(
            zone_id, power=POWER_ON, temperature=OFF_MAGIC_TEMP
        )

    def _show(
        self,
        zone_id: int,
        *,
        overlay: bool,
        fields: ZoneOverlayFields,
        grace: float,
    ) -> None:
        self._coordinator.optimistic.apply_zone_state(
            zone_id, overlay=overlay, fields=fields, grace_period=grace
        )
        self._coordinator.async_update_listeners()

    def _mark_off_optimistic(self, zone_id: int) -> None:
        self._show(
            zone_id,
            overlay=True,
            fields=ZoneOverlayFields(power=POWER_OFF),
            grace=_MANUAL_HOLD_GRACE_S,
        )

    async def _async_resume(self, zone_id: int, *, still_open: bool) -> None:
        self._off_active.discard(zone_id)
        if not self._batch_enabled():
            self._snaps.pop(zone_id, None)
            self._schedule_persist()
            _LOGGER.info("Window closed: resuming zone %s", zone_id)
            await self._coordinator.async_set_zone_auto(zone_id)
            return
        snap = self._snaps.get(zone_id)
        if snap and snap.released:
            if not still_open and not snap.pending:
                self._snaps.pop(zone_id, None)
                self._schedule_persist()
            return
        if snap is None:
            _LOGGER.info(
                "Window closed: resuming zone %s (no pre-open snapshot)", zone_id
            )
            await self._coordinator.async_set_zone_auto(zone_id)
            return

        epoch = self._bump(zone_id)
        await self._async_restore_local(zone_id, snap)
        if self._epoch.get(zone_id) != epoch:
            return
        if still_open:
            snap.released = True
        wants_resume = snap.schedule_active or snap.assume_schedule
        if wants_resume and snap.cloud_off_sent:
            snap.pending = _PENDING_RESUME
            self._mark_resume_optimistic(zone_id, snap)
            self._arm_batch()
            _LOGGER.info("Window resume queued for zone %s", zone_id)
        elif not wants_resume and snap.cloud_off_sent:
            snap.pending = _PENDING_RESTORE
            self._mark_restore_optimistic(zone_id, snap)
            self._arm_batch()
            _LOGGER.info("Window manual restore queued for zone %s", zone_id)
        else:
            self._coordinator.optimistic.clear_zone(zone_id)
            self._coordinator.async_update_listeners()
            _LOGGER.info("Window closed: local restore zone %s (no cloud)", zone_id)
            if not still_open:
                self._snaps.pop(zone_id, None)
        self._schedule_persist()

    def _mark_resume_optimistic(self, zone_id: int, snap: _WindowPreState) -> None:
        self._show(
            zone_id,
            overlay=False,
            fields=ZoneOverlayFields(temperature=snap.temperature),
            grace=self._batch_seconds() + _RESUME_GRACE_PAD_S,
        )

    def _mark_restore_optimistic(self, zone_id: int, snap: _WindowPreState) -> None:
        if snap.power == POWER_OFF or snap.temperature is None:
            return
        self._show(
            zone_id,
            overlay=True,
            fields=ZoneOverlayFields(power=POWER_ON, temperature=snap.temperature),
            grace=self._batch_seconds() + _RESUME_GRACE_PAD_S,
        )

    def _arm_batch(self) -> None:
        """Start the hold on the first pending cloud intent. Do not reset it."""
        if self._batch_handle is not None:
            return
        if not any(snap.pending for snap in self._snaps.values()):
            return
        delay = self._batch_seconds()
        if delay <= 0:
            self._hass.async_create_task(self._async_flush())
            return
        self._batch_handle = async_call_later(self._hass, delay, self._on_batch_timer)
        _LOGGER.debug("Window resume batch armed for %ss", delay)

    @callback
    def _on_batch_timer(self, _now: object) -> None:
        self._batch_handle = None
        self._hass.async_create_task(self._async_flush())

    def _disarm_if_idle(self) -> None:
        if any(snap.pending for snap in self._snaps.values()):
            return
        if self._batch_handle is not None:
            self._batch_handle()
            self._batch_handle = None

    async def _async_flush(self) -> None:
        """Send every held resume or manual restore. One queue, so they merge."""
        work: list[tuple[int, str]] = []
        for zone_id, snap in list(self._snaps.items()):
            if snap.pending:
                work.append((zone_id, snap.pending))
                snap.pending = None
        if not work:
            return
        _LOGGER.info(
            "Flushing window cloud batch (%d zone(s))",
            len(work),
        )
        for zone_id, kind in work:
            try:
                if kind == _PENDING_RESUME:
                    await self._coordinator.async_set_zone_auto(zone_id)
                elif kind == _PENDING_RESTORE:
                    await self._async_cloud_restore(zone_id)
            except Exception:
                _LOGGER.exception("Window cloud batch failed for zone %s", zone_id)
                failed = self._snaps.get(zone_id)
                if failed is not None:
                    failed.pending = kind
                continue
            self._note_cloud_sent(zone_id)
        self._schedule_persist()
        self._arm_batch()

    def _note_cloud_sent(self, zone_id: int) -> None:
        """Forget a finished episode. A timeout resume keeps the snapshot."""
        snap = self._snaps.get(zone_id)
        if snap is None:
            return
        if self.zone_window_is_open(zone_id):
            # Resume already queued. A later restart must not treat this as off.
            snap.released = True
            snap.pending = None
            snap.cloud_off_sent = False
            return
        self._snaps.pop(zone_id, None)

    async def _async_cloud_restore(self, zone_id: int) -> None:
        """Put a manual setpoint back. Resume would throw that setpoint away."""
        snap = self._snaps.get(zone_id)
        if snap is None or snap.power == POWER_OFF or snap.temperature is None:
            return
        await self._coordinator.async_set_zone_heat(zone_id, float(snap.temperature))

    async def _async_restore_local(self, zone_id: int, snap: _WindowPreState) -> None:
        if snap.power == POWER_OFF:
            await self._async_local_off(zone_id)
            self._coordinator.recovery_queue.capture_overlay(
                zone_id, power=POWER_OFF, temperature=None
            )
            return
        if snap.temperature is None:
            return
        await self._async_local_temperature(zone_id, snap.temperature)
        self._coordinator.recovery_queue.capture_overlay(
            zone_id, power=POWER_ON, temperature=snap.temperature
        )

    async def _async_local_off(self, zone_id: int) -> None:
        """Shut linked TRVs now. The cloud off may still be in debounce."""
        await async_apply_available(
            self._hass,
            self._local_entity_ids(zone_id),
            lambda entity_id: async_set_off(self._hass, entity_id, blocking=False),
            failure="Local window off failed for %s",
        )

    async def _async_local_temperature(self, zone_id: int, temperature: float) -> None:
        """Set the pre-open temperature on linked TRVs without waiting for the cloud."""
        await async_apply_available(
            self._hass,
            self._local_entity_ids(zone_id),
            lambda entity_id: async_set_temperature(
                self._hass,
                entity_id,
                temperature,
                blocking=False,
                ensure_heat=True,
            ),
            failure="Local window restore failed for %s",
        )
