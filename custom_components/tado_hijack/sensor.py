"""Sensor platform for Tado Hijack."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant

from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ZONE_TYPE_AIR_CONDITIONING,
    ZONE_TYPE_HEATING,
    ZONE_TYPE_HOT_WATER,
)
from .entity import TadoHomeEntity, TadoZoneEntity
from .helpers.discovery import yield_zones
from .helpers.logging_utils import get_redacted_logger
from .helpers.parsers import parse_heating_power

if TYPE_CHECKING:
    from . import TadoConfigEntry
    from .coordinator import TadoDataUpdateCoordinator

_LOGGER = get_redacted_logger(__name__)


@dataclass(frozen=True, kw_only=True)
class TadoSensorEntityDescription(SensorEntityDescription):
    """Describes Tado sensor entity."""

    value_fn: Callable[[Any], Any]


SENSORS: tuple[TadoSensorEntityDescription, ...] = (
    TadoSensorEntityDescription(
        key="api_limit",
        translation_key="api_limit",
        native_unit_of_measurement=None,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda data: int(data.rate_limit.limit),
    ),
    TadoSensorEntityDescription(
        key="api_remaining",
        translation_key="api_remaining",
        native_unit_of_measurement=None,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda data: int(data.rate_limit.remaining),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TadoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tado sensors based on a config entry."""
    coordinator: TadoDataUpdateCoordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        TadoRateLimitSensor(coordinator, description) for description in SENSORS
    ]
    entities.append(TadoApiStatusSensor(coordinator))

    # Per-Zone Sensors
    for zone in yield_zones(
        coordinator, {ZONE_TYPE_HEATING, ZONE_TYPE_AIR_CONDITIONING}
    ):
        if zone.type == ZONE_TYPE_HEATING:
            entities.append(TadoHeatingPowerSensor(coordinator, zone.id, zone.name))

        entities.append(TadoHumiditySensor(coordinator, zone.id, zone.name))

    async_add_entities(entities)


class TadoRateLimitSensor(TadoHomeEntity, SensorEntity):
    """Sensor for Tado API Rate Limit."""

    entity_description: TadoSensorEntityDescription

    def __init__(
        self,
        coordinator: Any,
        description: TadoSensorEntityDescription,
    ) -> None:
        """Initialize Tado sensor."""
        if description.translation_key is None:
            raise ValueError("Sensor description must have a translation_key")
        super().__init__(coordinator, description.translation_key)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"
        self._set_entity_id("sensor", description.key)

    @property
    def native_value(self) -> int:
        """Return native value."""
        try:
            return int(self.entity_description.value_fn(self.coordinator.data))
        except (TypeError, ValueError, AttributeError):
            return 0


class TadoApiStatusSensor(TadoHomeEntity, SensorEntity):
    """Sensor for Tado API connection status."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["connected", "throttled", "rate_limited"]

    def __init__(self, coordinator: Any) -> None:
        """Initialize Tado API status sensor."""
        super().__init__(coordinator, "api_status")
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_api_status"
        self._set_entity_id("sensor", "api_status")

    @property
    def native_value(self) -> str:
        """Return the current API status."""
        return str(self.coordinator.data.api_status)


class TadoHeatingPowerSensor(TadoZoneEntity, SensorEntity):
    """Sensor for Tado heating power (valve opening)."""

    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: Any, zone_id: int, zone_name: str) -> None:
        """Initialize heating power sensor."""
        zone = coordinator.zones_meta.get(zone_id)
        trans_key = (
            "hot_water_power" if zone and zone.type == "HOT_WATER" else "heating_power"
        )
        super().__init__(coordinator, trans_key, zone_id, zone_name)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_pwr_{zone_id}"

    @property
    def native_value(self) -> float | None:
        """Return the current heating or hot water power."""
        zone = self.coordinator.zones_meta.get(self._zone_id)
        zone_type = getattr(zone, "type", None)

        # 1. For Hot Water, check optimistic power first
        if zone_type == ZONE_TYPE_HOT_WATER:
            power = self.coordinator.optimistic.get_zone_power(self._zone_id)
            if power is not None:
                return 100.0 if power == "ON" else 0.0

        # 2. Fallback to actual state
        state = self.coordinator.data.zone_states.get(str(self._zone_id))
        return parse_heating_power(state, zone_type)


class TadoHumiditySensor(TadoZoneEntity, SensorEntity):
    """Sensor for Tado zone humidity.

    Why zone-level humidity when HomeKit has per-device humidity?
    HomeKit humidity updates are extremely slow (local polling). This sensor
    uses the Tado Cloud API which updates much faster and comes for free with
    the regular state poll - no extra API calls needed.
    """

    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: Any, zone_id: int, zone_name: str) -> None:
        """Initialize humidity sensor."""
        super().__init__(coordinator, "humidity", zone_id, zone_name)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_hum_{zone_id}"

    @property
    def native_value(self) -> float | None:
        """Return the current humidity percentage."""
        state = self.coordinator.data.zone_states.get(str(self._zone_id))
        if state and state.sensor_data_points and state.sensor_data_points.humidity:
            return float(state.sensor_data_points.humidity.percentage)
        return None
