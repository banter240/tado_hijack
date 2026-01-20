"""Sensor platform for Tado Hijack."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CAPABILITY_INSIDE_TEMP
from .entity import TadoDeviceEntity, TadoHomeEntity
from .helpers.logging_utils import get_redacted_logger

if TYPE_CHECKING:
    from . import TadoConfigEntry

_LOGGER = get_redacted_logger(__name__)


@dataclass(frozen=True, kw_only=True)
class TadoSensorEntityDescription(SensorEntityDescription):
    """Describes Tado sensor entity."""

    value_fn: Callable[[dict[str, Any]], int]


SENSORS: tuple[TadoSensorEntityDescription, ...] = (
    TadoSensorEntityDescription(
        key="api_limit",
        translation_key="api_limit",
        native_unit_of_measurement=None,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda data: int(getattr(data.get("rate_limit"), "limit", 0)),
    ),
    TadoSensorEntityDescription(
        key="api_remaining",
        translation_key="api_remaining",
        native_unit_of_measurement=None,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda data: int(getattr(data.get("rate_limit"), "remaining", 0)),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TadoConfigEntry,
    async_add_entities: Any,
) -> None:
    """Set up Tado sensors based on a config entry."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        TadoRateLimitSensor(coordinator, description) for description in SENSORS
    ]
    entities.append(TadoApiStatusSensor(coordinator))

    # Add offset sensors for devices with temperature measurement capability
    for zone in coordinator.zones_meta.values():
        if zone.type != "HEATING":
            continue
        entities.extend(
            TadoOffsetSensor(
                coordinator,
                device,
                zone.id,
            )
            for device in zone.devices
            if CAPABILITY_INSIDE_TEMP in (device.characteristics.capabilities or [])
        )
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

    @property
    def native_value(self) -> str:
        """Return the current API status."""
        return str(self.coordinator.data.get("api_status", "connected"))


class TadoOffsetSensor(TadoDeviceEntity, RestoreEntity, SensorEntity):
    """Sensor for Tado device temperature offset."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    def __init__(
        self,
        coordinator: Any,
        device: Any,
        zone_id: int,
    ) -> None:
        """Initialize Tado offset sensor."""
        super().__init__(
            coordinator,
            "temperature_offset",
            device.serial_no,
            device.short_serial_no,
            device.device_type,
            zone_id,
            device.current_fw_version,
        )
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_offset_{device.short_serial_no}"
        )
        self._restored_value: float | None = None

    async def async_added_to_hass(self) -> None:
        """Restore previous state on startup."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state not in (None, "unknown", "unavailable"):
                with contextlib.suppress(ValueError, TypeError):
                    self._restored_value = float(last_state.state)

    @property
    def native_value(self) -> float | None:
        """Return the temperature offset value."""
        offsets = self.coordinator.data.get("offsets", {})
        offset = offsets.get(self._serial_no)
        return float(offset.celsius) if offset is not None else self._restored_value
