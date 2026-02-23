"""Models for Tado Hijack."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, TypedDict

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.helpers.entity import EntityCategory

if TYPE_CHECKING:
    from tadoasync.models import (
        Capabilities,
        Device,
        HomeState,
        TemperatureOffset,
        Zone,
        ZoneState,
    )


@dataclass(slots=True)
class RateLimit:
    """Model for API Rate Limit statistics."""

    limit: int
    remaining: int


@dataclass
class TadoData:
    """Data structure to hold Tado data.

    Provides type safety and IDE autocomplete for data dictionary access.
    Updated by DataManager.fetch_full_update() and coordinator._async_update_data().
    """

    home_state: HomeState | None = None
    zone_states: dict[str, ZoneState] = field(default_factory=dict)
    rate_limit: RateLimit = field(default_factory=lambda: RateLimit(0, 0))
    api_status: str = "unknown"
    zones: dict[int, Zone] = field(default_factory=dict)
    devices: dict[str, Device] = field(default_factory=dict)
    capabilities: dict[int, Capabilities] = field(default_factory=dict)
    offsets: dict[str, TemperatureOffset] = field(default_factory=dict)
    away_config: dict[int, float] = field(default_factory=dict)


class CommandType(StrEnum):
    """Types of API commands."""

    SET_OVERLAY = "set_overlay"
    RESUME_SCHEDULE = "resume_schedule"
    SET_PRESENCE = "set_presence"
    MANUAL_POLL = "manual_poll"
    SET_CHILD_LOCK = "set_child_lock"
    SET_OFFSET = "set_offset"
    SET_AWAY_TEMP = "set_away_temp"
    SET_DAZZLE = "set_dazzle"
    SET_EARLY_START = "set_early_start"
    SET_OPEN_WINDOW = "set_open_window"
    IDENTIFY = "identify"


@dataclass
class TadoCommand:
    """Represents a queued API command."""

    cmd_type: CommandType
    zone_id: int | None = None
    data: dict[str, Any] | None = None
    rollback_context: Any = None


class TadoEntityDefinition(TypedDict, total=False):
    """Define properties for a Tado entity."""

    key: str
    translation_key: str | None
    unique_id_suffix: str | None
    use_legacy_unique_id_format: bool | None
    platform: str  # "sensor", "binary_sensor", etc.
    scope: str  # "home", "zone", "device", "hot_water", "bridge"

    # Function to extract value.
    # Signature depends on scope:
    # - home: (coordinator) -> value
    # - zone: (coordinator, zone_id) -> value
    # - device: (coordinator, device_serial) -> value
    # - bridge: (coordinator, bridge_serial) -> value
    value_fn: Callable[..., Any]
    is_supported_fn: Callable[..., bool] | None
    press_fn: Callable[..., Any] | None
    set_fn: Callable[..., Any] | None
    turn_on_fn: Callable[..., Any] | None
    turn_off_fn: Callable[..., Any] | None

    # Select Entity Specifics
    options_fn: Callable[..., list[str]] | None
    select_option_fn: Callable[..., Any] | None

    # Standard HA Entity Properties
    icon: str | None
    ha_device_class: SensorDeviceClass | None
    ha_state_class: SensorStateClass | None
    ha_native_unit_of_measurement: str | None
    suggested_display_precision: int | None
    entity_category: EntityCategory | None
    entity_registry_enabled_default: bool | None
    supported_zone_types: set[str] | None
    supported_generations: set[str] | None  # None = all generations
    required_device_capabilities: list[str] | None
    is_inverted: bool | None

    # Number Entity Specifics
    min_value: float | None
    max_value: float | None
    step: float | None
    min_fn: Callable[..., float] | None
    max_fn: Callable[..., float] | None
    step_fn: Callable[..., float] | None
    optimistic_key: str | None
    optimistic_scope: str | None
    optimistic_value_map: dict[str, bool] | None
