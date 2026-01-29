"""Binary sensor platform for Tado Hijack (Battery, Connectivity)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ZONE_TYPE_AIR_CONDITIONING,
    ZONE_TYPE_HEATING,
    ZONE_TYPE_HOT_WATER,
)
from .entity import TadoDeviceEntity, TadoHomeEntity, TadoHotWaterZoneEntity
from .helpers.discovery import yield_devices, yield_zones

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

    # Device Level Sensors
    for device, zone_id in yield_devices(
        coordinator,
        {ZONE_TYPE_HEATING, ZONE_TYPE_AIR_CONDITIONING, ZONE_TYPE_HOT_WATER},
    ):
        entities.extend(
            (
                TadoBatterySensor(coordinator, device, zone_id),
                TadoConnectionSensor(coordinator, device, zone_id),
            )
        )

    # Bridge Connection Sensors
    entities.extend(
        TadoBridgeConnectionSensor(coordinator, bridge)
        for bridge in coordinator.bridges
    )

    # Hot Water Zone Sensors
    for zone in yield_zones(coordinator, {ZONE_TYPE_HOT_WATER}):
        entities.extend(
            (
                TadoHotWaterOverlaySensor(coordinator, zone.id, zone.name),
                TadoHotWaterPowerSensor(coordinator, zone.id, zone.name),
                TadoHotWaterConnectivitySensor(coordinator, zone.id, zone.name),
            )
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


class TadoHotWaterOverlaySensor(TadoHotWaterZoneEntity, BinarySensorEntity):
    """Binary sensor showing if hot water has a manual overlay active."""

    # No device class - shows On/Off states (not Plugged in/Unplugged)

    def __init__(self, coordinator: Any, zone_id: int, zone_name: str) -> None:
        """Initialize hot water overlay sensor."""
        super().__init__(coordinator, "overlay", zone_id, zone_name)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_hw_overlay_{zone_id}"
        )

    @property
    def is_on(self) -> bool:
        """Return true if manual overlay is active."""
        state = self.coordinator.data.zone_states.get(str(self._zone_id))
        if state is None:
            return False
        return bool(getattr(state, "overlay_active", False))


class TadoHotWaterPowerSensor(TadoHotWaterZoneEntity, BinarySensorEntity):
    """Binary sensor showing if hot water power is ON."""

    _attr_device_class = BinarySensorDeviceClass.POWER

    def __init__(self, coordinator: Any, zone_id: int, zone_name: str) -> None:
        """Initialize hot water power sensor."""
        super().__init__(coordinator, "power", zone_id, zone_name)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_hw_power_{zone_id}"

    @property
    def is_on(self) -> bool:
        """Return true if hot water power is ON."""
        state = self.coordinator.data.zone_states.get(str(self._zone_id))
        if state is None:
            return False
        if setting := getattr(state, "setting", None):
            return getattr(setting, "power", "OFF") == "ON"
        return False


class TadoHotWaterConnectivitySensor(TadoHotWaterZoneEntity, BinarySensorEntity):
    """Binary sensor showing hot water zone connectivity (Connected/Disconnected)."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: Any, zone_id: int, zone_name: str) -> None:
        """Initialize hot water connectivity sensor."""
        super().__init__(coordinator, "connectivity", zone_id, zone_name)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_hw_conn_{zone_id}"

    @property
    def is_on(self) -> bool:
        """Return true if hot water zone is connected.

        Checks if any device in the zone is connected.
        """
        zone = self.coordinator.zones_meta.get(self._zone_id)
        if zone is None:
            return False

        for device in zone.devices:
            device_meta = self.coordinator.devices_meta.get(device.serial_no)
            if (
                device_meta
                and device_meta.connection_state
                and device_meta.connection_state.value
            ):
                return True
        return False
