"""Select platform for Tado Hijack."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final, cast

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ZONE_HUMIDITY_ENTITIES,
    CONF_ZONE_TEMP_ENTITIES,
    CONF_ZONE_WINDOW_ENTITIES,
    WINDOW_MODE_OPTIONS,
    WINDOW_SENSOR_NONE,
)
from .entity import TadoGenericEntityMixin, TadoHomeEntity, TadoZoneEntity
from .helpers.discovery import yield_zones
from .helpers.entity_setup import async_setup_generic_platform
from .helpers.logging_utils import get_redacted_logger
from .models import TadoEntityDefinition

if TYPE_CHECKING:
    from . import TadoConfigEntry
    from .coordinator import TadoDataUpdateCoordinator

_LOGGER = get_redacted_logger(__name__)

# No linked sensor. Translated via select state "device" (Device / Gerät).
_SOURCE_NONE: Final = "device"
_LEGACY_SOURCE_SENTINELS: Final = frozenset(
    {"automatic", "auto", "device", "gerät", "gerat"}
)


def migrate_legacy_source_sentinels(hass: Any, entry: TadoConfigEntry) -> None:
    """Drop stored Automatic/Device sentinels. Those mean 'use the device'."""
    data = dict(entry.data)
    changed = False
    for key in (CONF_ZONE_TEMP_ENTITIES, CONF_ZONE_HUMIDITY_ENTITIES):
        raw = data.get(key)
        if not isinstance(raw, dict):
            continue
        cleaned = {
            zone_id: entity_id
            for zone_id, entity_id in raw.items()
            if str(entity_id).strip().lower() not in _LEGACY_SOURCE_SENTINELS
        }
        if cleaned != raw:
            data[key] = cleaned
            changed = True
    if changed:
        hass.config_entries.async_update_entry(entry, data=data)


async def async_setup_entry(
    hass: Any,
    entry: TadoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tado select entities based on a config entry."""
    await async_setup_generic_platform(
        hass,
        entry,
        async_add_entities,
        "select",
        {
            "home": TadoGenericHomeSelect,
            "zone": TadoGenericZoneSelect,
        },
    )

    # Setup source selects for all generations.
    coordinator: TadoDataUpdateCoordinator = entry.runtime_data
    source_entities: list[Any] = []
    for zone in yield_zones(coordinator):
        source_entities.extend(
            (
                TadoZoneTempSourceSelect(coordinator, zone.id, zone.name),
                TadoZoneHumiditySourceSelect(coordinator, zone.id, zone.name),
                TadoZoneWindowSensorSelect(coordinator, zone.id, zone.name),
                TadoZoneWindowModeSelect(coordinator, zone.id, zone.name),
            )
        )
    if source_entities:
        async_add_entities(source_entities)


class TadoGenericHomeSelect(TadoHomeEntity, TadoGenericEntityMixin, SelectEntity):
    """Generic select for Home scope."""

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        definition: TadoEntityDefinition,
    ) -> None:
        """Initialize the generic home select."""
        TadoHomeEntity.__init__(
            self, coordinator, cast(str, definition["translation_key"])
        )
        TadoGenericEntityMixin.__init__(self, definition)
        self._set_entity_id("select", definition["key"])
        self._option_map: dict[str, str] = {}
        if options_fn := definition.get("options_fn"):
            raw_options: list[str] = options_fn(coordinator)
            self._option_map = {opt.lower(): opt for opt in raw_options}
            self._attr_options = [opt.lower() for opt in raw_options]
        else:
            self._attr_options = []

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        val = self._get_actual_value()
        if val is not None:
            val_lower = str(val).lower()
            if val_lower in self._attr_options:
                return val_lower
        return None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        api_value = self._option_map.get(option)
        if api_value is None:
            _LOGGER.error("Invalid option selected: %s", option)
            return
        await self._async_select_option(api_value)
        self.async_write_ha_state()


class TadoGenericZoneSelect(TadoZoneEntity, TadoGenericEntityMixin, SelectEntity):
    """Generic select for Zone scope."""

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        definition: TadoEntityDefinition,
        zone_id: int,
        zone_name: str,
    ) -> None:
        """Initialize the generic zone select."""
        TadoZoneEntity.__init__(
            self,
            coordinator,
            cast(str, definition["translation_key"]),
            zone_id,
            zone_name,
        )
        TadoGenericEntityMixin.__init__(self, definition)
        self._attr_options: list[str] = []
        self._option_map: dict[str, str] = {}
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{self._get_unique_id_suffix()}_{zone_id}"

    async def async_added_to_hass(self) -> None:
        """Fetch options on startup."""
        await super().async_added_to_hass()
        if options_fn := self._definition.get("options_fn"):
            # Ensure capabilities are loaded
            await self.coordinator.async_get_capabilities(self._zone_id)
            if source_options := options_fn(self.coordinator, self._zone_id):
                self._option_map = {opt.lower(): opt for opt in source_options}
                self._attr_options = sorted(self._option_map.keys())
                self.async_write_ha_state()

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        val = self._get_actual_value()
        if val is not None:
            val_lower = str(val).lower()
            if val_lower in self._attr_options:
                return val_lower
        return None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        api_value = self._option_map.get(option)
        if api_value is None:
            _LOGGER.error("Invalid option selected: %s", option)
            return

        await self._async_select_option(api_value)
        self.async_write_ha_state()


class TadoZoneSourceSelectBase(TadoZoneEntity, SelectEntity):
    """Base class for temperature/humidity source select entities."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        translation_key: str,
        zone_id: int,
        zone_name: str,
        config_key: str,
        device_class_filter: str,
        unique_id_suffix: str,
    ) -> None:
        """Initialize the source select base."""
        super().__init__(coordinator, translation_key, zone_id, zone_name)
        self._config_key = config_key
        self._device_class_filter = device_class_filter
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_zone_{zone_id}_{unique_id_suffix}"
        )

    @property
    def options(self) -> list[str]:
        """Return all selectable source entities."""
        sensors = [
            eid
            for eid in self.hass.states.async_entity_ids("sensor")
            if (s := self.hass.states.get(eid))
            and s.attributes.get("device_class") == self._device_class_filter
        ]
        climate_entities = list(self.hass.states.async_entity_ids("climate"))
        return [_SOURCE_NONE, *sorted(sensors + climate_entities)]

    @property
    def current_option(self) -> str:
        """Return the currently linked entity ID, or the sentinel if none."""
        saved = self.coordinator.config_entry.data.get(self._config_key, {}).get(
            str(self._zone_id)
        )
        if saved and self.hass.states.get(str(saved)) is not None:
            return str(saved)
        return _SOURCE_NONE

    async def async_select_option(self, option: str) -> None:
        """Persist the selected source entity to config entry data (no reload)."""
        entry = self.coordinator.config_entry
        current_map: dict[str, str] = dict(entry.data.get(self._config_key, {}))
        if option == _SOURCE_NONE:
            current_map.pop(str(self._zone_id), None)
        else:
            current_map[str(self._zone_id)] = option
        self.hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, self._config_key: current_map},
        )
        if self._config_key == CONF_ZONE_TEMP_ENTITIES:
            self.coordinator.note_offset_sources_changed()
        self.async_write_ha_state()


class TadoZoneTempSourceSelect(TadoZoneSourceSelectBase):
    """Select entity to choose the temperature source for indoor climate sensors.

    Available for all hardware generations.  When set, the chosen entity
    (temperature sensor or climate entity) overrides the built-in zone state
    temperature used for dew point, mold risk and absolute humidity calculations.

    Default (both gens): cloud zone state sensor_data_points.inside_temperature
    """

    _attr_icon = "mdi:thermometer"

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        zone_id: int,
        zone_name: str,
    ) -> None:
        """Initialize the temperature source select."""
        super().__init__(
            coordinator,
            "zone_temp_source",
            zone_id,
            zone_name,
            CONF_ZONE_TEMP_ENTITIES,
            "temperature",
            "temp_source",
        )


class TadoZoneHumiditySourceSelect(TadoZoneSourceSelectBase):
    """Select entity to choose the humidity source for indoor climate sensors.

    Available for all hardware generations.  When set, the chosen entity
    overrides the built-in zone state humidity used for dew point, mold risk,
    absolute humidity and ventilation recommendation calculations.

    Accepts humidity sensors (reads entity state) and climate entities (reads
    the current_humidity attribute, which HomeKit/Matter climate entities expose).

    Default (both gens): cloud zone state sensor_data_points.humidity
    """

    _attr_icon = "mdi:water-percent"

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        zone_id: int,
        zone_name: str,
    ) -> None:
        """Initialize the humidity source select."""
        super().__init__(
            coordinator,
            "zone_humidity_source",
            zone_id,
            zone_name,
            CONF_ZONE_HUMIDITY_ENTITIES,
            "humidity",
            "humidity_source",
        )


class TadoZoneWindowSensorSelect(TadoZoneEntity, SelectEntity):
    """Select entity to link an external contact sensor as the zone window state.

    Available for all hardware generations.  When set, the chosen
    ``binary_sensor`` drives window open/close reactions handled by the
    coordinator's ``WindowController`` (zone off / schedule resume, optionally
    delayed by the zone's open-window detection timeout).
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:window-open-variant"

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        zone_id: int,
        zone_name: str,
    ) -> None:
        """Initialize the window sensor select."""
        super().__init__(coordinator, "zone_window_sensor", zone_id, zone_name)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_zone_{zone_id}_window_sensor"
        )

    @property
    def options(self) -> list[str]:
        """Return all binary sensors plus the unlink sentinel."""
        return [
            WINDOW_SENSOR_NONE,
            *sorted(self.hass.states.async_entity_ids("binary_sensor")),
        ]

    @property
    def current_option(self) -> str:
        """Return the linked sensor entity ID, or the sentinel if none."""
        saved = self.coordinator.config_entry.data.get(
            CONF_ZONE_WINDOW_ENTITIES, {}
        ).get(str(self._zone_id))
        if saved and self.hass.states.get(str(saved)) is not None:
            return str(saved)
        return WINDOW_SENSOR_NONE

    async def async_select_option(self, option: str) -> None:
        """Link the chosen sensor and re-subscribe without reload."""
        entity_id = "" if option == WINDOW_SENSOR_NONE else option
        await self.coordinator.window_controller.async_set_zone_window_sensor(
            self._zone_id, entity_id
        )
        self.async_write_ha_state()


class TadoZoneWindowModeSelect(TadoZoneEntity, SelectEntity):
    """Select entity to configure the zone's external window reaction mode.

    Modes:
    - ``direct``: window open turns the zone off immediately, close resumes.
    - ``timeout``: like ``direct``, plus a self-healing resume — heating
      resumes after the open window detection timeout even while the
      window is still open (protection against a stuck sensor or a dead
      sensor battery); a new cycle only starts on the next close -> open
      transition.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:tune-vertical"

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        zone_id: int,
        zone_name: str,
    ) -> None:
        """Initialize the window mode select."""
        super().__init__(coordinator, "zone_window_mode", zone_id, zone_name)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_zone_{zone_id}_window_mode"
        )
        self._attr_options = list(WINDOW_MODE_OPTIONS)

    @property
    def current_option(self) -> str:
        """Return the persisted window mode (default: direct)."""
        return str(
            self.coordinator.window_controller.get_zone_window_mode(self._zone_id)
        )

    async def async_select_option(self, option: str) -> None:
        """Persist the chosen window mode without reload."""
        await self.coordinator.window_controller.async_set_zone_window_mode(
            self._zone_id, option
        )
        self.async_write_ha_state()
