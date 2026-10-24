"""Copy entities created in HomeKit or Matter onto the Hijack device.

This is the default. It stays off while attach is on, and in full cloud mode.
HomeKit Device (V3) or Matter (Tado X) remains the source.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button import SERVICE_PRESS, ButtonEntity
from homeassistant.components.climate import (
    ATTR_CURRENT_HUMIDITY,
    ATTR_CURRENT_TEMPERATURE,
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_HUMIDITY,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    ATTR_HVAC_MODES,
    ATTR_MAX_HUMIDITY,
    ATTR_MAX_TEMP,
    ATTR_MIN_HUMIDITY,
    ATTR_MIN_TEMP,
    ATTR_PRESET_MODE,
    ATTR_PRESET_MODES,
    ATTR_SWING_HORIZONTAL_MODE,
    ATTR_SWING_HORIZONTAL_MODES,
    ATTR_SWING_MODE,
    ATTR_SWING_MODES,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ATTR_TARGET_TEMP_STEP,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_HUMIDITY,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_SWING_HORIZONTAL_MODE,
    SERVICE_SET_SWING_MODE,
    SERVICE_SET_TEMPERATURE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.components.climate.const import (
    DEFAULT_MAX_HUMIDITY,
    DEFAULT_MIN_HUMIDITY,
)
from homeassistant.components.number import (
    ATTR_MAX,
    ATTR_MIN,
    ATTR_STEP,
    ATTR_VALUE,
    NumberEntity,
)
from homeassistant.components.number import (
    DOMAIN as NUMBER_DOMAIN,
)
from homeassistant.components.number import (
    SERVICE_SET_VALUE as NUMBER_SET_VALUE,
)
from homeassistant.components.select import (
    ATTR_OPTION,
    ATTR_OPTIONS,
    SERVICE_SELECT_OPTION,
    SelectEntity,
)
from homeassistant.components.select import (
    DOMAIN as SELECT_DOMAIN,
)
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    ATTR_TEMPERATURE,
    ATTR_UNIT_OF_MEASUREMENT,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import Event, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_registry import EVENT_ENTITY_REGISTRY_UPDATED
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import slugify

from ..const import (
    DEVICE_TYPE_MAP,
    DOMAIN,
    TEMP_MAX_PROXY,
    TEMP_MIN_PROXY,
    bridge_display_name,
    bridge_model_name,
)
from ..entity import TadoEntity
from .device_link import device_identifier, zone_device_identifier
from .device_linker import get_local_device, invalidate_cache
from .discovery import get_bridges, yield_devices
from .logging_utils import get_redacted_logger
from .zone_utils import (
    cloud_climate_can_follow_schedule,
    zone_follows_cloud_schedule,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, State
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from ..coordinator import TadoDataUpdateCoordinator

_LOGGER = get_redacted_logger(__name__)
_SERVICE_TARGET_KEYS = frozenset(marker.schema for marker in cv.TARGET_SERVICE_FIELDS)
_SKIP = {STATE_UNAVAILABLE, STATE_UNKNOWN}


@dataclass(frozen=True)
class ProxyHost:
    """Hijack device that receives the copied local entities."""

    serial: str
    short_serial: str
    device_type: str
    zone_id: int
    fw_version: str | None
    is_bridge: bool


def proxy_active(coordinator: TadoDataUpdateCoordinator) -> bool:
    """True when copies should be created."""
    return (
        not coordinator.full_cloud_mode
        and not coordinator.link_local_devices
        and coordinator.proxy_local_entities
    )


def _hosts(coordinator: TadoDataUpdateCoordinator) -> Iterator[ProxyHost]:
    seen: set[str] = set()
    for device, zone_id in yield_devices(coordinator):
        serial = str(getattr(device, "serial_no", "") or "")
        if not serial or serial in seen:
            continue
        seen.add(serial)
        yield ProxyHost(
            serial=serial,
            short_serial=str(getattr(device, "short_serial_no", None) or serial[-4:]),
            device_type=str(getattr(device, "device_type", "") or ""),
            zone_id=int(zone_id),
            fw_version=getattr(device, "current_fw_version", None),
            is_bridge=False,
        )
    for bridge in get_bridges(coordinator.devices_meta, coordinator.generation):
        serial = str(getattr(bridge, "serial_no", "") or "")
        if not serial or serial in seen:
            continue
        seen.add(serial)
        dtype = str(getattr(bridge, "device_type", "") or "")
        yield ProxyHost(
            serial=serial,
            short_serial=str(getattr(bridge, "short_serial_no", None) or serial[-4:]),
            device_type=dtype,
            zone_id=0,
            fw_version=getattr(bridge, "current_fw_version", None),
            is_bridge=True,
        )


def _proxy_key(source: er.RegistryEntry) -> str:
    """Stable role for this copy. Serial + key is the identity, not HomeKit's id."""
    if source.domain == CLIMATE_DOMAIN:
        return str(CLIMATE_DOMAIN)
    if source.domain == BUTTON_DOMAIN:
        return "identify"
    if source.original_device_class:
        return str(slugify(str(source.original_device_class)))
    if name := source.original_name or source.name:
        return str(slugify(str(name)))
    return str(source.domain)


def _uid(entry_id: str, serial: str, key: str) -> str:
    return f"{entry_id}_local_{key}_{serial}"


class LocalProxyManager:
    """Discover local Tado entities and add copies on the matching Hijack device."""

    def __init__(self, coordinator: TadoDataUpdateCoordinator) -> None:
        self._coordinator = coordinator
        self._adders: dict[str, AddEntitiesCallback] = {}
        self._proxies: dict[str, TadoLocalProxyBase] = {}
        self._unsub: Callable[[], None] | None = None

    @property
    def active(self) -> bool:
        return proxy_active(self._coordinator)

    def register(self, platform: str, adder: AddEntitiesCallback) -> None:
        """Store the platform adder and add any copies already visible."""
        self._adders[platform] = adder
        self._add_missing(platform)

    async def async_start(self) -> None:
        """Watch the registry for local entities that appear after setup."""
        if self._unsub is not None or not self.active:
            return
        self._unsub = self._coordinator.hass.bus.async_listen(
            EVENT_ENTITY_REGISTRY_UPDATED, self._on_registry_update
        )
        self._add_missing()

    def shutdown(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        self._adders.clear()
        self._proxies.clear()

    @callback
    def _on_registry_update(self, event: Event) -> None:
        entity_id = str(event.data.get("entity_id") or "")
        domain = entity_id.split(".", 1)[0]
        if domain in _PROXY_DOMAINS or str(event.data.get("action")) == "create":
            invalidate_cache()
            self._add_missing()

    def _add_missing(self, platform: str | None = None) -> None:
        if not self.active or self._coordinator.config_entry is None:
            return
        hass = self._coordinator.hass
        entry_id = self._coordinator.config_entry.entry_id
        e_reg = er.async_get(hass)
        new_by_domain: dict[str, list[TadoLocalProxyBase]] = {}
        for host, source in self._iter_sources(hass, e_reg, entry_id):
            if platform is not None and source.domain != platform:
                continue
            adder = self._adders.get(source.domain)
            cls = _CLASSES.get(source.domain)
            if adder is None or cls is None:
                continue
            unique = _uid(entry_id, host.serial, _proxy_key(source))
            existing = self._proxies.get(unique)
            if existing is not None:
                existing.rebind_source(hass, e_reg, source)
                continue
            entity = cls(self._coordinator, host, source)
            self._proxies[unique] = entity
            new_by_domain.setdefault(source.domain, []).append(entity)
        for domain, entities in new_by_domain.items():
            self._adders[domain](entities)
            _LOGGER.debug("Copied %d local %s entities", len(entities), domain)

    def _iter_sources(
        self,
        hass: HomeAssistant,
        e_reg: er.EntityRegistry,
        entry_id: str,
    ) -> Iterator[tuple[ProxyHost, er.RegistryEntry]]:
        generation = self._coordinator.generation
        for host in _hosts(self._coordinator):
            local = get_local_device(
                hass, host.serial, generation, exclude_entry_id=entry_id
            )
            if local is None:
                continue
            for source in er.async_entries_for_device(e_reg, local.id):
                if source.platform == DOMAIN or source.domain not in _PROXY_DOMAINS:
                    continue
                if source.disabled_by is not None:
                    continue
                yield host, source


_NAMED_KEYS = frozenset(
    {
        "battery",
        "child_lock",
        "climate",
        "humidity",
        "identify",
        "occupancy",
        "temperature",
        "valve",
        "window",
    }
)


class TadoLocalProxyBase(TadoEntity):
    """Hijack copy of a HomeKit or Matter entity."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        host: ProxyHost,
        source: er.RegistryEntry,
    ) -> None:
        key = _proxy_key(source)
        super().__init__(coordinator, f"local_{key}")
        if coordinator.config_entry is None:
            raise RuntimeError("Config entry not available")
        self._host = host
        self._source_entity_id = source.entity_id
        self._source_unsub: Callable[[], None] | None = None
        self._serial_no = host.serial
        self._attr_unique_id = _uid(coordinator.config_entry.entry_id, host.serial, key)
        self._set_entity_id(source.domain, f"local_{key}")
        if key not in _NAMED_KEYS:
            self._attr_name = source.original_name or source.name or key
        if source.entity_category is not None:
            self._attr_entity_category = EntityCategory(source.entity_category)
        if source.original_device_class is not None:
            self._attr_device_class = source.original_device_class
        if source.original_icon:
            self._attr_icon = source.original_icon

    def rebind_source(
        self,
        hass: HomeAssistant,
        e_reg: er.EntityRegistry,
        source: er.RegistryEntry,
    ) -> None:
        """Keep this entity when HomeKit is renamed, re-paired, or reappears."""
        if source.entity_id == self._source_entity_id:
            return
        current = e_reg.async_get(self._source_entity_id)
        if (
            current is not None
            and current.disabled_by is None
            and current.unique_id != source.unique_id
            and hass.states.get(self._source_entity_id) is not None
        ):
            return
        self._source_entity_id = source.entity_id
        if self.hass is not None:
            self._listen_source()
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._listen_source()
        self.async_on_remove(self._unlisten_source)

    def _listen_source(self) -> None:
        self._unlisten_source()
        self._source_unsub = async_track_state_change_event(
            self.hass, [self._source_entity_id], self._on_source
        )

    def _unlisten_source(self) -> None:
        if self._source_unsub is not None:
            self._source_unsub()
            self._source_unsub = None

    @callback
    def _on_source(self, _event: Event) -> None:
        self.async_write_ha_state()

    def _source(self) -> State | None:
        return self.hass.states.get(self._source_entity_id)

    @property
    def available(self) -> bool:
        state = self._source()
        return state is not None and state.state != STATE_UNAVAILABLE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self._source()
        if state is None:
            return {"source_entity_id": self._source_entity_id}
        attrs = {
            key: value
            for key, value in state.attributes.items()
            if key
            not in {
                "friendly_name",
                "icon",
                "device_class",
                "state_class",
                "unit_of_measurement",
                "supported_features",
            }
        }
        attrs["source_entity_id"] = self._source_entity_id
        return attrs

    @property
    def native_unit_of_measurement(self) -> str | None:
        return _unit_attr(self._source())

    @property
    def device_info(self) -> DeviceInfo:
        if self.coordinator.config_entry is None:
            raise RuntimeError("Config entry not available")
        serial = self._host.serial
        if self._host.is_bridge:
            return DeviceInfo(
                identifiers={device_identifier(serial)},
                name=bridge_display_name(
                    self._host.device_type, self._host.short_serial
                ),
                manufacturer="Tado",
                model=bridge_model_name(self._host.device_type),
                sw_version=self._host.fw_version,
                serial_number=serial,
            )
        model_name = DEVICE_TYPE_MAP.get(self._host.device_type, self._host.device_type)
        try:
            via_device_id = dr.async_get_device_id_by_identifier(
                self.coordinator.hass,
                zone_device_identifier(
                    self.coordinator.config_entry.entry_id, self._host.zone_id
                ),
                config_entry_id=self.coordinator.config_entry.entry_id,
            )
        except ValueError:
            via_device_id = None
        info = DeviceInfo(
            identifiers={device_identifier(serial)},
            name=f"tado {model_name} {self._host.short_serial}",
            manufacturer="Tado",
            model=model_name,
            sw_version=self._host.fw_version,
            serial_number=serial,
        )
        if via_device_id is not None:
            info["via_device_id"] = via_device_id
        return info

    async def _async_call(
        self, domain: str, service: str, data: dict[str, Any]
    ) -> None:
        payload = {
            key: value for key, value in data.items() if key not in _SERVICE_TARGET_KEYS
        }
        payload[ATTR_ENTITY_ID] = self._source_entity_id
        await self.hass.services.async_call(
            domain,
            service,
            payload,
            blocking=True,
        )


class TadoLocalClimateProxy(TadoLocalProxyBase, ClimateEntity):
    """Copy of a local climate entity.

    HomeKit and Matter have no auto mode. Auto is added when the cloud
    climate for this zone can resume onto its plan. The cached week is not
    required. Auto resumes through Hijack and is not sent to the source.
    """

    def _on_cloud_schedule(self) -> bool:
        """True when Hijack, not the valve, says this zone is on its plan."""
        coordinator = self.tado_coordinator
        zone_id = self._host.zone_id
        return cloud_climate_can_follow_schedule(
            coordinator, zone_id
        ) and zone_follows_cloud_schedule(coordinator, zone_id)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = super().extra_state_attributes
        attrs.pop(ATTR_HVAC_MODES, None)
        return attrs

    @property
    def hvac_mode(self) -> HVACMode:
        if self._on_cloud_schedule():
            return HVACMode.AUTO
        state = self._source()
        if state is None:
            return HVACMode.OFF
        try:
            return HVACMode(state.state)
        except ValueError:
            return HVACMode.OFF

    @property
    def hvac_modes(self) -> list[HVACMode]:
        state = self._source()
        raw = state.attributes.get(ATTR_HVAC_MODES) if state else None
        if not raw:
            modes = [HVACMode.OFF, HVACMode.HEAT]
        else:
            modes = []
            for item in raw:
                with contextlib.suppress(ValueError):
                    modes.append(HVACMode(item))
            if not modes:
                modes = [HVACMode.OFF]
        if (
            cloud_climate_can_follow_schedule(self.tado_coordinator, self._host.zone_id)
            and HVACMode.AUTO not in modes
        ):
            modes.append(HVACMode.AUTO)
        return modes

    @property
    def hvac_action(self) -> HVACAction | None:
        state = self._source()
        raw = state.attributes.get(ATTR_HVAC_ACTION) if state else None
        if raw is None:
            return None
        try:
            return HVACAction(raw)
        except ValueError:
            return None

    @property
    def current_temperature(self) -> float | None:
        return _float_attr(self._source(), ATTR_CURRENT_TEMPERATURE)

    @property
    def target_temperature(self) -> float | None:
        return _float_attr(self._source(), ATTR_TEMPERATURE)

    @property
    def target_temperature_high(self) -> float | None:
        return _float_attr(self._source(), ATTR_TARGET_TEMP_HIGH)

    @property
    def target_temperature_low(self) -> float | None:
        return _float_attr(self._source(), ATTR_TARGET_TEMP_LOW)

    @property
    def current_humidity(self) -> float | None:
        return _float_attr(self._source(), ATTR_CURRENT_HUMIDITY)

    @property
    def target_humidity(self) -> float | None:
        return _float_attr(self._source(), ATTR_HUMIDITY)

    @property
    def min_humidity(self) -> float:
        return _float_attr_default(
            self._source(), ATTR_MIN_HUMIDITY, DEFAULT_MIN_HUMIDITY
        )

    @property
    def max_humidity(self) -> float:
        return _float_attr_default(
            self._source(), ATTR_MAX_HUMIDITY, DEFAULT_MAX_HUMIDITY
        )

    @property
    def min_temp(self) -> float:
        return _float_attr_default(self._source(), ATTR_MIN_TEMP, TEMP_MIN_PROXY)

    @property
    def max_temp(self) -> float:
        return _float_attr_default(self._source(), ATTR_MAX_TEMP, TEMP_MAX_PROXY)

    @property
    def target_temperature_step(self) -> float | None:
        return _float_attr(self._source(), ATTR_TARGET_TEMP_STEP)

    @property
    def temperature_unit(self) -> str:
        state = self._source()
        unit = (
            state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
            if state is not None
            else None
        )
        return str(unit) if unit is not None else UnitOfTemperature.CELSIUS

    @property
    def supported_features(self) -> ClimateEntityFeature:
        state = self._source()
        if state is None:
            return ClimateEntityFeature(0)
        return ClimateEntityFeature(
            int(state.attributes.get(ATTR_SUPPORTED_FEATURES) or 0)
        )

    @property
    def fan_mode(self) -> str | None:
        return _str_attr(self._source(), ATTR_FAN_MODE)

    @property
    def fan_modes(self) -> list[str] | None:
        return _list_attr(self._source(), ATTR_FAN_MODES)

    @property
    def swing_mode(self) -> str | None:
        return _str_attr(self._source(), ATTR_SWING_MODE)

    @property
    def swing_modes(self) -> list[str] | None:
        return _list_attr(self._source(), ATTR_SWING_MODES)

    @property
    def swing_horizontal_mode(self) -> str | None:
        return _str_attr(self._source(), ATTR_SWING_HORIZONTAL_MODE)

    @property
    def swing_horizontal_modes(self) -> list[str] | None:
        return _list_attr(self._source(), ATTR_SWING_HORIZONTAL_MODES)

    @property
    def preset_mode(self) -> str | None:
        return _str_attr(self._source(), ATTR_PRESET_MODE)

    @property
    def preset_modes(self) -> list[str] | None:
        return _list_attr(self._source(), ATTR_PRESET_MODES)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        data = {key: value for key, value in kwargs.items() if value is not None}
        await self._async_call(CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE, data)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.AUTO:
            if not cloud_climate_can_follow_schedule(
                self.tado_coordinator, self._host.zone_id
            ):
                raise ServiceValidationError(
                    "This zone cannot follow a cloud schedule."
                )
            await self.coordinator.async_set_zone_auto(self._host.zone_id)
            return
        await self._async_call(
            CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE, {ATTR_HVAC_MODE: hvac_mode}
        )

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        await self._async_call(
            CLIMATE_DOMAIN, SERVICE_SET_FAN_MODE, {ATTR_FAN_MODE: fan_mode}
        )

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        await self._async_call(
            CLIMATE_DOMAIN, SERVICE_SET_SWING_MODE, {ATTR_SWING_MODE: swing_mode}
        )

    async def async_set_swing_horizontal_mode(self, swing_horizontal_mode: str) -> None:
        await self._async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_SWING_HORIZONTAL_MODE,
            {ATTR_SWING_HORIZONTAL_MODE: swing_horizontal_mode},
        )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        await self._async_call(
            CLIMATE_DOMAIN, SERVICE_SET_PRESET_MODE, {ATTR_PRESET_MODE: preset_mode}
        )

    async def async_set_humidity(self, humidity: int) -> None:
        await self._async_call(
            CLIMATE_DOMAIN, SERVICE_SET_HUMIDITY, {ATTR_HUMIDITY: humidity}
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_call(CLIMATE_DOMAIN, SERVICE_TURN_ON, kwargs)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_call(CLIMATE_DOMAIN, SERVICE_TURN_OFF, kwargs)


class TadoLocalSensorProxy(TadoLocalProxyBase, SensorEntity):
    """Copy of a local sensor."""

    @property
    def native_value(self) -> Any:
        state = self._source()
        return None if state is None or state.state in _SKIP else state.state

    @property
    def state_class(self) -> str | None:
        state = self._source()
        if state is None:
            return None
        raw = state.attributes.get("state_class")
        return str(raw) if raw is not None else None


class TadoLocalBinarySensorProxy(TadoLocalProxyBase, BinarySensorEntity):
    """Copy of a local binary sensor."""

    @property
    def is_on(self) -> bool:
        state = self._source()
        return state is not None and state.state == STATE_ON


class TadoLocalButtonProxy(TadoLocalProxyBase, ButtonEntity):
    """Copy of a local button."""

    async def async_press(self) -> None:
        await self._async_call(BUTTON_DOMAIN, SERVICE_PRESS, {})


class TadoLocalNumberProxy(TadoLocalProxyBase, NumberEntity):
    """Copy of a local number."""

    @property
    def native_value(self) -> float | None:
        return _float_state(self._source())

    @property
    def native_min_value(self) -> float:
        return _float_attr_default(self._source(), ATTR_MIN, 0.0)

    @property
    def native_max_value(self) -> float:
        return _float_attr_default(self._source(), ATTR_MAX, 100.0)

    @property
    def native_step(self) -> float:
        return _float_attr_default(self._source(), ATTR_STEP, 1.0)

    async def async_set_native_value(self, value: float) -> None:
        await self._async_call(NUMBER_DOMAIN, NUMBER_SET_VALUE, {ATTR_VALUE: value})


class TadoLocalSwitchProxy(TadoLocalProxyBase, SwitchEntity):
    """Copy of a local switch."""

    @property
    def is_on(self) -> bool:
        state = self._source()
        return state is not None and state.state == STATE_ON

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_call(SWITCH_DOMAIN, SERVICE_TURN_ON, kwargs)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_call(SWITCH_DOMAIN, SERVICE_TURN_OFF, kwargs)


class TadoLocalSelectProxy(TadoLocalProxyBase, SelectEntity):
    """Copy of a local select."""

    @property
    def current_option(self) -> str | None:
        state = self._source()
        return None if state is None or state.state in _SKIP else str(state.state)

    @property
    def options(self) -> list[str]:
        return _list_attr(self._source(), ATTR_OPTIONS) or []

    async def async_select_option(self, option: str) -> None:
        await self._async_call(
            SELECT_DOMAIN, SERVICE_SELECT_OPTION, {ATTR_OPTION: option}
        )


_CLASSES: dict[str, type[TadoLocalProxyBase]] = {
    CLIMATE_DOMAIN: TadoLocalClimateProxy,
    SENSOR_DOMAIN: TadoLocalSensorProxy,
    BINARY_SENSOR_DOMAIN: TadoLocalBinarySensorProxy,
    BUTTON_DOMAIN: TadoLocalButtonProxy,
    NUMBER_DOMAIN: TadoLocalNumberProxy,
    SWITCH_DOMAIN: TadoLocalSwitchProxy,
    SELECT_DOMAIN: TadoLocalSelectProxy,
}
_PROXY_DOMAINS = frozenset(_CLASSES)


def _float_attr(state: State | None, key: str) -> float | None:
    if state is None:
        return None
    raw = state.attributes.get(key)
    try:
        return None if raw is None else float(raw)
    except TypeError, ValueError:
        return None


def _float_attr_default(state: State | None, key: str, default: float) -> float:
    value = _float_attr(state, key)
    return default if value is None else value


def _float_state(state: State | None) -> float | None:
    if state is None or state.state in _SKIP:
        return None
    try:
        return float(state.state)
    except TypeError, ValueError:
        return None


def _unit_attr(state: State | None) -> str | None:
    if state is None:
        return None
    unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
    return str(unit) if unit is not None else None


def _str_attr(state: State | None, key: str) -> str | None:
    if state is None:
        return None
    raw = state.attributes.get(key)
    return None if raw is None else str(raw)


def _list_attr(state: State | None, key: str) -> list[str] | None:
    if state is None:
        return None
    raw = state.attributes.get(key)
    return [str(item) for item in raw] if isinstance(raw, list) else None
