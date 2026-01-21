"""Switch platform for Tado Hijack."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import PROTECTION_MODE_TEMP
from .entity import TadoDeviceEntity, TadoHomeEntity, TadoZoneEntity
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
    """Set up Tado switches based on a config entry."""
    coordinator: TadoDataUpdateCoordinator = entry.runtime_data
    entities: list[SwitchEntity] = [TadoAwaySwitch(coordinator)]

    # Per-Zone Schedule Switches -> Zone Devices
    entities.extend(
        TadoZoneScheduleSwitch(coordinator, zone.id, zone.name)
        for zone in coordinator.zones_meta.values()
        if zone.type in ("HEATING", "AIR_CONDITIONING", "HOT_WATER")
    )

    # Hot Water Switches -> Zone Devices
    entities.extend(
        TadoHotWaterSwitch(coordinator, zone.id, zone.name)
        for zone in coordinator.zones_meta.values()
        if zone.type == "HOT_WATER"
    )

    # Dazzle Mode Switches -> Zone Devices (Tado dazzle is per zone)
    entities.extend(
        TadoDazzleModeSwitch(coordinator, zone.id, zone.name)
        for zone in coordinator.zones_meta.values()
        if getattr(zone, "supports_dazzle", False)
    )

    # Child Lock Switches -> Device Entities
    for zone in coordinator.zones_meta.values():
        if zone.type != "HEATING":
            continue
        entities.extend(
            TadoChildLockSwitch(coordinator, device, zone.id)
            for device in zone.devices
            if getattr(device, "child_lock_enabled", None) is not None
        )

    async_add_entities(entities)


class TadoAwaySwitch(TadoHomeEntity, SwitchEntity):
    """Switch for Tado Home/Away control."""

    def __init__(self, coordinator: Any) -> None:
        """Initialize Tado away switch."""
        super().__init__(coordinator, "away_mode")
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_away_mode"

    @property
    def is_on(self) -> bool:
        """Return true if in AWAY mode with optimistic fallback."""
        if (optimistic := self.tado_coordinator.optimistic.get_presence()) is not None:
            return optimistic == "AWAY"

        home_state = self.tado_coordinator.data.get("home_state")
        if home_state is None:
            return False
        return str(getattr(home_state, "presence", "")) == "AWAY"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn AWAY mode ON."""
        await self.tado_coordinator.async_set_presence_debounced("AWAY")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn AWAY mode OFF (Go HOME)."""
        await self.tado_coordinator.async_set_presence_debounced("HOME")


class TadoZoneScheduleSwitch(TadoZoneEntity, SwitchEntity):
    """Switch to toggle between Smart Schedule and Manual Overlay."""

    def __init__(self, coordinator: Any, zone_id: int, zone_name: str) -> None:
        """Initialize Tado zone schedule switch."""
        super().__init__(coordinator, "schedule", zone_id, zone_name)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_sch_{zone_id}"

    @property
    def is_on(self) -> bool:
        """Return true if Smart Schedule is active."""
        if (
            optimistic_overlay := self.tado_coordinator.optimistic.get_zone_overlay(
                self._zone_id
            )
        ) is not None:
            # overlay=True means manual mode -> Schedule=False. So we return NOT overlay.
            return not optimistic_overlay

        state = self.tado_coordinator.data.get("zone_states", {}).get(
            str(self._zone_id)
        )
        return not bool(getattr(state, "overlay_active", False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Resume smart schedule."""
        await self.tado_coordinator.async_set_zone_auto(self._zone_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Force manual overlay (Protection mode)."""
        await self.tado_coordinator.async_set_zone_heat(
            self._zone_id, temp=PROTECTION_MODE_TEMP
        )


class TadoChildLockSwitch(TadoDeviceEntity, SwitchEntity):
    """Switch for Tado Child Lock."""

    def __init__(self, coordinator: Any, device: Any, zone_id: int) -> None:
        """Initialize Tado child lock switch."""
        super().__init__(
            coordinator,
            "child_lock",
            device.serial_no,
            device.short_serial_no,
            device.device_type,
            zone_id,
            device.current_fw_version,
        )
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_childlock_{device.serial_no}"
        )

    @property
    def is_on(self) -> bool:
        """Return true if child lock is enabled."""
        if (
            optimistic := self.tado_coordinator.optimistic.get_child_lock(
                self._serial_no
            )
        ) is not None:
            return optimistic

        device = self.tado_coordinator.devices_meta.get(self._serial_no)
        # Assuming devices_meta is refreshed with new child lock status
        # Note: devices_meta comes from SLOW POLL (get_devices).
        # Child lock change might not be reflected immediately unless we trigger slow poll or update device manually?
        # But set_child_lock doesn't return new state. Optimistic UI handles the gap.
        return bool(getattr(device, "child_lock_enabled", False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable child lock."""
        await self.tado_coordinator.async_set_child_lock(self._serial_no, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable child lock."""
        await self.tado_coordinator.async_set_child_lock(self._serial_no, False)


class TadoHotWaterSwitch(TadoZoneEntity, SwitchEntity):
    """Switch for Tado Hot Water power control."""

    def __init__(self, coordinator: Any, zone_id: int, zone_name: str) -> None:
        """Initialize hot water switch."""
        super().__init__(coordinator, "hot_water", zone_id, zone_name)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_hw_{zone_id}"

    @property
    def is_on(self) -> bool:
        """Return true if hot water is ON."""
        if (
            optimistic_overlay := self.tado_coordinator.optimistic.get_zone_overlay(
                self._zone_id
            )
        ) is not None:
            return not optimistic_overlay

        state = self.tado_coordinator.data.get("zone_states", {}).get(
            str(self._zone_id)
        )
        return False if state is None else getattr(state, "power", "OFF") == "ON"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn hot water ON."""
        await self.tado_coordinator.async_set_hot_water_power(self._zone_id, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn hot water OFF."""
        await self.tado_coordinator.async_set_hot_water_power(self._zone_id, False)


class TadoDazzleModeSwitch(TadoZoneEntity, SwitchEntity):
    """Switch for Tado Dazzle Mode control."""

    def __init__(self, coordinator: Any, zone_id: int, zone_name: str) -> None:
        """Initialize dazzle mode switch."""
        super().__init__(coordinator, "dazzle_mode", zone_id, zone_name)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_dazzle_{zone_id}"

    @property
    def is_on(self) -> bool:
        """Return true if dazzle mode is enabled."""
        if (
            optimistic := self.tado_coordinator.optimistic.get_dazzle(self._zone_id)
        ) is not None:
            return optimistic

        # Dazzle mode info is in self.zones_meta (SLOW POLL)
        zone = self.tado_coordinator.zones_meta.get(self._zone_id)
        return bool(getattr(zone, "dazzle_enabled", False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable dazzle mode."""
        await self.tado_coordinator.async_set_dazzle_mode(self._zone_id, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable dazzle mode."""
        await self.tado_coordinator.async_set_dazzle_mode(self._zone_id, False)
