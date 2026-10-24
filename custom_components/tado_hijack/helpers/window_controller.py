"""External window sensor handling for Tado zones."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.const import (
    MAX_LENGTH_STATE_STATE,
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
    CONF_ZONE_WINDOW_CLOSE_DELAY_S,
    CONF_ZONE_WINDOW_ENTITIES,
    CONF_ZONE_WINDOW_MODES,
    CONF_ZONE_WINDOW_OPEN_DELAY_S,
    CONF_ZONE_WINDOW_RESUME_SCHEDULE,
    DEFAULT_WINDOW_DELAY_S,
    DEFAULT_WINDOW_RESUME_BATCH,
    DEFAULT_WINDOW_RESUME_BATCH_S,
    DEFAULT_ZONE_WINDOW_RESUME_SCHEDULE,
    MAX_WINDOW_CONTACTS,
    MAX_WINDOW_DELAY_S,
    MAX_WINDOW_RESUME_BATCH_S,
    MIN_WINDOW_RESUME_BATCH_S,
    OVERLAY_MANUAL,
    OVERLAY_TIMER,
    POWER_OFF,
    POWER_ON,
    WINDOW_MODE_DIRECT,
    WINDOW_MODE_TIMEOUT,
    WINDOW_MODES,
    WINDOW_SENSOR_NONE,
    WINDOW_SENSOR_SENTINELS,
)
from .local_climate import (
    async_apply_available,
    async_set_off,
    async_set_temperature,
    climate_is_off,
    linked_climate_ids,
)
from .logging_utils import get_redacted_logger
from .optimistic_manager import ZoneOverlayFields
from .zone_utils import zone_follows_cloud_schedule

if TYPE_CHECKING:
    from ..coordinator import TadoDataUpdateCoordinator

_LOGGER = get_redacted_logger(__name__)

# Contact sensors report "on" (binary_sensor convention) or "open" (covers).
_OPEN_STATES = {STATE_ON, STATE_OPEN}
_IGNORED_STATES = {STATE_UNAVAILABLE, STATE_UNKNOWN}
_KIND_OPEN = "open"
_KIND_CLOSED = "closed"
_KIND_UNKNOWN = "unknown"


def normalize_window_contacts(value: Any) -> list[str]:
    """One stored string or a list, capped, without blanks or duplicates."""
    if isinstance(value, str):
        items: list[Any] = [value]
    elif isinstance(value, list):
        items = value
    else:
        return []
    contacts: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        entity_id = item.strip()
        if (
            not entity_id
            or entity_id in WINDOW_SENSOR_SENTINELS
            or entity_id in contacts
        ):
            continue
        contacts.append(entity_id)
        if len(contacts) >= MAX_WINDOW_CONTACTS:
            break
    return contacts


_STORE_KEY = "window_pre_states"
_PENDING_RESUME = "resume"
_PENDING_RESTORE = "restore"
# Cloud resume is queued after the hold; keep AUTO on screen until then.
_RESUME_GRACE_PAD_S = 90
# Burst of climate reports while a HomeKit off is still in flight.
_REOFF_COOLDOWN_S = 2.0


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

    A linked climate stays local: off, and off again if it leaves off while
    the contact is open. Full cloud mode and a zone with no linked climate
    send one manual cloud off. When the room still resumes the schedule,
    close and the timeout queue that cloud resume after the local setpoint
    is back. Timeout mode also resumes when the open-window timer ends
    while the sensor is still open.
    """

    def __init__(self, coordinator: TadoDataUpdateCoordinator) -> None:
        self._coordinator = coordinator
        self._hass = coordinator.hass
        self._subs: dict[str, Callable[[], None]] = {}
        self._zones_by_sensor: dict[str, set[int]] = defaultdict(set)
        self._reoff_at: dict[str, float] = {}
        # Self-heal while the contact stays open. Not the open/close wait.
        self._timers: dict[int, Callable[[], None]] = {}
        # Wait before the off, or before the resume. One edge at a time.
        self._delay_timers: dict[int, Callable[[], None]] = {}
        # Close or the self-heal timer resumes only if this zone was turned off.
        self._off_active: set[int] = set()
        self._snaps: dict[int, _WindowPreState] = {}
        self._epoch: dict[int, int] = {}
        self._batch_handle: Callable[[], None] | None = None
        self._persist_lock = asyncio.Lock()
        self._persist_task: asyncio.Task[None] | None = None
        self._persist_again = False

    def zone_window_contacts(self, zone_id: int) -> list[str]:
        """Linked contacts. A legacy single string is a one-item list."""
        return list(self._contacts_by_zone().get(str(zone_id), ()))

    def zone_window_contact_ids(self, zone_ids: Iterable[int]) -> list[str]:
        """Unique contact entity ids for these zones, in zone then list order."""
        seen: list[str] = []
        for zone_id in zone_ids:
            for entity_id in self.zone_window_contacts(zone_id):
                if entity_id not in seen:
                    seen.append(entity_id)
        return seen

    def zone_window_contacts_state(self, zone_id: int) -> str:
        """Entity ids for the diagnostic sensor. Empty is ``none``."""
        contacts = self.zone_window_contacts(zone_id)
        if not contacts:
            return WINDOW_SENSOR_NONE
        joined = ", ".join(contacts)
        return joined if len(joined) <= MAX_LENGTH_STATE_STATE else str(len(contacts))

    def zone_window_is_open(
        self,
        zone_id: int,
        *,
        override: tuple[str, str] | None = None,
    ) -> bool:
        """True when any linked contact is open. Unknown contacts are skipped."""
        return self._window_kind(zone_id, override=override) == _KIND_OPEN

    def _window_kind(
        self,
        zone_id: int,
        *,
        override: tuple[str, str] | None = None,
    ) -> str:
        """``open`` if any contact is open, ``closed`` if one is shut, else ``unknown``."""
        saw_closed = False
        for entity_id in self.zone_window_contacts(zone_id):
            if override is not None and entity_id == override[0]:
                state_value: str | None = override[1]
            else:
                state = self._hass.states.get(entity_id)
                state_value = state.state if state is not None else None
            if state_value in _OPEN_STATES:
                return _KIND_OPEN
            if state_value is None or state_value in _IGNORED_STATES:
                continue
            saw_closed = True
        if saw_closed:
            return _KIND_CLOSED
        return _KIND_UNKNOWN

    def _contacts_by_zone(self) -> dict[str, list[str]]:
        raw = self._coordinator.config_entry.data.get(CONF_ZONE_WINDOW_ENTITIES) or {}
        if not isinstance(raw, dict):
            return {}
        mapped: dict[str, list[str]] = {}
        for zid, value in raw.items():
            if contacts := normalize_window_contacts(value):
                mapped[str(zid)] = contacts
        return mapped

    def get_zone_window_delay(self, zone_id: int, key: str) -> float:
        """Seconds to wait before acting. Missing or junk is 0."""
        raw = (self._coordinator.config_entry.data.get(key) or {}).get(
            str(zone_id), DEFAULT_WINDOW_DELAY_S
        )
        try:
            seconds = float(raw)
        except TypeError, ValueError:
            return float(DEFAULT_WINDOW_DELAY_S)
        return float(min(MAX_WINDOW_DELAY_S, max(0.0, seconds)))

    async def async_set_zone_window_delay(
        self, zone_id: int, key: str, seconds: float
    ) -> None:
        """Store a per-zone wait. 0 removes it. No Tado call."""
        if key not in (
            CONF_ZONE_WINDOW_OPEN_DELAY_S,
            CONF_ZONE_WINDOW_CLOSE_DELAY_S,
        ):
            raise ValueError(f"Unknown window delay '{key}'")
        stored = int(min(MAX_WINDOW_DELAY_S, max(0, round(seconds))))
        current = dict(self._coordinator.config_entry.data.get(key) or {})
        if stored <= 0:
            current.pop(str(zone_id), None)
        else:
            current[str(zone_id)] = stored
        self._update_entry_data({key: current})
        self._coordinator.async_update_listeners()

    def get_zone_window_mode(self, zone_id: int) -> str:
        modes = self._coordinator.config_entry.data.get(CONF_ZONE_WINDOW_MODES) or {}
        mode = str(modes.get(str(zone_id), ""))
        return mode if mode in WINDOW_MODES else WINDOW_MODE_DIRECT

    def _resume_flags(self) -> dict[str, Any]:
        raw = (
            self._coordinator.config_entry.data.get(CONF_ZONE_WINDOW_RESUME_SCHEDULE)
            or {}
        )
        return raw if isinstance(raw, dict) else {}

    def zone_resumes_schedule(self, zone_id: int) -> bool:
        """True unless this room opted out. A missing value is on."""
        raw = self._resume_flags()
        if str(zone_id) not in raw:
            return DEFAULT_ZONE_WINDOW_RESUME_SCHEDULE
        return bool(raw[str(zone_id)])

    async def async_set_zone_window_resume_schedule(
        self, zone_id: int, enabled: bool
    ) -> None:
        """Store the per-room choice. The default is removed, not written."""
        current = dict(self._resume_flags())
        if enabled == DEFAULT_ZONE_WINDOW_RESUME_SCHEDULE:
            current.pop(str(zone_id), None)
        else:
            current[str(zone_id)] = enabled
        self._update_entry_data({CONF_ZONE_WINDOW_RESUME_SCHEDULE: current})
        self._coordinator.async_update_listeners()

    def _schedule_resume_wanted(self, zone_id: int, snap: _WindowPreState) -> bool:
        return self.zone_resumes_schedule(zone_id) and (
            snap.schedule_active or snap.assume_schedule
        )

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
        return linked_climate_ids(self._coordinator, zone_id)

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

    def _store_contacts(self, zone_id: int, contacts: list[str]) -> None:
        current = dict(
            self._coordinator.config_entry.data.get(CONF_ZONE_WINDOW_ENTITIES) or {}
        )
        if stored := normalize_window_contacts(contacts):
            current[str(zone_id)] = stored
        else:
            current.pop(str(zone_id), None)
        self._update_entry_data({CONF_ZONE_WINDOW_ENTITIES: current})
        self.reload_subscriptions()
        self._coordinator.async_update_listeners()

    async def async_add_zone_window_sensor(self, zone_id: int, entity_id: str) -> None:
        """Append one contact. An already-open room is applied at once."""
        if not entity_id or entity_id in WINDOW_SENSOR_SENTINELS:
            return
        contacts = self.zone_window_contacts(zone_id)
        if entity_id in contacts:
            return
        if len(contacts) >= MAX_WINDOW_CONTACTS:
            _LOGGER.warning(
                "Zone %s already has %s window contacts",
                zone_id,
                MAX_WINDOW_CONTACTS,
            )
            return
        was_open = self.zone_window_is_open(zone_id)
        self._store_contacts(zone_id, [*contacts, entity_id])
        if not was_open and self._window_kind(zone_id) == _KIND_OPEN:
            await self._async_evaluate_zone_startup(zone_id)

    async def async_remove_zone_window_sensor(
        self, zone_id: int, entity_id: str
    ) -> None:
        """Drop one contact. The last one unlinks the zone without a cloud resume."""
        contacts = self.zone_window_contacts(zone_id)
        if entity_id not in contacts:
            return
        was_open = self.zone_window_is_open(zone_id)
        remaining = [item for item in contacts if item != entity_id]
        self._store_contacts(zone_id, remaining)
        if not remaining:
            self._forget_zone(zone_id)
            return
        if was_open and self._window_kind(zone_id) == _KIND_CLOSED:
            await self._async_dispatch_transition(zone_id, opened=False)

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
        self._drop_zone_clocks(zone_id)

    def _update_entry_data(self, patch: dict[str, Any]) -> None:
        entry = self._coordinator.config_entry
        self._hass.config_entries.async_update_entry(
            entry, data={**entry.data, **patch}
        )

    def _forget_zone(self, zone_id: int) -> None:
        """Drop a zone whose sensor was unlinked. Do not invent a cloud resume."""
        self._drop_zone_clocks(zone_id)
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
        for zid, entity_ids in self._contacts_by_zone().items():
            zone_id = int(zid)
            for entity_id in entity_ids:
                self._zones_by_sensor[entity_id].add(zone_id)

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

        active_zones = {int(zid) for zid in self._contacts_by_zone()}
        for zone_id in set(self._timers) | set(self._delay_timers):
            if zone_id not in active_zones:
                self._drop_zone_clocks(zone_id)
                self._off_active.discard(zone_id)

        if desired:
            _LOGGER.debug("Window controller tracking sensors: %s", sorted(desired))

    async def async_start(self) -> None:
        # The local-vs-cloud choice needs the climate map. Starting the tracker
        # here is safe if recovery also starts it. Full cloud mode has no local
        # climate, so the window path stays on the cloud off below.
        if not self._coordinator.full_cloud_mode:
            tracker = self._coordinator.availability_tracker
            await tracker.async_start()
            tracker.register_on_map(self._on_climate_map)
            tracker.register_on_state(self._on_climate_state)
        await self._async_load_snaps()
        if not self._batch_enabled() and any(
            snap.pending for snap in self._snaps.values()
        ):
            await self._async_flush()
        self.reload_subscriptions()
        for zone_id in {int(zid) for zid in self._contacts_by_zone()}:
            await self._async_evaluate_zone_startup(zone_id)
        self._arm_batch()

    async def _async_evaluate_zone_startup(self, zone_id: int) -> None:
        """Apply an already-open window once. Closed windows wait for a transition."""
        if not self.zone_window_contacts(zone_id):
            return
        kind = self._window_kind(zone_id)
        if kind == _KIND_UNKNOWN:
            return
        if kind == _KIND_CLOSED:
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
        """Option off: finish a held episode without waiting for a batch."""
        snap = self._snaps.get(zone_id)
        if self._uses_local(zone_id) and (snap is None or not snap.cloud_off_sent):
            if snap is not None:
                await self._async_finish_local(zone_id, snap, still_open=False)
            return
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
        tracker = self._coordinator.availability_tracker
        tracker.unregister_on_map(self._on_climate_map)
        tracker.unregister_on_state(self._on_climate_state)
        for unsub in self._subs.values():
            unsub()
        self._subs.clear()
        self._zones_by_sensor.clear()
        self._off_active.clear()
        for clock in (self._timers, self._delay_timers):
            for zone_id in list(clock):
                self._drop_clock(clock, zone_id)
        if self._batch_handle is not None:
            self._batch_handle()
            self._batch_handle = None

    async def _async_on_sensor_event(self, event: Event) -> None:
        entity_id = str(event.data.get("entity_id", ""))
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")

        if new_state is None or old_state is None:
            return
        if new_state.state in _IGNORED_STATES:
            return
        if new_state.state == old_state.state:
            return

        for zone_id in list(self._zones_by_sensor.get(entity_id, ())):
            was_open = self.zone_window_is_open(
                zone_id, override=(entity_id, old_state.state)
            )
            now_open = self.zone_window_is_open(
                zone_id, override=(entity_id, new_state.state)
            )
            if was_open == now_open:
                continue
            await self._async_dispatch_transition(zone_id, now_open)

    async def _async_dispatch_transition(self, zone_id: int, opened: bool) -> None:
        """Wait on the delay timer, then off or resume.

        The timeout timer is separate. It starts only after the off, and a
        close cancels it. A flap the other way cancels the delay, so no
        cloud call goes out. Startup does not come through here.
        A zone that is already off skips the open wait.
        """
        self._drop_clock(self._delay_timers, zone_id)
        if opened:
            if zone_id in self._off_active or not self._arm_delay(zone_id, opened=True):
                await self._async_commit_open(zone_id)
            return
        self._drop_clock(self._timers, zone_id)
        if not self._window_episode(zone_id):
            return
        if not self._arm_delay(zone_id, opened=False):
            await self._async_resume(zone_id, still_open=False)

    def _delay_key(self, *, opened: bool) -> str:
        return (
            CONF_ZONE_WINDOW_OPEN_DELAY_S if opened else CONF_ZONE_WINDOW_CLOSE_DELAY_S
        )

    def _arm_delay(self, zone_id: int, *, opened: bool) -> bool:
        """Arm the open or close wait. 0 means act now."""
        seconds = self.get_zone_window_delay(zone_id, self._delay_key(opened=opened))
        if seconds <= 0:
            return False
        self._arm_clock(
            self._delay_timers,
            zone_id,
            seconds,
            self._make_delay_action(zone_id, opened=opened),
        )
        _LOGGER.debug(
            "Window %s delay armed for zone %s (%ss)",
            "open" if opened else "close",
            zone_id,
            seconds,
        )
        return True

    def _make_delay_action(
        self, zone_id: int, *, opened: bool
    ) -> Callable[[], Awaitable[None]]:

        async def _fire() -> None:
            if self.zone_window_is_open(zone_id) != opened:
                return
            if opened:
                await self._async_commit_open(zone_id)
                return
            if not self._window_episode(zone_id):
                return
            await self._async_resume(zone_id, still_open=False)

        return _fire

    async def _async_commit_open(self, zone_id: int) -> None:
        """Turn the zone off, then arm the separate timeout timer."""
        await self._async_handle_open(zone_id, startup=False)
        if (
            self.get_zone_window_mode(zone_id) == WINDOW_MODE_TIMEOUT
            and zone_id in self._off_active
        ):
            self._start_timer(zone_id)

    def _start_timer(self, zone_id: int) -> bool:
        timeout_s = self._coordinator.get_open_window_timeout_seconds(zone_id)
        if timeout_s <= 0:
            self._drop_clock(self._timers, zone_id)
            _LOGGER.debug(
                "Zone %s has open window detection disabled; skipping timer",
                zone_id,
            )
            return False
        self._arm_clock(
            self._timers,
            zone_id,
            timeout_s,
            self._make_timer_action(zone_id),
        )
        _LOGGER.debug("Window timer armed for zone %s (%ss)", zone_id, timeout_s)
        return True

    def _make_timer_action(self, zone_id: int) -> Callable[[], Awaitable[None]]:

        async def _expire() -> None:
            if zone_id not in self._off_active:
                return
            _LOGGER.warning(
                "Window timer expired for zone %s with the sensor still"
                " open; resuming heating (self-heal)",
                zone_id,
            )
            await self._async_resume(zone_id, still_open=True)

        return _expire

    def _window_episode(self, zone_id: int) -> bool:
        """True when this zone was turned off or still has a stored pre-state."""
        return zone_id in self._off_active or zone_id in self._snaps

    @callback
    def _drop_zone_clocks(self, zone_id: int) -> None:
        """Cancel both clocks for one zone. Each clock stays its own dict."""
        self._drop_clock(self._timers, zone_id)
        self._drop_clock(self._delay_timers, zone_id)

    @callback
    def _drop_clock(self, clock: dict[int, Callable[[], None]], zone_id: int) -> None:
        """Cancel one zone on this clock. The other clock stays armed."""
        if unsub := clock.pop(zone_id, None):
            unsub()

    def _arm_clock(
        self,
        clock: dict[int, Callable[[], None]],
        zone_id: int,
        seconds: float,
        action: Callable[[], Awaitable[None]],
    ) -> None:
        """Replace one zone on this clock. A fire only drops the slot."""
        self._drop_clock(clock, zone_id)

        async def _fire(_now: object) -> None:
            clock.pop(zone_id, None)
            await action()

        clock[zone_id] = async_call_later(self._hass, seconds, _fire)

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
        if self._uses_local(zone_id):
            await self._async_ensure_off(zone_id, assume_schedule=False)
            return
        self._off_active.add(zone_id)
        await self._async_cloud_off(zone_id)

    def _cloud_owd(self, zone_id: int) -> float | None:
        """Open-window timeout in seconds, only while the zone mode is timeout."""
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
        schedule = zone_follows_cloud_schedule(coord, zone_id)
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
        local = self._uses_local(zone_id)
        epoch = self._bump(zone_id)
        if local:
            await self._async_local_off(zone_id)
            if self._epoch.get(zone_id) != epoch:
                return
            self._coordinator.recovery_queue.capture_overlay(
                zone_id, power=POWER_OFF, temperature=None
            )
            _LOGGER.info("Window open: local off zone %s", zone_id)
            return
        if self._epoch.get(zone_id) != epoch or snap.cloud_off_sent:
            return
        await self._async_cloud_off(zone_id)
        if self._epoch.get(zone_id) != epoch:
            return
        snap.cloud_off_sent = True
        self._schedule_persist()

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

    async def _async_resume(self, zone_id: int, *, still_open: bool) -> None:
        self._off_active.discard(zone_id)
        snap = self._snaps.get(zone_id)
        if self._uses_local(zone_id) and (snap is None or not snap.cloud_off_sent):
            if snap is not None:
                await self._async_finish_local(zone_id, snap, still_open=still_open)
            return
        if snap and snap.released:
            if not still_open and not snap.pending:
                self._snaps.pop(zone_id, None)
                self._schedule_persist()
            return
        if snap is None:
            if not self.zone_resumes_schedule(zone_id):
                _LOGGER.info("Window closed: zone %s resume is off", zone_id)
                return
            snap = _WindowPreState(
                schedule_active=True,
                temperature=None,
                power=None,
                cloud_off_sent=True,
                assume_schedule=True,
                released=still_open,
            )
            self._snaps[zone_id] = snap
            self._queue_cloud_intent(zone_id, snap, _PENDING_RESUME)
            self._schedule_persist()
            return

        epoch = self._bump(zone_id)
        await self._async_restore_local(zone_id, snap)
        if self._epoch.get(zone_id) != epoch:
            return
        if still_open:
            snap.released = True
        wants_resume = self._schedule_resume_wanted(zone_id, snap)
        if wants_resume and snap.cloud_off_sent:
            self._queue_cloud_intent(zone_id, snap, _PENDING_RESUME)
        elif not wants_resume and snap.cloud_off_sent:
            self._queue_cloud_intent(zone_id, snap, _PENDING_RESTORE)
        else:
            self._coordinator.optimistic.clear_zone(zone_id)
            self._coordinator.async_update_listeners()
            _LOGGER.info("Window closed: local restore zone %s (no cloud)", zone_id)
            if not still_open:
                self._snaps.pop(zone_id, None)
        self._schedule_persist()

    def _queue_cloud_intent(
        self, zone_id: int, snap: _WindowPreState, kind: str
    ) -> None:
        """Hold one cloud resume or manual restore for the shared batch."""
        snap.pending = kind
        if kind == _PENDING_RESUME:
            self._mark_resume_optimistic(zone_id, snap)
            _LOGGER.info("Window resume queued for zone %s", zone_id)
        else:
            self._mark_restore_optimistic(zone_id, snap)
            _LOGGER.info("Window manual restore queued for zone %s", zone_id)
        self._arm_batch()

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
        delay = self._batch_seconds() if self._batch_enabled() else 0.0
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

    def _uses_local(self, zone_id: int) -> bool:
        """True when a HomeKit or Matter climate can hold the zone. False in full cloud mode."""
        return bool(self._local_entity_ids(zone_id))

    def _hold_active(self, zone_id: int) -> bool:
        if zone_id not in self._off_active:
            return False
        snap = self._snaps.get(zone_id)
        if snap is not None and snap.released:
            return False
        return self.zone_window_is_open(zone_id)

    def _held_zones(self, entity_id: str) -> list[int]:
        zones: list[int] = []
        for key in self._contacts_by_zone():
            zone_id = int(key)
            if entity_id not in self._local_entity_ids(zone_id):
                continue
            if self._hold_active(zone_id):
                zones.append(zone_id)
        return zones

    @callback
    def _on_climate_map(self) -> None:
        self._hass.async_create_task(self._async_catch_open_holds())

    @callback
    def _on_climate_state(self, entity_id: str) -> None:
        zones = self._held_zones(entity_id)
        if not zones:
            return
        state = self._hass.states.get(entity_id)
        if (
            state is None
            or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN)
            or climate_is_off(state)
        ):
            return
        self._hass.async_create_task(self._async_reoff_entity(entity_id, zones))

    async def _async_catch_open_holds(self) -> None:
        seen: set[str] = set()
        for key in self._contacts_by_zone():
            zone_id = int(key)
            if not self._hold_active(zone_id):
                continue
            for entity_id in self._local_entity_ids(zone_id):
                if entity_id in seen:
                    continue
                seen.add(entity_id)
                state = self._hass.states.get(entity_id)
                if state is None or climate_is_off(state):
                    continue
                if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                    continue
                await self._async_reoff_entity(entity_id, [zone_id])

    async def _async_reoff_entity(self, entity_id: str, zones: list[int]) -> None:
        now = time.monotonic()
        if now - self._reoff_at.get(entity_id, 0.0) < _REOFF_COOLDOWN_S:
            return
        self._reoff_at[entity_id] = now
        _LOGGER.info(
            "Window still open: turning %s off again (zones %s)",
            entity_id,
            sorted(zones),
        )
        try:
            self._coordinator.offline_fallback.suppress_writes([entity_id])
            await async_set_off(self._hass, entity_id, blocking=False)
        except Exception:
            _LOGGER.warning(
                "Local window re-off failed for %s", entity_id, exc_info=True
            )

    async def _async_finish_local(
        self, zone_id: int, snap: _WindowPreState, *, still_open: bool
    ) -> None:
        if snap.released:
            if not still_open and not snap.pending:
                self._snaps.pop(zone_id, None)
                self._schedule_persist()
            return
        snap.pending = None
        self._disarm_if_idle()
        if still_open:
            snap.released = True
        epoch = self._bump(zone_id)
        await self._async_restore_local(zone_id, snap)
        if self._epoch.get(zone_id) != epoch:
            return
        if self._schedule_resume_wanted(zone_id, snap):
            self._queue_cloud_intent(zone_id, snap, _PENDING_RESUME)
            self._schedule_persist()
            return
        self._coordinator.optimistic.clear_zone(zone_id)
        self._coordinator.async_update_listeners()
        _LOGGER.info(
            "Window %s: local restore zone %s",
            "timeout" if still_open else "closed",
            zone_id,
        )
        if not still_open:
            self._snaps.pop(zone_id, None)
        self._schedule_persist()

    async def _async_cloud_off(self, zone_id: int) -> None:
        """Unlimited manual off, or the open-window duration in timeout mode.

        Same call as ``set_mode`` with ``hvac_mode: off`` and ``overlay: manual``.
        A duration becomes a timer. Full cloud mode always uses this path.
        """
        timeout_s = self._cloud_owd(zone_id)
        minutes = int(timeout_s // 60) if timeout_s else None
        _LOGGER.info(
            "Window open: cloud off zone %s (%s)",
            zone_id,
            f"{minutes}min" if minutes else "unlimited",
        )
        await self._coordinator.async_set_zone_hvac_mode(
            zone_id,
            "off",
            duration=minutes,
            overlay_mode=OVERLAY_TIMER if minutes else OVERLAY_MANUAL,
            refresh_after=False,
        )

    async def _async_local_off(self, zone_id: int) -> None:
        """Turn linked climates off."""
        self._coordinator.offline_fallback.suppress_writes(
            self._local_entity_ids(zone_id)
        )
        await async_apply_available(
            self._hass,
            self._local_entity_ids(zone_id),
            lambda entity_id: async_set_off(self._hass, entity_id, blocking=False),
            failure="Local window off failed for %s",
        )

    async def _async_local_temperature(self, zone_id: int, temperature: float) -> None:
        """Set the pre-open temperature on linked TRVs without waiting for the cloud."""
        self._coordinator.offline_fallback.suppress_writes(
            self._local_entity_ids(zone_id)
        )
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
