"""Switch platform for Tado Hijack."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    PROTECTION_MODE_TEMP,
    ZONE_TYPE_AIR_CONDITIONING,
    ZONE_TYPE_HEATING,
)
from .entity import (
    TadoDeviceEntity,
    TadoHomeEntity,
    TadoOptimisticMixin,
    TadoZoneEntity,
)
from .helpers.discovery import yield_devices, yield_zones
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
    entities: list[SwitchEntity] = [
        TadoAwaySwitch(coordinator),
        TadoPollingSwitch(coordinator),
        TadoReducedPollingLogicSwitch(coordinator),
    ]

    # Zone Level Switches
    for zone in yield_zones(
        coordinator, {ZONE_TYPE_HEATING, ZONE_TYPE_AIR_CONDITIONING}
    ):
        if zone.type == ZONE_TYPE_HEATING:
            entities.append(TadoZoneScheduleSwitch(coordinator, zone.id, zone.name))

        if getattr(zone, "supports_dazzle", False):
            entities.append(TadoDazzleModeSwitch(coordinator, zone.id, zone.name))

        if zone.type == ZONE_TYPE_HEATING:
            entities.append(TadoEarlyStartSwitch(coordinator, zone.id, zone.name))

        if (owd := getattr(zone, "open_window_detection", None)) and owd.supported:
            entities.append(TadoOpenWindowSwitch(coordinator, zone.id, zone.name))

    # Device Level Switches (Child Lock)
    entities.extend(
        TadoChildLockSwitch(coordinator, device, zone_id)
        for device, zone_id in yield_devices(coordinator, {ZONE_TYPE_HEATING})
        if getattr(device, "child_lock_enabled", None) is not None
    )
    async_add_entities(entities)


class TadoOptimisticSwitch(TadoOptimisticMixin, SwitchEntity):
    """Base class for optimistic switches."""

    @property
    def is_on(self) -> bool:
        """Return true if entity is on."""
        return bool(self._resolve_state())


class TadoAwaySwitch(TadoHomeEntity, TadoOptimisticSwitch):
    """Switch for Tado Home/Away control."""

    _attr_optimistic_key = "presence"
    _attr_optimistic_scope = "home"

    def __init__(self, coordinator: Any) -> None:
        """Initialize Tado away switch."""

        super().__init__(coordinator, "away_mode")

        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_away_mode"
        self._set_entity_id("switch", "away_mode")

    def _get_optimistic_value(self) -> bool | None:
        if (opt := cast("str | None", super()._get_optimistic_value())) is not None:
            return opt == "AWAY"
        return None

    def _get_actual_value(self) -> bool:
        home_state = self.tado_coordinator.data.home_state

        if home_state is None:
            return False

        return str(getattr(home_state, "presence", "")) == "AWAY"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn AWAY mode ON."""

        await self.tado_coordinator.async_set_presence_debounced("AWAY")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn AWAY mode OFF (Go HOME). Surrenders presence lock."""

        await self.tado_coordinator.async_set_presence_debounced("HOME")


class TadoZoneScheduleSwitch(TadoZoneEntity, TadoOptimisticSwitch):
    """Switch to toggle between Smart Schedule and Manual Overlay."""

    _attr_optimistic_key = "overlay"
    _attr_optimistic_scope = "zone"

    def __init__(self, coordinator: Any, zone_id: int, zone_name: str) -> None:
        """Initialize Tado zone schedule switch."""

        super().__init__(coordinator, "schedule", zone_id, zone_name)

        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_sch_{zone_id}"

    def _get_optimistic_value(self) -> bool | None:
        if (opt := cast("bool | None", super()._get_optimistic_value())) is not None:
            return not opt
        return None

    def _get_actual_value(self) -> bool:
        state = self.tado_coordinator.data.zone_states.get(str(self._zone_id))
        if state is None:
            return False

        return not bool(getattr(state, "overlay_active", False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Resume smart schedule."""

        await self.tado_coordinator.async_set_zone_auto(self._zone_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Force manual overlay (Protection mode)."""

        await self.tado_coordinator.async_set_zone_heat(
            self._zone_id, temp=PROTECTION_MODE_TEMP
        )


class TadoReducedPollingLogicSwitch(TadoHomeEntity, SwitchEntity):
    """Switch to enable/disable the reduced polling timeframe logic."""

    def __init__(self, coordinator: Any) -> None:
        """Initialize logic switch."""
        super().__init__(coordinator, "reduced_polling_logic")
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_reduced_polling_logic"
        )
        self._set_entity_id("switch", "reduced_polling_logic")
        self._attr_icon = "mdi:clock-check-outline"

    @property
    def is_on(self) -> bool:
        """Return true if reduced polling logic is enabled."""
        return self.tado_coordinator.is_reduced_polling_logic_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable reduced polling logic."""
        await self.tado_coordinator.async_set_reduced_polling_logic(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable reduced polling logic."""
        await self.tado_coordinator.async_set_reduced_polling_logic(False)


class TadoPollingSwitch(TadoHomeEntity, SwitchEntity):
    """Switch to globally enable/disable periodic polling."""

    def __init__(self, coordinator: Any) -> None:
        """Initialize polling switch."""
        super().__init__(coordinator, "polling_active")
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_polling_active"
        self._set_entity_id("switch", "polling_active")
        self._attr_icon = "mdi:sync"

    @property
    def is_on(self) -> bool:
        """Return true if polling is enabled."""
        return self.tado_coordinator.is_polling_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable polling."""
        await self.tado_coordinator.async_set_polling_active(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable polling."""
        await self.tado_coordinator.async_set_polling_active(False)


class TadoChildLockSwitch(TadoDeviceEntity, TadoOptimisticSwitch):
    """Switch for Tado Child Lock."""

    _attr_optimistic_key = "child_lock"
    _attr_optimistic_scope = "device"

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

    def _get_actual_value(self) -> bool:
        device = self.tado_coordinator.devices_meta.get(self._serial_no)

        return bool(getattr(device, "child_lock_enabled", False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable child lock."""

        await self.tado_coordinator.async_set_child_lock(self._serial_no, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable child lock."""

        await self.tado_coordinator.async_set_child_lock(self._serial_no, False)


class TadoDazzleModeSwitch(TadoZoneEntity, TadoOptimisticSwitch):
    """Switch for Tado Dazzle Mode control."""

    _attr_optimistic_key = "dazzle"
    _attr_optimistic_scope = "zone"

    def __init__(self, coordinator: Any, zone_id: int, zone_name: str) -> None:
        """Initialize dazzle mode switch."""

        super().__init__(coordinator, "dazzle_mode", zone_id, zone_name)

        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_dazzle_{zone_id}"

    def _get_actual_value(self) -> bool:
        zone = self.tado_coordinator.zones_meta.get(self._zone_id)

        return bool(getattr(zone, "dazzle_enabled", False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable dazzle mode."""

        await self.tado_coordinator.async_set_dazzle_mode(self._zone_id, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable dazzle mode."""

        await self.tado_coordinator.async_set_dazzle_mode(self._zone_id, False)


class TadoEarlyStartSwitch(TadoZoneEntity, TadoOptimisticSwitch):
    """Switch for Tado Early Start control."""

    _attr_optimistic_key = "early_start"
    _attr_optimistic_scope = "zone"

    def __init__(self, coordinator: Any, zone_id: int, zone_name: str) -> None:
        """Initialize early start switch."""

        super().__init__(coordinator, "early_start", zone_id, zone_name)

        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_early_{zone_id}"

    def _get_actual_value(self) -> bool:
        zone = self.tado_coordinator.zones_meta.get(self._zone_id)

        return bool(getattr(zone, "early_start_enabled", False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable early start."""

        await self.tado_coordinator.async_set_early_start(self._zone_id, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable early start."""

        await self.tado_coordinator.async_set_early_start(self._zone_id, False)


class TadoOpenWindowSwitch(TadoZoneEntity, TadoOptimisticSwitch):
    """Switch for Tado Open Window Detection control."""

    _attr_optimistic_key = "open_window"
    _attr_optimistic_scope = "zone"

    def __init__(self, coordinator: Any, zone_id: int, zone_name: str) -> None:
        """Initialize open window detection switch."""

        super().__init__(coordinator, "open_window", zone_id, zone_name)

        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_owd_{zone_id}"

    def _get_actual_value(self) -> bool:
        """Return actual value from coordinator."""
        zone = self.tado_coordinator.zones_meta.get(self._zone_id)
        return bool(
            zone
            and (owd := getattr(zone, "open_window_detection", None))
            and owd.enabled
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable open window detection."""

        await self.tado_coordinator.async_set_open_window_detection(self._zone_id, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable open window detection."""

        await self.tado_coordinator.async_set_open_window_detection(
            self._zone_id, False
        )
