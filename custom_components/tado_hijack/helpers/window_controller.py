"""External window sensor handling for Tado zones."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from homeassistant.const import STATE_ON, STATE_OPEN, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, callback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
)

from ..const import (
    CONF_ZONE_WINDOW_ENTITIES,
    CONF_ZONE_WINDOW_MODES,
    WINDOW_MODE_DIRECT,
    WINDOW_MODE_TIMEOUT,
    WINDOW_MODES,
    WINDOW_SENSOR_NONE,
)
from .logging_utils import get_redacted_logger

if TYPE_CHECKING:
    from ..coordinator import TadoDataUpdateCoordinator

_LOGGER = get_redacted_logger(__name__)

# Contact sensors report "on" (binary_sensor convention) or "open" (covers).
_OPEN_STATES = {STATE_ON, STATE_OPEN}


class WindowController:
    """Drive zone off/resume from linked contact sensors.

    Both modes turn the zone off on open and resume on close. ``timeout`` also
    resumes when the open-window timer expires while the sensor is still open,
    so a dead battery cannot hold the zone off.
    """

    def __init__(self, coordinator: TadoDataUpdateCoordinator) -> None:
        """Initialize the window controller."""
        self._coordinator = coordinator
        self._hass = coordinator.hass
        self._subs: dict[str, Callable[[], None]] = {}
        self._zones_by_sensor: dict[str, set[int]] = defaultdict(set)
        self._timers: dict[int, Callable[..., Any]] = {}
        # Close or the self-heal timer resumes only if this zone was turned off.
        self._off_active: set[int] = set()

    def _sensor_map(self) -> dict[str, str]:
        """Return the persisted {zone_id: sensor_entity_id} mapping."""
        raw = self._coordinator.config_entry.data.get(CONF_ZONE_WINDOW_ENTITIES) or {}
        return {str(zid): eid for zid, eid in raw.items() if eid}

    def get_zone_window_mode(self, zone_id: int) -> str:
        """Return the persisted window mode for a zone (default: direct)."""
        modes = self._coordinator.config_entry.data.get(CONF_ZONE_WINDOW_MODES) or {}
        mode = str(modes.get(str(zone_id), ""))
        return mode if mode in WINDOW_MODES else WINDOW_MODE_DIRECT

    async def async_set_zone_window_sensor(self, zone_id: int, entity_id: str) -> None:
        """Persist a zone sensor link and re-subscribe without reload."""
        current = dict(self._sensor_map())
        if entity_id in (WINDOW_SENSOR_NONE, ""):
            current.pop(str(zone_id), None)
            self._cancel_timer(zone_id)
            self._off_active.discard(zone_id)
        else:
            current[str(zone_id)] = entity_id
        self._update_entry_data({CONF_ZONE_WINDOW_ENTITIES: current})
        self.reload_subscriptions()
        await self._async_evaluate_zone_startup(zone_id)

    async def async_set_zone_window_mode(self, zone_id: int, mode: str) -> None:
        """Persist the zone window mode (direct / timeout variants)."""
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
        """Write a shallow merge into config entry data."""
        entry = self._coordinator.config_entry
        self._hass.config_entries.async_update_entry(
            entry, data={**entry.data, **patch}
        )

    @callback
    def reload_subscriptions(self) -> None:
        """Synchronize state listeners with the persisted sensor selections."""
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
        """Subscribe and run the one-shot post-start evaluation."""
        self.reload_subscriptions()
        for zone_id in {int(zid) for zid in self._sensor_map()}:
            await self._async_evaluate_zone_startup(zone_id)

    async def _async_evaluate_zone_startup(self, zone_id: int) -> None:
        """Apply an already-open window once. Closed windows wait for a transition."""
        entity_id = self._sensor_map().get(str(zone_id))
        if not entity_id:
            return
        state = self._hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return
        if state.state not in _OPEN_STATES:
            return

        mode = self.get_zone_window_mode(zone_id)
        await self._async_turn_off(zone_id)
        if mode == WINDOW_MODE_TIMEOUT:
            self._start_timer(zone_id)

    def shutdown(self) -> None:
        """Release listeners and timers (unload / HA stop)."""
        for unsub in self._subs.values():
            unsub()
        self._subs.clear()
        self._zones_by_sensor.clear()
        self._off_active.clear()
        for zone_id in list(self._timers):
            self._cancel_timer(zone_id)

    async def _async_on_sensor_event(self, event: Event) -> None:
        """Dispatch a single sensor state transition to linked zones."""
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
            await self._async_turn_off(zone_id)
            if mode == WINDOW_MODE_TIMEOUT:
                self._start_timer(zone_id)
            return

        self._cancel_timer(zone_id)
        if zone_id not in self._off_active:
            return
        await self._async_resume(zone_id)

    def _start_timer(self, zone_id: int) -> bool:
        """Arm (replacing any stale one) the single per-zone timeout timer.

        Returns True if the timer was armed, False if OWD is disabled.
        """
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
        """Build the self-heal action for an expired window timer."""

        async def _expire(_now: object) -> None:
            self._timers.pop(zone_id, None)
            if zone_id not in self._off_active:
                return
            _LOGGER.warning(
                "Window timer expired for zone %s with the sensor still"
                " open; resuming heating (self-heal)",
                zone_id,
            )
            await self._async_resume(zone_id)

        return _expire

    @callback
    def _cancel_timer(self, zone_id: int) -> None:
        """Drop the zone's pending timer (flapping inside the window)."""
        if unsub := self._timers.pop(zone_id, None):
            unsub()

    async def _async_turn_off(self, zone_id: int) -> None:
        """Send the window-off overlay through the command queue."""
        _LOGGER.info("Window open: setting zone %s off", zone_id)
        self._off_active.add(zone_id)
        # Timeout mode expires into a resume. direct stays off until close.
        owd_s = self._coordinator.get_open_window_timeout_seconds(zone_id)
        mode = self.get_zone_window_mode(zone_id)
        armed = mode == WINDOW_MODE_TIMEOUT and owd_s > 0
        await self._coordinator.async_set_zone_off(
            zone_id, owd_timeout_s=owd_s if armed else None
        )

    async def _async_resume(self, zone_id: int) -> None:
        """Resume the zone schedule through the command queue."""
        _LOGGER.info("Window closed: resuming zone %s", zone_id)
        self._off_active.discard(zone_id)
        await self._coordinator.async_set_zone_auto(zone_id)
