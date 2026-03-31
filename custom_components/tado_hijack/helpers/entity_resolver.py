"""Helpers for resolving Home Assistant entities to Tado zones."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers import entity_registry as er

from ..const import DOMAIN
from .logging_utils import get_redacted_logger

if TYPE_CHECKING:
    from ..coordinator import TadoDataUpdateCoordinator


_LOGGER = get_redacted_logger(__name__)


class EntityResolver:
    """Handles resolution of HA entity IDs to Tado zone IDs."""

    def __init__(self, coordinator: TadoDataUpdateCoordinator) -> None:
        """Initialize the resolver."""
        self.coordinator = coordinator
        self.hass = coordinator.hass
        self._cache: dict[str, int] = {}

    def get_zone_id(self, entity_id: str) -> int | None:
        """Resolve a Tado zone ID from any entity ID (HomeKit or Hijack)."""
        if entity_id in self._cache:
            return self._cache[entity_id]

        # Check climate map (HomeKit)
        if (zone_id := self.coordinator._climate_to_zone.get(entity_id)) is not None:
            self._cache[entity_id] = zone_id
            return zone_id

        ent_reg = er.async_get(self.hass)
        if entry := ent_reg.async_get(entity_id):
            if (
                entry.platform == DOMAIN
                and entry.config_entry_id == self.coordinator.config_entry.entry_id
            ):
                if (zone_id := self.parse_unique_id(entry.unique_id)) is not None:
                    self._cache[entity_id] = zone_id
                    return zone_id

                # Try to resolve via device serial_no (for TRV/device entities)
                if (
                    zone_id := self._resolve_device_to_zone(entry.unique_id)
                ) is not None:
                    self._cache[entity_id] = zone_id
                    return zone_id

        # Deep scan
        _LOGGER.debug("Starting deep entity registry scan for %s", entity_id)
        target_name = entity_id.split(".", 1)[-1]
        target_base = self._get_entity_base_name(target_name)

        for entity_entry in er.async_entries_for_config_entry(
            ent_reg, self.coordinator.config_entry.entry_id
        ):
            if (zid := self.parse_unique_id(entity_entry.unique_id)) is not None:
                self._cache[entity_entry.entity_id] = zid
                entry_name = entity_entry.entity_id.split(".", 1)[-1]
                if entry_base := self._get_entity_base_name(entry_name):
                    self._cache[f"{entity_entry.domain}.{entry_base}"] = zid

        if entity_id in self._cache:
            return self._cache[entity_id]

        if target_base:
            for domain in ["water_heater", "climate", "switch", "sensor"]:
                if (zid := self._cache.get(f"{domain}.{target_base}")) is not None:
                    self._cache[entity_id] = zid
                    return zid
        return None

    @staticmethod
    def _get_entity_base_name(entity_name: str | None) -> str | None:
        """Normalize an entity name by stripping numeric suffixes."""
        if not entity_name:
            return None
        if entity_name[-1].isdigit() and "_" in entity_name:
            return entity_name.rsplit("_", 1)[0]
        return entity_name

    def parse_unique_id(self, unique_id: str) -> int | None:
        """Extract zone ID from unique_id with support for multiple formats."""
        try:
            parts = unique_id.split("_")
            if parts[-1].isdigit():
                return int(parts[-1])

            for i, part in enumerate(parts):
                if part == "zone" and i + 1 < len(parts) and parts[i + 1].isdigit():
                    return int(parts[i + 1])
        except (ValueError, IndexError, AttributeError):
            pass
        return None

    def _resolve_device_to_zone(self, unique_id: str) -> int | None:
        """Find zone owning device by extracting serial_no from unique_id.

        Format: {entry_id}_{type}_{serial_no}
        Examples: battery_RU1234567, child_lock_VA9876543
        """
        try:
            parts = unique_id.split("_")
            if len(parts) >= 3:  # noqa: PLR2004
                serial_no = parts[-1]

                for zone in self.coordinator.zones_meta.values():
                    for device in zone.devices:
                        if device.serial_no == serial_no:
                            _LOGGER.debug(
                                "Resolved device %s to zone %d via serial %s",
                                unique_id,
                                zone.id,
                                serial_no,
                            )
                            return zone.id
        except (ValueError, IndexError, AttributeError):
            pass
        return None

    def get_serial_from_entity(self, entity_id: str) -> str | None:
        """Resolve a device serial number from a device entity ID.

        Checks each known device serial against the entity's unique_id,
        which handles both legacy ({serial}_{suffix}) and modern ({entry_id}_{suffix}_{serial}) formats.
        """
        ent_reg = er.async_get(self.hass)
        if entry := ent_reg.async_get(entity_id):
            return next(
                (
                    serial
                    for serial in self.coordinator.data_manager.devices_meta
                    if serial in entry.unique_id
                ),
                None,
            )
        else:
            return None

    def is_zone_disabled(self, zone_id: int) -> bool:
        """Check if the zone control is disabled by user."""
        if not self.coordinator.config_entry:
            return False

        ent_reg = er.async_get(self.hass)
        unique_id = f"{self.coordinator.config_entry.entry_id}_sch_{zone_id}"
        if entity_id := ent_reg.async_get_entity_id("switch", DOMAIN, unique_id):
            entry = ent_reg.async_get(entity_id)
            if entry and entry.disabled:
                return True
        return False
