"""Track local climate entity (HomeKit / Matter) availability per TRV serial."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, callback
from homeassistant.helpers.entity_registry import EVENT_ENTITY_REGISTRY_UPDATED
from homeassistant.helpers.event import async_track_state_change_event

from .device_linker import get_climate_entity_id, invalidate_cache
from .logging_utils import get_redacted_logger
from .zone_utils import trv_serials

if TYPE_CHECKING:
    from ..coordinator import TadoDataUpdateCoordinator

_LOGGER = get_redacted_logger(__name__)

_UNAVAILABLE = {STATE_UNAVAILABLE, STATE_UNKNOWN}


class AvailabilityTracker:
    """Map TRV serials to local climate entities and track whether they are reachable.

    HomeKit and Matter entities often appear after the first Tado poll, and a
    device can already be unavailable when tracking starts. Both cases have to
    be visible or the recovery queue never records an intent.
    """

    def __init__(self, coordinator: TadoDataUpdateCoordinator) -> None:
        """Initialize tracker with coordinator reference."""
        self._coordinator = coordinator
        self._hass = coordinator.hass
        self._generation = coordinator.generation
        self._entity_by_serial: dict[str, str] = {}
        self._serial_by_entity: dict[str, str] = {}
        self._available: dict[str, bool] = {}
        self._on_available_callbacks: list[Callable[[str], None]] = []
        self._unsub: Callable[[], None] | None = None
        self._registry_unsub: Callable[[], None] | None = None

    async def async_start(self) -> None:
        """Map current entities and watch the registry for ones that show up later."""
        if self._registry_unsub is None:
            self._registry_unsub = self._hass.bus.async_listen(
                EVENT_ENTITY_REGISTRY_UPDATED, self._on_registry_update
            )
        self.refresh()

    def refresh(self, *, invalidate: bool = False) -> None:
        """Rebuild the serial map. Safe to call on later polls."""
        serials = trv_serials(self._coordinator.zones_meta)
        if invalidate or any(
            serial not in self._entity_by_serial for serial in serials
        ):
            invalidate_cache()

        desired: dict[str, str] = {}
        for serial in serials:
            if entity_id := get_climate_entity_id(self._hass, serial, self._generation):
                desired[serial] = entity_id

        if desired == self._entity_by_serial:
            return

        for serial in set(self._entity_by_serial) - set(desired):
            self._available.pop(serial, None)

        for serial, entity_id in desired.items():
            if self._entity_by_serial.get(serial) != entity_id:
                self._available[serial] = self._entity_is_available(entity_id)
                _LOGGER.debug("Mapped serial=%s to entity=%s", serial, entity_id)

        self._entity_by_serial = desired
        self._serial_by_entity = {eid: serial for serial, eid in desired.items()}
        self._resubscribe()
        if desired:
            _LOGGER.info(
                "AvailabilityTracker tracking %d local climate entities", len(desired)
            )

    @callback
    def _on_registry_update(self, event: Event) -> None:
        """Pick up climate entities created after startup."""
        entity_id = str(event.data.get("entity_id") or "")
        old_entity_id = str(event.data.get("old_entity_id") or "")
        if entity_id.startswith("climate.") or old_entity_id.startswith("climate."):
            self.refresh(invalidate=True)

    def _entity_is_available(self, entity_id: str) -> bool:
        """False when the entity is missing or not currently reporting a state."""
        state = self._hass.states.get(entity_id)
        return False if state is None else state.state not in _UNAVAILABLE

    def _resubscribe(self) -> None:
        """Point the state listener at the current entity set."""
        if self._unsub:
            self._unsub()
            self._unsub = None
        if not self._entity_by_serial:
            return
        self._unsub = async_track_state_change_event(
            self._hass,
            list(self._entity_by_serial.values()),
            self._async_on_state_change,
        )

    @callback
    def _async_on_state_change(self, event: Event) -> None:
        """Handle state change of a tracked climate entity."""
        entity_id = event.data.get("entity_id")
        if not entity_id or entity_id not in self._serial_by_entity:
            return

        serial = self._serial_by_entity[entity_id]
        new_state = event.data.get("new_state")
        if not new_state:
            return

        is_available = new_state.state not in _UNAVAILABLE
        was_available = self._available.get(serial, False)
        if is_available == was_available:
            return

        self._available[serial] = is_available
        _LOGGER.debug(
            "Serial=%s availability changed: %s -> %s",
            serial,
            was_available,
            is_available,
        )
        if is_available:
            self._fire_on_available(serial)

    def _fire_on_available(self, serial: str) -> None:
        """Fire all registered callbacks for a recovered serial."""
        for cb in self._on_available_callbacks:
            try:
                cb(serial)
            except Exception:
                _LOGGER.exception("Recovery callback failed for serial=%s", serial)

    def is_available(self, serial: str) -> bool:
        """True when no local entity is mapped, or the mapped one is reachable.

        Unmapped serials fail open: there is no local device to replay onto.
        """
        if serial not in self._entity_by_serial:
            return True
        return self._available.get(serial, False)

    def get_available_serials(self) -> set[str]:
        """Return all serials whose local entities are currently available."""
        return {serial for serial, available in self._available.items() if available}

    def get_entity_id(self, serial: str) -> str | None:
        """Get the local climate entity ID for a serial, or None."""
        return self._entity_by_serial.get(serial)

    def register_on_available(self, callback: Callable[[str], None]) -> None:
        """Register a callback fired when a tracked device becomes reachable."""
        if callback not in self._on_available_callbacks:
            self._on_available_callbacks.append(callback)

    def unregister_on_available(self, callback: Callable[[str], None]) -> None:
        """Unregister a recovery callback."""
        if callback in self._on_available_callbacks:
            self._on_available_callbacks.remove(callback)

    def shutdown(self) -> None:
        """Stop tracking and cleanup subscriptions."""
        if self._unsub:
            self._unsub()
            self._unsub = None
        if self._registry_unsub:
            self._registry_unsub()
            self._registry_unsub = None
        self._on_available_callbacks.clear()
        self._entity_by_serial.clear()
        self._serial_by_entity.clear()
        self._available.clear()
