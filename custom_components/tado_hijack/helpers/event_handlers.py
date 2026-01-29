"""Event handlers for Tado Hijack."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.climate import (
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    EVENT_CALL_SERVICE,
)
from homeassistant.core import CALLBACK_TYPE, Event, callback

if TYPE_CHECKING:
    from ..coordinator import TadoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


class TadoEventHandler:
    """Handles Home Assistant bus events for Tado Hijack."""

    def __init__(self, coordinator: TadoDataUpdateCoordinator) -> None:
        """Initialize the event handler."""
        self.coordinator = coordinator
        self.hass = coordinator.hass
        self._unsub_listener: CALLBACK_TYPE | None = None

    def setup(self) -> None:
        """Listen for climate service calls to trigger optimistic updates."""

        @callback
        def _handle_service_call(event: Event) -> None:
            data = event.data
            domain = data.get("domain")
            service = data.get("service")

            if domain != "climate" or service not in (
                SERVICE_SET_TEMPERATURE,
                SERVICE_SET_HVAC_MODE,
            ):
                return

            service_data = data.get("service_data", {})
            entity_ids = service_data.get(ATTR_ENTITY_ID)

            if not entity_ids:
                return

            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]

            hvac_mode = service_data.get("hvac_mode")
            is_auto_mode = hvac_mode == "auto"

            for eid in entity_ids:
                if (zone_id := self.coordinator._climate_to_zone.get(eid)) is not None:
                    if is_auto_mode:
                        _LOGGER.debug(
                            "Intercepted AUTO mode on HomeKit climate %s. Resuming schedule for zone %d.",
                            eid,
                            zone_id,
                        )
                        self.hass.async_create_task(
                            self.coordinator.async_set_zone_auto(zone_id)
                        )
                    else:
                        _LOGGER.debug(
                            "Intercepted climate change on %s. Setting optimistic MANUAL for zone %d.",
                            eid,
                            zone_id,
                        )
                        self.coordinator.optimistic.apply_zone_state(
                            zone_id, overlay=True
                        )
                        self.coordinator.async_update_listeners()

        self._unsub_listener = self.hass.bus.async_listen(
            EVENT_CALL_SERVICE, _handle_service_call
        )

    def shutdown(self) -> None:
        """Stop listening for events."""
        if self._unsub_listener:
            self._unsub_listener()
            self._unsub_listener = None
