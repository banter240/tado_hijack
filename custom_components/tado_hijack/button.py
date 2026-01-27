"""Button platform for Tado Hijack."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import TadoHomeEntity, TadoZoneEntity
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
    """Set up Tado buttons based on a config entry."""
    coordinator: TadoDataUpdateCoordinator = entry.runtime_data
    entities: list[ButtonEntity] = [
        TadoRefreshMetadataButton(coordinator),
        TadoRefreshOffsetsButton(coordinator),
        TadoRefreshAwayConfigButton(coordinator),
        TadoRefreshPresenceButton(coordinator),
        TadoManualPollButton(coordinator),
        TadoResumeAllSchedulesButton(coordinator),
        TadoTurnOffAllButton(coordinator),
        TadoBoostAllButton(coordinator),
    ]

    # Per-zone resume schedule buttons
    entities.extend(
        TadoZoneResumeScheduleButton(coordinator, zone.id, zone.name)
        for zone in coordinator.zones_meta.values()
        if zone.type == "HEATING"
    )
    async_add_entities(entities)


class TadoRefreshMetadataButton(TadoHomeEntity, ButtonEntity):
    """Button to refresh metadata (Zones/Devices)."""

    def __init__(self, coordinator: TadoDataUpdateCoordinator) -> None:
        """Initialize refresh metadata button."""
        super().__init__(coordinator, "refresh_metadata")
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_refresh_metadata"
        self._set_entity_id("button", "refresh_metadata")

    async def async_press(self) -> None:
        """Handle button press."""
        await self.tado_coordinator.async_manual_poll("metadata")


class TadoRefreshPresenceButton(TadoHomeEntity, ButtonEntity):
    """Button to refresh presence state."""

    def __init__(self, coordinator: TadoDataUpdateCoordinator) -> None:
        """Initialize refresh presence button."""
        super().__init__(coordinator, "refresh_presence")
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_refresh_presence"
        self._set_entity_id("button", "refresh_presence")

    async def async_press(self) -> None:
        """Handle button press."""
        await self.tado_coordinator.async_manual_poll("presence")


class TadoRefreshOffsetsButton(TadoHomeEntity, ButtonEntity):
    """Button to refresh temperature offsets."""

    def __init__(self, coordinator: TadoDataUpdateCoordinator) -> None:
        """Initialize refresh offsets button."""
        super().__init__(coordinator, "refresh_offsets")
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_refresh_offsets"
        self._set_entity_id("button", "refresh_offsets")

    async def async_press(self) -> None:
        """Handle button press."""
        await self.tado_coordinator.async_manual_poll("offsets")


class TadoRefreshAwayConfigButton(TadoHomeEntity, ButtonEntity):
    """Button to refresh away configuration."""

    def __init__(self, coordinator: TadoDataUpdateCoordinator) -> None:
        """Initialize refresh away button."""
        super().__init__(coordinator, "refresh_away")
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_refresh_away"
        self._set_entity_id("button", "refresh_away")

    async def async_press(self) -> None:
        """Handle button press."""
        await self.tado_coordinator.async_manual_poll("away")


class TadoManualPollButton(TadoHomeEntity, ButtonEntity):
    """Button to trigger a manual poll."""

    def __init__(self, coordinator: TadoDataUpdateCoordinator) -> None:
        """Initialize manual poll button."""
        super().__init__(coordinator, "full_manual_poll")
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_full_manual_poll"
        self._set_entity_id("button", "full_manual_poll")

    async def async_press(self) -> None:
        """Handle button press (debounced by ApiManager)."""
        _LOGGER.debug("Manual poll triggered via button")
        await self.tado_coordinator.async_manual_poll()


class TadoResumeAllSchedulesButton(TadoHomeEntity, ButtonEntity):
    """Button to resume all zone schedules."""

    def __init__(self, coordinator: TadoDataUpdateCoordinator) -> None:
        """Initialize resume all schedules button."""
        super().__init__(coordinator, "resume_all_schedules")
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_resume_all"
        self._set_entity_id("button", "resume_all_schedules")

    async def async_press(self) -> None:
        """Handle button press (debounced by ApiManager)."""
        _LOGGER.debug("Resume all schedules triggered via button")
        await self.tado_coordinator.async_resume_all_schedules()


class TadoTurnOffAllButton(TadoHomeEntity, ButtonEntity):
    """Button to turn off all heating zones."""

    def __init__(self, coordinator: TadoDataUpdateCoordinator) -> None:
        """Initialize turn off all button."""
        super().__init__(coordinator, "turn_off_all_zones")
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_turn_off_all"
        self._set_entity_id("button", "turn_off_all_zones")

    async def async_press(self) -> None:
        """Handle button press (debounced by ApiManager)."""
        _LOGGER.debug("Turn off all zones triggered via button")
        await self.tado_coordinator.async_turn_off_all_zones()


class TadoBoostAllButton(TadoHomeEntity, ButtonEntity):
    """Button to boost all heating zones."""

    def __init__(self, coordinator: TadoDataUpdateCoordinator) -> None:
        """Initialize boost all button."""
        super().__init__(coordinator, "boost_all_zones")
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_boost_all"
        self._set_entity_id("button", "boost_all_zones")

    async def async_press(self) -> None:
        """Handle button press (debounced by ApiManager)."""
        _LOGGER.debug("Boost all zones triggered via button")
        await self.tado_coordinator.async_boost_all_zones()


class TadoZoneResumeScheduleButton(TadoZoneEntity, ButtonEntity):
    """Button to resume schedule for a specific zone."""

    def __init__(
        self, coordinator: TadoDataUpdateCoordinator, zone_id: int, zone_name: str
    ) -> None:
        """Initialize zone resume schedule button."""
        super().__init__(coordinator, "resume_schedule", zone_id, zone_name)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_resume_{zone_id}"

    async def async_press(self) -> None:
        """Handle button press (debounced by ApiManager)."""
        _LOGGER.debug("Resume schedule zone %d triggered via button", self._zone_id)
        await self.tado_coordinator.async_set_zone_auto(self._zone_id)
        self.async_write_ha_state()
