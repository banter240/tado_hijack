"""Base entity for Tado Hijack."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import DEVICE_TYPE_MAP, DOMAIN
from .helpers.device_linker import get_homekit_identifiers

if TYPE_CHECKING:
    from typing import Any
    from .coordinator import TadoDataUpdateCoordinator


class TadoOptimisticMixin:
    """Mixin for entities checking optimistic state before actual state."""

    coordinator: TadoDataUpdateCoordinator
    _attr_optimistic_key: str | None = None
    _attr_optimistic_scope: str | None = None

    def _get_optimistic_value(self) -> Any | None:
        """Return optimistic value from coordinator if set."""
        if not self._attr_optimistic_key or not self._attr_optimistic_scope:
            return None

        # Resolve ID based on scope
        entity_id: str | int | None = None
        if self._attr_optimistic_scope == "zone":
            entity_id = getattr(self, "_zone_id", None)
        elif self._attr_optimistic_scope == "device":
            entity_id = getattr(self, "_serial_no", None)
        elif self._attr_optimistic_scope == "home":
            entity_id = "global"

        if entity_id is None:
            return None

        return self.coordinator.optimistic.get_optimistic(
            self._attr_optimistic_scope, entity_id, self._attr_optimistic_key
        )

    def _get_actual_value(self) -> Any:
        """Return actual value from coordinator data."""
        raise NotImplementedError

    def _resolve_state(self) -> Any:
        """Resolve state: Optimistic > Actual."""
        if (opt := self._get_optimistic_value()) is not None:
            return opt
        return self._get_actual_value()


class TadoStateMemoryMixin(RestoreEntity):
    """Mixin to remember and restore specific states (like last temp)."""

    _state_memory: dict[str, Any]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the memory mixin."""
        super().__init__(*args, **kwargs)
        self._state_memory = {}

    async def async_added_to_hass(self) -> None:
        """Restore state from HA state machine."""
        await super().async_added_to_hass()
        if last_state := await self.async_get_last_state():
            for key in self._state_memory:
                attr_key = f"last_{key}"
                if attr_key in last_state.attributes:
                    self._state_memory[key] = last_state.attributes[attr_key]

    def _store_last_state(self, key: str, value: Any) -> None:
        """Store a value in memory."""
        if value is not None:
            self._state_memory[key] = value

    def _get_last_state(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from memory."""
        return self._state_memory.get(key, default)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes including memory."""
        attrs: dict[str, Any] = {}
        # Try to get attributes from other mixins/bases if they exist
        if (
            hasattr(super(), "extra_state_attributes")
            and (super_attrs := super().extra_state_attributes) is not None
        ):
            attrs |= super_attrs

        # Add memory attributes (prefixed with last_)
        for key, value in self._state_memory.items():
            attrs[f"last_{key}"] = value
        return attrs


class TadoEntity(CoordinatorEntity):
    """Base class for Tado Hijack entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        translation_key: str | None,
    ) -> None:
        """Initialize Tado entity."""
        super().__init__(coordinator)
        self._attr_translation_key = translation_key

    @property
    def tado_coordinator(self) -> TadoDataUpdateCoordinator:
        """Return the coordinator."""
        return cast("TadoDataUpdateCoordinator", self.coordinator)


class TadoHomeEntity(TadoEntity):
    """Entity belonging to the Tado Home device."""

    def _set_entity_id(self, domain: str, key: str, prefix: str = "tado") -> None:
        """Set entity_id before registration. Call in subclass __init__."""
        title = (
            self.coordinator.config_entry.title
            if self.coordinator.config_entry
            else "home"
        )
        if title.startswith("Tado "):
            title = title[5:]
        home_slug = slugify(title)
        self.entity_id = f"{domain}.{prefix}_{home_slug}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the home."""
        if self.coordinator.config_entry is None:
            raise RuntimeError("Config entry not available")

        identifiers = {(DOMAIN, self.coordinator.config_entry.entry_id)}

        name = self.coordinator.config_entry.title
        model = "Internet Bridge"
        sw_version = None

        # Link to Bridges if found
        for bridge in self.coordinator.bridges:
            identifiers.add((DOMAIN, bridge.serial_no))
            if hk_ids := get_homekit_identifiers(
                self.coordinator.hass, bridge.serial_no
            ):
                identifiers.update(hk_ids)

            # Use first bridge for metadata (HomeKit-style name)
            if sw_version is None:
                name = f"tado Internet Bridge {bridge.serial_no}"
                model = bridge.device_type
                sw_version = bridge.current_fw_version

        return DeviceInfo(
            identifiers=identifiers,
            name=name,
            manufacturer="Tado",
            model=model,
            sw_version=sw_version,
            configuration_url="https://app.tado.com",
        )


class TadoZoneEntity(TadoEntity):
    """Entity belonging to a specific Tado Zone device."""

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        translation_key: str,
        zone_id: int,
        zone_name: str,
    ) -> None:
        """Initialize Tado zone entity."""
        super().__init__(coordinator, translation_key)
        self._zone_id = zone_id
        self._zone_name = zone_name

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the zone."""
        if self.coordinator.config_entry is None:
            raise RuntimeError("Config entry not available")
        return DeviceInfo(
            identifiers={(DOMAIN, f"zone_{self._zone_id}")},
            name=self._zone_name,
            manufacturer="Tado",
            model="Heating Zone",
            via_device=(DOMAIN, self.coordinator.config_entry.entry_id),
        )


class TadoHotWaterZoneEntity(TadoEntity):
    """Entity belonging to a specific Tado Hot Water Zone device."""

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        translation_key: str,
        zone_id: int,
        zone_name: str,
    ) -> None:
        """Initialize Tado hot water zone entity."""
        super().__init__(coordinator, translation_key)
        self._zone_id = zone_id
        self._zone_name = zone_name

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the hot water zone."""
        if self.coordinator.config_entry is None:
            raise RuntimeError("Config entry not available")
        # Use zone name directly - Tado typically names it "Hot Water" already
        return DeviceInfo(
            identifiers={(DOMAIN, f"zone_{self._zone_id}")},
            name=self._zone_name,
            manufacturer="Tado",
            model="Hot Water Zone",
            via_device=(DOMAIN, self.coordinator.config_entry.entry_id),
        )


class TadoDeviceEntity(TadoEntity):
    """Entity belonging to a specific Tado physical device (Valve/Thermostat)."""

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        translation_key: str,
        serial_no: str,
        short_serial: str,
        device_type: str,
        zone_id: int,
        fw_version: str | None = None,
    ) -> None:
        """Initialize Tado device entity."""
        super().__init__(coordinator, translation_key)
        self._serial_no = serial_no
        self._short_serial = short_serial
        self._device_type = device_type
        self._zone_id = zone_id
        self._fw_version = fw_version

        self._linked_identifiers = get_homekit_identifiers(coordinator.hass, serial_no)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the physical device."""
        identifiers = {(DOMAIN, self._serial_no)}
        if self._linked_identifiers:
            identifiers.update(self._linked_identifiers)

        model_name = DEVICE_TYPE_MAP.get(self._device_type, self._device_type)

        return DeviceInfo(
            identifiers=identifiers,
            name=f"tado {model_name} {self._short_serial}",
            manufacturer="Tado",
            model=model_name,
            via_device=(DOMAIN, f"zone_{self._zone_id}"),
            sw_version=self._fw_version,
            serial_number=self._serial_no,
        )
