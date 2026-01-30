"""Select platform for Tado Hijack."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import TadoZoneEntity
from .helpers.logging_utils import get_redacted_logger
from .helpers.parsers import get_ac_capabilities

if TYPE_CHECKING:
    from . import TadoConfigEntry
    from .coordinator import TadoDataUpdateCoordinator

_LOGGER = get_redacted_logger(__name__)


async def async_setup_entry(
    hass: Any,
    entry: TadoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tado select entities based on a config entry."""
    coordinator: TadoDataUpdateCoordinator = entry.runtime_data
    entities: list[SelectEntity] = []

    for zone in coordinator.zones_meta.values():
        if zone.type != "AIR_CONDITIONING":
            continue

        entities.extend(
            (
                TadoAcSelect(coordinator, zone.id, zone.name, "fan_speed"),
                TadoAcSelect(coordinator, zone.id, zone.name, "vertical_swing"),
                TadoAcSelect(coordinator, zone.id, zone.name, "horizontal_swing"),
            )
        )
    if entities:
        async_add_entities(entities)


class TadoAcSelect(TadoZoneEntity, SelectEntity):
    """Representation of a Tado AC setting select."""

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        zone_id: int,
        zone_name: str,
        key: str,
    ) -> None:
        """Initialize the AC select entity."""
        super().__init__(coordinator, key, zone_id, zone_name)
        self._attr_options: list[str] = []  # Start empty
        self._option_map: dict[str, str] = {}
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}_{zone_id}"
        self._key = key

    async def async_added_to_hass(self) -> None:
        """Fetch options on startup if not cached."""
        await super().async_added_to_hass()
        if capabilities := await self.tado_coordinator.async_get_capabilities(
            self._zone_id
        ):
            options = get_ac_capabilities(capabilities)
            if source_options := options.get(f"{self._key}s") or options.get(self._key):
                self._option_map = {opt.lower(): opt for opt in source_options}
                self._attr_options = sorted(self._option_map.keys())
                self.async_write_ha_state()

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        # 1. Check Optimistic Value (High Priority)
        opt = self.tado_coordinator.optimistic
        val = None
        if self._key == "fan_speed":
            # Note: We currently don't have optimistic fan_speed, but we can add it here if needed
            pass
        elif self._key == "vertical_swing":
            val = opt.get_vertical_swing(self._zone_id)
        elif self._key == "horizontal_swing":
            val = opt.get_horizontal_swing(self._zone_id)

        # 2. Fallback to API State
        if val is None:
            state = self.tado_coordinator.data.zone_states.get(str(self._zone_id))
            if state and state.setting:
                val = getattr(state.setting, self._key, None)

        if val is not None:
            val_lower = str(val).lower()
            if val_lower in self._attr_options:
                return val_lower
        return None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        # Map back to API value
        api_value = self._option_map.get(option)
        if api_value is None:
            _LOGGER.error("Invalid option selected: %s", option)
            return

        await self.tado_coordinator.async_set_ac_setting(
            self._zone_id, self._key, api_value
        )
        self.async_write_ha_state()
