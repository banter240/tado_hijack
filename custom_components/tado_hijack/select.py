"""Select platform for Tado Hijack."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import TadoZoneEntity
from .helpers.logging_utils import get_redacted_logger

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

        # Get capabilities for the zone
        # We use the first mode's capabilities as a proxy for available options
        # In a real scenario, we might need to merge capabilities from all modes
        capabilities = coordinator.data.get("capabilities", {}).get(zone.id)
        if not capabilities:
            continue

        # Find available options across all AC modes
        fan_speeds: set[str] = set()
        v_swings: set[str] = set()
        h_swings: set[str] = set()

        for mode_attr in ("auto", "cool", "dry", "fan", "heat"):
            if ac_mode := getattr(capabilities, mode_attr, None):
                if ac_mode.fan_speeds:
                    fan_speeds.update(ac_mode.fan_speeds)
                if ac_mode.vertical_swing:
                    v_swings.update(ac_mode.vertical_swing)
                if ac_mode.horizontal_swing:
                    h_swings.update(ac_mode.horizontal_swing)

        if fan_speeds:
            entities.append(
                TadoAcSelect(
                    coordinator,
                    zone.id,
                    zone.name,
                    "fan_speed",
                    sorted(fan_speeds),
                )
            )
        if v_swings:
            entities.append(
                TadoAcSelect(
                    coordinator,
                    zone.id,
                    zone.name,
                    "vertical_swing",
                    sorted(v_swings),
                )
            )
        if h_swings:
            entities.append(
                TadoAcSelect(
                    coordinator,
                    zone.id,
                    zone.name,
                    "horizontal_swing",
                    sorted(h_swings),
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
        options: list[str],
    ) -> None:
        """Initialize the AC select entity."""
        super().__init__(coordinator, key, zone_id, zone_name)
        # Store mapping from HA option (lowercase) to API option (original)
        self._option_map = {opt.lower(): opt for opt in options}
        self._attr_options = sorted(self._option_map.keys())
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}_{zone_id}"
        self._key = key

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        state = self.tado_coordinator.data.get("zone_states", {}).get(
            str(self._zone_id)
        )
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
