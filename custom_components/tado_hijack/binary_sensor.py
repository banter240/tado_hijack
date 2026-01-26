"""Binary sensor platform for Tado Hijack (Battery, Connectivity)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import TadoDeviceEntity, TadoHomeEntity

if TYPE_CHECKING:
    from . import TadoConfigEntry
    from .coordinator import TadoDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TadoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tado binary sensors."""
    coordinator: TadoDataUpdateCoordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = []
    seen_devices: set[str] = set()

    for zone in coordinator.zones_meta.values():
        if zone.type not in ("HEATING", "AIR_CONDITIONING", "HOT_WATER"):
            continue

        for device in zone.devices:
            # Skip devices we've already processed (can appear in multiple zones)
            if device.serial_no in seen_devices:
                continue
            seen_devices.add(device.serial_no)

            entities.extend(
                (
                    TadoBatterySensor(coordinator, device, zone.id),
                    TadoConnectionSensor(coordinator, device, zone.id),
                )
            )
    # Bridge Connection Sensors
    entities.extend(
        TadoBridgeConnectionSensor(coordinator, bridge)
        for bridge in coordinator.bridges
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


class TadoConnectionSensor(TadoDeviceEntity, BinarySensorEntity):
    """Representation of a Tado device connection state."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: Any, device: Any, zone_id: int) -> None:
        """Initialize Tado connection sensor."""
        super().__init__(
            coordinator,
            "connection_state",
            device.serial_no,
            device.short_serial_no,
            device.device_type,
            zone_id,
            device.current_fw_version,
        )
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_conn_{device.serial_no}"
        )

    @property
    def is_on(self) -> bool:
        """Return true if device is connected."""
        device = self.coordinator.devices_meta.get(self._serial_no)
        if device and device.connection_state:
            return bool(device.connection_state.value)
        return False


class TadoBridgeConnectionSensor(TadoHomeEntity, BinarySensorEntity):
    """Representation of a Tado Bridge connection state."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: Any, bridge: Any) -> None:
        """Initialize Tado bridge connection sensor."""
        super().__init__(coordinator, "bridge_connection")
        self._serial_no = bridge.serial_no
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_bridge_{bridge.serial_no}"
        )
        self._set_entity_id("binary_sensor", "cloud_connection", prefix="tado_ib")

    @property
    def is_on(self) -> bool:
        """Return true if bridge is connected."""
        return next(
            (
                bool(bridge.connection_state.value)
                for bridge in self.coordinator.bridges
                if bridge.serial_no == self._serial_no and bridge.connection_state
            ),
            False,
        )
