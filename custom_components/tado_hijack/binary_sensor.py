"""Binary sensor platform for Tado Hijack (Battery)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import TadoDeviceEntity

if TYPE_CHECKING:
    from . import TadoConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TadoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tado battery sensors."""
    coordinator = entry.runtime_data
    entities: list[TadoBatterySensor] = []

    for zone in coordinator.zones_meta.values():
        if zone.type != "HEATING":
            continue

        entities.extend(
            TadoBatterySensor(
                coordinator,
                device,
                zone.id,
            )
            for device in zone.devices
        )
    async_add_entities(entities)


class TadoBatterySensor(TadoDeviceEntity, BinarySensorEntity):
    """Representation of a Tado device battery state."""

    _attr_device_class = BinarySensorDeviceClass.BATTERY

    def __init__(self, coordinator: Any, device: Any, zone_id: int) -> None:
        """Initialize Tado battery sensor."""
        super().__init__(
            coordinator,
            "battery_state",
            device.serial_no,
            device.short_serial_no,
            device.device_type,
            zone_id,
            device.current_fw_version,
        )
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_bat_{device.serial_no}"
        )

    @property
    def is_on(self) -> bool:
        """Return true if battery is low."""
        device = self.coordinator.devices_meta.get(self._serial_no)
        return bool(device and device.battery_state == "LOW")
