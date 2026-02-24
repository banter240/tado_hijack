"""Entity Definitions for Tado Hijack."""

from __future__ import annotations

from typing import Any, Final, cast

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util import dt as dt_util

from .const import (
    CAPABILITY_INSIDE_TEMP,
    CONF_API_PROXY_URL,
    CONF_PROXY_TOKEN,
    CONF_AUTO_API_QUOTA_PERCENT,
    CONF_DEBOUNCE_TIME,
    CONF_DISABLE_POLLING_WHEN_THROTTLED,
    CONF_LOG_LEVEL,
    CONF_JITTER_PERCENT,
    CONF_MIN_AUTO_QUOTA_INTERVAL_S,
    CONF_OFFSET_POLL_INTERVAL,
    CONF_PRESENCE_POLL_INTERVAL,
    CONF_REDUCED_POLLING_ACTIVE,
    CONF_REDUCED_POLLING_END,
    CONF_REDUCED_POLLING_INTERVAL,
    CONF_REDUCED_POLLING_START,
    CONF_REFRESH_AFTER_RESUME,
    CONF_SLOW_POLL_INTERVAL,
    CONF_THROTTLE_THRESHOLD,
    CONF_SUPPRESS_REDUNDANT_CALLS,
    CONF_SUPPRESS_REDUNDANT_BUTTONS,
    DEFAULT_SUPPRESS_REDUNDANT_CALLS,
    DEFAULT_SUPPRESS_REDUNDANT_BUTTONS,
    DEFAULT_AUTO_API_QUOTA_PERCENT,
    DEFAULT_DEBOUNCE_TIME,
    DEFAULT_JITTER_PERCENT,
    DEFAULT_LOG_LEVEL,
    DEFAULT_MIN_AUTO_QUOTA_INTERVAL_S,
    DEFAULT_OFFSET_POLL_INTERVAL,
    DEFAULT_PRESENCE_POLL_INTERVAL,
    DEFAULT_REDUCED_POLLING_END,
    DEFAULT_REDUCED_POLLING_INTERVAL,
    DEFAULT_REDUCED_POLLING_START,
    DEFAULT_REFRESH_AFTER_RESUME,
    DEFAULT_SLOW_POLL_INTERVAL,
    DEFAULT_THROTTLE_THRESHOLD,
    GEN_CLASSIC,
    GEN_X,
    TEMP_MAX_AC,
    TEMP_MAX_HOT_WATER_OVERRIDE,
    TEMP_MIN_AC,
    TEMP_MIN_HOT_WATER,
    ZONE_TYPE_AIR_CONDITIONING,
    ZONE_TYPE_HEATING,
    ZONE_TYPE_HOT_WATER,
)
from .helpers.parsers import get_ac_capabilities
from .helpers.quota_math import get_next_reset_time
from .helpers.tadov3 import parsers as v3_parsers
from .helpers.tadox import parsers as tadox_parsers
from .models import TadoEntityDefinition


def _get_owd_timeout(c: Any, zid: int) -> int:
    """Resolve open window detection timeout (optimistic > cache)."""
    opt = c.optimistic.get_open_window(zid)
    if opt is not None:
        return int(opt)

    zone = c.zones_meta.get(zid)
    if zone and zone.open_window_detection and zone.open_window_detection.enabled:
        return int(zone.open_window_detection.timeout_in_seconds)
    return 0


def _get_away_temp(c: Any, zid: int) -> float:
    """Resolve away temperature (optimistic > cache)."""
    opt = c.optimistic.get_away_temp(zid)
    return float(c.data.away_config.get(zid) or 0.0) if opt is None else float(opt)


def _get_next_reset_timestamp(c: Any) -> Any:
    """Get next expected quota reset as datetime object."""
    try:
        window = c.reset_tracker.get_expected_window()
        expected_hour = window.hour if window.confidence == "learned" else None
        expected_minute = window.minute if window.confidence == "learned" else None
        return get_next_reset_time(
            expected_hour, expected_minute, c.reset_tracker.get_last_reset_original()
        )
    except Exception:
        return None


def _create_definition(
    key: str,
    platform: str,
    scope: str,
    value_fn: Any,
    icon: str | None = None,
    device_class: SensorDeviceClass | None = None,
    state_class: SensorStateClass | None = None,
    unit: str | None = None,
    entity_category: EntityCategory | None = None,
    translation_key: str | None = None,
    enabled_default: bool = True,
    supported_zone_types: set[str] | None = None,
    supported_generations: set[str] | None = None,
    required_device_capabilities: list[str] | None = None,
    is_supported_fn: Any | None = None,
    press_fn: Any | None = None,
    set_fn: Any | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    step: float | None = None,
    min_fn: Any | None = None,
    max_fn: Any | None = None,
    step_fn: Any | None = None,
    optimistic_key: str | None = None,
    optimistic_scope: str | None = None,
    turn_on_fn: Any | None = None,
    turn_off_fn: Any | None = None,
    is_inverted: bool | None = None,
    options_fn: Any | None = None,
    select_option_fn: Any | None = None,
    unique_id_suffix: str | None = None,
    use_legacy_unique_id_format: bool | None = None,
    optimistic_value_map: dict[str, bool] | None = None,
    suggested_display_precision: int | None = None,
) -> TadoEntityDefinition:
    """Create a TadoEntityDefinition."""
    return cast(
        TadoEntityDefinition,
        {
            "key": key,
            "translation_key": translation_key or key,
            "unique_id_suffix": unique_id_suffix,
            "use_legacy_unique_id_format": use_legacy_unique_id_format,
            "platform": platform,
            "scope": scope,
            "value_fn": value_fn,
            "is_supported_fn": is_supported_fn,
            "press_fn": press_fn,
            "set_fn": set_fn,
            "turn_on_fn": turn_on_fn,
            "turn_off_fn": turn_off_fn,
            "options_fn": options_fn,
            "select_option_fn": select_option_fn,
            "icon": icon,
            "ha_device_class": device_class,
            "ha_state_class": state_class,
            "ha_native_unit_of_measurement": unit,
            "suggested_display_precision": suggested_display_precision,
            "entity_category": entity_category,
            "entity_registry_enabled_default": enabled_default,
            "supported_zone_types": supported_zone_types,
            "supported_generations": supported_generations,
            "required_device_capabilities": required_device_capabilities,
            "min_value": min_value,
            "max_value": max_value,
            "step": step,
            "min_fn": min_fn,
            "max_fn": max_fn,
            "step_fn": step_fn,
            "optimistic_key": optimistic_key,
            "optimistic_scope": optimistic_scope,
            "optimistic_value_map": optimistic_value_map,
            "is_inverted": is_inverted,
        },
    )


def create_home_sensor(
    key: str,
    value_fn: Any,
    icon: str | None = None,
    device_class: SensorDeviceClass | None = None,
    state_class: SensorStateClass | None = None,
    unit: str | None = None,
    entity_category: EntityCategory | None = None,
) -> TadoEntityDefinition:
    """Create a sensor for the Tado Home (global scope)."""
    return _create_definition(
        key=key,
        platform="sensor",
        scope="home",
        value_fn=value_fn,
        icon=icon,
        device_class=device_class,
        state_class=state_class,
        unit=unit,
        entity_category=entity_category,
    )


def create_diagnostic_sensor(
    key: str,
    value_fn: Any,
    icon: str | None = None,
    unit: str | None = None,
    state_class: SensorStateClass | None = None,
    device_class: SensorDeviceClass | None = None,
) -> TadoEntityDefinition:
    """Create a diagnostic sensor (Home scope)."""
    return create_home_sensor(
        key=key,
        value_fn=value_fn,
        icon=icon,
        unit=unit,
        state_class=state_class,
        device_class=device_class,
        entity_category=EntityCategory.DIAGNOSTIC,
    )


def create_diagnostic_zone_sensor(
    key: str,
    value_fn: Any,
    icon: str | None = None,
    device_class: SensorDeviceClass | None = None,
    state_class: SensorStateClass | None = None,
    unit: str | None = None,
    supported_zone_types: set[str] | None = None,
    supported_generations: set[str] | None = None,
    unique_id_suffix: str | None = None,
) -> TadoEntityDefinition:
    """Create a diagnostic sensor for a Tado Zone."""
    return create_zone_sensor(
        key=key,
        value_fn=value_fn,
        icon=icon,
        device_class=device_class,
        state_class=state_class,
        unit=unit,
        entity_category=EntityCategory.DIAGNOSTIC,
        supported_zone_types=supported_zone_types,
        supported_generations=supported_generations,
        unique_id_suffix=unique_id_suffix,
    )


def create_home_binary_sensor(
    key: str,
    value_fn: Any,
    icon: str | None = None,
    device_class: Any | None = None,
    entity_category: EntityCategory | None = None,
    translation_key: str | None = None,
    unique_id_suffix: str | None = None,
) -> TadoEntityDefinition:
    """Create a binary sensor for the Tado Home."""
    return _create_definition(
        key=key,
        platform="binary_sensor",
        scope="home",
        value_fn=value_fn,
        icon=icon,
        device_class=device_class,
        entity_category=entity_category,
        translation_key=translation_key,
        unique_id_suffix=unique_id_suffix,
    )


def create_zone_binary_sensor(
    key: str,
    value_fn: Any,
    icon: str | None = None,
    device_class: Any | None = None,
    entity_category: EntityCategory | None = None,
    supported_zone_types: set[str] | None = None,
    supported_generations: set[str] | None = None,
    translation_key: str | None = None,
    unique_id_suffix: str | None = None,
) -> TadoEntityDefinition:
    """Create a binary sensor for a Tado Zone."""
    return _create_definition(
        key=key,
        platform="binary_sensor",
        scope="zone",
        value_fn=value_fn,
        icon=icon,
        device_class=device_class,
        entity_category=entity_category,
        supported_zone_types=supported_zone_types,
        supported_generations=supported_generations,
        translation_key=translation_key,
        unique_id_suffix=unique_id_suffix,
    )


def create_device_binary_sensor(
    key: str,
    value_fn: Any,
    icon: str | None = None,
    device_class: Any | None = None,
    entity_category: EntityCategory | None = None,
    translation_key: str | None = None,
    unique_id_suffix: str | None = None,
) -> TadoEntityDefinition:
    """Create a binary sensor for a Tado Device."""
    return _create_definition(
        key=key,
        platform="binary_sensor",
        scope="device",
        value_fn=value_fn,
        icon=icon,
        device_class=device_class,
        entity_category=entity_category,
        translation_key=translation_key,
        unique_id_suffix=unique_id_suffix,
    )


def create_bridge_binary_sensor(
    key: str,
    value_fn: Any,
    icon: str | None = None,
    device_class: BinarySensorDeviceClass | None = None,
    entity_category: EntityCategory | None = None,
    translation_key: str | None = None,
    unique_id_suffix: str | None = None,
) -> TadoEntityDefinition:
    """Create a binary sensor for a Tado Bridge."""
    return _create_definition(
        key=key,
        platform="binary_sensor",
        scope="bridge",
        value_fn=value_fn,
        icon=icon,
        device_class=device_class,
        entity_category=entity_category,
        translation_key=translation_key,
        unique_id_suffix=unique_id_suffix,
    )


def create_home_switch(
    key: str,
    value_fn: Any,
    turn_on_fn: Any,
    turn_off_fn: Any,
    icon: str | None = None,
    entity_category: EntityCategory | None = None,
    optimistic_key: str | None = None,
    is_inverted: bool | None = None,
    unique_id_suffix: str | None = None,
    optimistic_value_map: dict[str, bool] | None = None,
) -> TadoEntityDefinition:
    """Create a switch for the Tado Home."""
    return _create_definition(
        key=key,
        platform="switch",
        scope="home",
        value_fn=value_fn,
        turn_on_fn=turn_on_fn,
        turn_off_fn=turn_off_fn,
        icon=icon,
        entity_category=entity_category,
        optimistic_key=optimistic_key,
        optimistic_scope="home",
        is_inverted=is_inverted,
        unique_id_suffix=unique_id_suffix,
        optimistic_value_map=optimistic_value_map,
    )


def create_zone_switch(
    key: str,
    value_fn: Any,
    turn_on_fn: Any,
    turn_off_fn: Any,
    icon: str | None = None,
    entity_category: EntityCategory | None = None,
    optimistic_key: str | None = None,
    supported_zone_types: set[str] | None = None,
    supported_generations: set[str] | None = None,
    is_inverted: bool | None = None,
    translation_key: str | None = None,
    unique_id_suffix: str | None = None,
    is_supported_fn: Any | None = None,
) -> TadoEntityDefinition:
    """Create a switch for a Tado Zone."""
    return _create_definition(
        key=key,
        platform="switch",
        scope="zone",
        value_fn=value_fn,
        turn_on_fn=turn_on_fn,
        turn_off_fn=turn_off_fn,
        icon=icon,
        entity_category=entity_category,
        optimistic_key=optimistic_key,
        optimistic_scope="zone",
        supported_zone_types=supported_zone_types,
        supported_generations=supported_generations,
        is_inverted=is_inverted,
        translation_key=translation_key,
        unique_id_suffix=unique_id_suffix,
        is_supported_fn=is_supported_fn,
    )


def create_device_switch(
    key: str,
    value_fn: Any,
    turn_on_fn: Any,
    turn_off_fn: Any,
    icon: str | None = None,
    entity_category: EntityCategory | None = None,
    optimistic_key: str | None = None,
    unique_id_suffix: str | None = None,
    is_supported_fn: Any | None = None,
) -> TadoEntityDefinition:
    """Create a switch for a Tado Device."""
    return _create_definition(
        key=key,
        platform="switch",
        scope="device",
        value_fn=value_fn,
        turn_on_fn=turn_on_fn,
        turn_off_fn=turn_off_fn,
        icon=icon,
        entity_category=entity_category,
        optimistic_key=optimistic_key,
        optimistic_scope="device",
        unique_id_suffix=unique_id_suffix,
        is_supported_fn=is_supported_fn,
    )


def create_device_number(
    key: str,
    value_fn: Any,
    set_fn: Any,
    min_value: float,
    max_value: float,
    step: float,
    unit: str | None = None,
    optimistic_key: str | None = None,
    entity_category: EntityCategory | None = None,
    unique_id_suffix: str | None = None,
    use_legacy_unique_id_format: bool | None = None,
    required_device_capabilities: list[str] | None = None,
    supported_generations: set[str] | None = None,
    suggested_display_precision: int | None = None,
) -> TadoEntityDefinition:
    """Create a number entity for a Tado Device."""
    return _create_definition(
        key=key,
        platform="number",
        scope="device",
        value_fn=value_fn,
        set_fn=set_fn,
        min_value=min_value,
        max_value=max_value,
        step=step,
        unit=unit,
        optimistic_key=optimistic_key,
        optimistic_scope="device",
        entity_category=entity_category,
        unique_id_suffix=unique_id_suffix,
        use_legacy_unique_id_format=use_legacy_unique_id_format,
        required_device_capabilities=required_device_capabilities,
        supported_generations=supported_generations,
        suggested_display_precision=suggested_display_precision,
    )


def create_zone_number(
    key: str,
    value_fn: Any,
    set_fn: Any,
    min_value: float | None = None,
    max_value: float | None = None,
    step: float | None = None,
    min_fn: Any | None = None,
    max_fn: Any | None = None,
    step_fn: Any | None = None,
    unit: str | None = None,
    optimistic_key: str | None = None,
    entity_category: EntityCategory | None = None,
    supported_zone_types: set[str] | None = None,
    supported_generations: set[str] | None = None,
    unique_id_suffix: str | None = None,
    use_legacy_unique_id_format: bool | None = None,
    is_supported_fn: Any | None = None,
    suggested_display_precision: int | None = None,
) -> TadoEntityDefinition:
    """Create a number entity for a Tado Zone."""
    return _create_definition(
        key=key,
        platform="number",
        scope="zone",
        value_fn=value_fn,
        set_fn=set_fn,
        min_value=min_value,
        max_value=max_value,
        step=step,
        min_fn=min_fn,
        max_fn=max_fn,
        step_fn=step_fn,
        unit=unit,
        optimistic_key=optimistic_key,
        optimistic_scope="zone",
        entity_category=entity_category,
        supported_zone_types=supported_zone_types,
        supported_generations=supported_generations,
        unique_id_suffix=unique_id_suffix,
        use_legacy_unique_id_format=use_legacy_unique_id_format,
        is_supported_fn=is_supported_fn,
        suggested_display_precision=suggested_display_precision,
    )


def create_home_button(
    key: str,
    press_fn: Any,
    icon: str | None = None,
    entity_category: EntityCategory | None = None,
    translation_key: str | None = None,
    unique_id_suffix: str | None = None,
) -> TadoEntityDefinition:
    """Create a button for the Tado Home."""
    return _create_definition(
        key=key,
        platform="button",
        scope="home",
        value_fn=lambda _: None,
        press_fn=press_fn,
        icon=icon,
        entity_category=entity_category,
        translation_key=translation_key,
        unique_id_suffix=unique_id_suffix,
    )


def create_zone_button(
    key: str,
    press_fn: Any,
    icon: str | None = None,
    entity_category: EntityCategory | None = None,
    supported_zone_types: set[str] | None = None,
    supported_generations: set[str] | None = None,
    translation_key: str | None = None,
    unique_id_suffix: str | None = None,
) -> TadoEntityDefinition:
    """Create a button for a Tado Zone."""
    return _create_definition(
        key=key,
        platform="button",
        scope="zone",
        value_fn=lambda *_: None,
        press_fn=press_fn,
        icon=icon,
        entity_category=entity_category,
        supported_zone_types=supported_zone_types,
        supported_generations=supported_generations,
        translation_key=translation_key,
        unique_id_suffix=unique_id_suffix,
    )


def create_zone_select(
    key: str,
    value_fn: Any,
    options_fn: Any,
    select_option_fn: Any,
    icon: str | None = None,
    entity_category: EntityCategory | None = None,
    optimistic_key: str | None = None,
    supported_zone_types: set[str] | None = None,
    supported_generations: set[str] | None = None,
    unique_id_suffix: str | None = None,
) -> TadoEntityDefinition:
    """Create a select entity for a Tado Zone."""
    return _create_definition(
        key=key,
        platform="select",
        scope="zone",
        value_fn=value_fn,
        options_fn=options_fn,
        select_option_fn=select_option_fn,
        icon=icon,
        entity_category=entity_category,
        optimistic_key=optimistic_key,
        optimistic_scope="zone",
        supported_zone_types=supported_zone_types or {ZONE_TYPE_AIR_CONDITIONING},
        supported_generations=supported_generations,
        unique_id_suffix=unique_id_suffix,
    )


def create_zone_sensor(
    key: str,
    value_fn: Any,
    icon: str | None = None,
    device_class: SensorDeviceClass | None = None,
    state_class: SensorStateClass | None = None,
    unit: str | None = None,
    entity_category: EntityCategory | None = None,
    supported_zone_types: set[str] | None = None,
    supported_generations: set[str] | None = None,
    unique_id_suffix: str | None = None,
) -> TadoEntityDefinition:
    """Create a sensor for a Tado Zone."""
    return _create_definition(
        key=key,
        platform="sensor",
        scope="zone",
        value_fn=value_fn,
        icon=icon,
        device_class=device_class,
        state_class=state_class,
        unit=unit,
        entity_category=entity_category,
        supported_zone_types=supported_zone_types,
        supported_generations=supported_generations,
        unique_id_suffix=unique_id_suffix,
    )


ENTITY_DEFINITIONS: Final[list[TadoEntityDefinition]] = [
    create_diagnostic_sensor(
        key="api_status",
        value_fn=lambda c: str(c.data.api_status),
        device_class=SensorDeviceClass.ENUM,
    ),
    create_diagnostic_sensor(
        key="tado_generation",
        value_fn=lambda c: ("Tado X" if c.generation == GEN_X else "Tado Classic (v3)"),
        icon="mdi:chip",
    ),
    create_diagnostic_sensor(
        key="proxy_url",
        value_fn=lambda c: (
            str(c.config_entry.data.get(CONF_API_PROXY_URL)).rstrip("/")
            if c.config_entry.data.get(CONF_API_PROXY_URL)
            else None
        ),
        icon="mdi:server-network",
    ),
    create_diagnostic_sensor(
        key="proxy_token",
        value_fn=lambda c: (
            (
                (token := c.config_entry.data.get(CONF_PROXY_TOKEN))
                and f"****{str(token)[-3:]}"
            )
            if c.config_entry.data.get(CONF_PROXY_TOKEN)
            else None
        ),
        icon="mdi:key-variant",
    ),
    create_diagnostic_sensor(
        key="api_limit",
        value_fn=lambda c: int(c.rate_limit.limit),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    create_diagnostic_sensor(
        key="api_remaining",
        value_fn=lambda c: int(c.rate_limit.remaining),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    create_diagnostic_sensor(
        key="quota_reset_last",
        value_fn=lambda c: c.reset_tracker.get_last_reset_original(),
        icon="mdi:clock-check",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    create_diagnostic_sensor(
        key="quota_reset_expected_window",
        value_fn=lambda c: str(c.reset_tracker.get_expected_window()),
        icon="mdi:clock-time-four",
    ),
    create_diagnostic_sensor(
        key="quota_reset_next",
        value_fn=lambda c: _get_next_reset_timestamp(c),
        icon="mdi:clock-alert",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    create_diagnostic_sensor(
        key="quota_reset_pattern_confidence",
        value_fn=lambda c: c.reset_tracker.get_expected_window().confidence,
        icon="mdi:chart-timeline-variant",
        device_class=SensorDeviceClass.ENUM,
    ),
    create_diagnostic_sensor(
        key="quota_reset_history_count",
        value_fn=lambda c: c.reset_tracker.history_count,
        icon="mdi:counter",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    create_diagnostic_sensor(
        key="current_zone_interval",
        value_fn=lambda c: (
            int(c.update_interval.total_seconds()) if c.update_interval else None
        ),
        icon="mdi:timer",
        unit="s",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    create_diagnostic_sensor(
        key="min_interval_configured",
        value_fn=lambda c: int(
            c.config_entry.data.get(
                CONF_MIN_AUTO_QUOTA_INTERVAL_S,
                DEFAULT_MIN_AUTO_QUOTA_INTERVAL_S,
            )
        ),
        icon="mdi:timer-cog",
        unit="s",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    create_diagnostic_sensor(
        key="min_interval_enforced",
        value_fn=lambda c: c._get_min_auto_quota_interval(),
        icon="mdi:timer-check",
        unit="s",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    create_diagnostic_sensor(
        key="reduced_polling_interval",
        value_fn=lambda c: int(
            c.config_entry.data.get(
                CONF_REDUCED_POLLING_INTERVAL, DEFAULT_REDUCED_POLLING_INTERVAL
            )
        ),
        icon="mdi:timer-pause",
        unit="s",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    create_diagnostic_sensor(
        key="debounce_time",
        value_fn=lambda c: int(
            c.config_entry.data.get(CONF_DEBOUNCE_TIME, DEFAULT_DEBOUNCE_TIME)
        ),
        icon="mdi:timer-sand",
        unit="s",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    create_diagnostic_sensor(
        key="presence_poll_interval",
        value_fn=lambda c: int(
            c.config_entry.data.get(
                CONF_PRESENCE_POLL_INTERVAL, DEFAULT_PRESENCE_POLL_INTERVAL
            )
        ),
        icon="mdi:home-account",
        unit="s",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    create_diagnostic_sensor(
        key="slow_poll_interval",
        value_fn=lambda c: int(
            c.config_entry.data.get(CONF_SLOW_POLL_INTERVAL, DEFAULT_SLOW_POLL_INTERVAL)
        ),
        icon="mdi:database-clock",
        unit="s",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    create_diagnostic_sensor(
        key="offset_poll_interval",
        value_fn=lambda c: int(
            c.config_entry.data.get(
                CONF_OFFSET_POLL_INTERVAL, DEFAULT_OFFSET_POLL_INTERVAL
            )
        ),
        icon="mdi:thermometer-lines",
        unit="s",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    create_diagnostic_sensor(
        key="auto_quota_percent",
        value_fn=lambda c: int(
            c.config_entry.data.get(
                CONF_AUTO_API_QUOTA_PERCENT, DEFAULT_AUTO_API_QUOTA_PERCENT
            )
        ),
        icon="mdi:chart-pie",
        unit="%",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    create_diagnostic_sensor(
        key="throttle_threshold",
        value_fn=lambda c: int(
            c.config_entry.data.get(CONF_THROTTLE_THRESHOLD, DEFAULT_THROTTLE_THRESHOLD)
        ),
        icon="mdi:speedometer-slow",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    create_diagnostic_sensor(
        key="jitter_percent",
        value_fn=lambda c: float(
            c.config_entry.data.get(CONF_JITTER_PERCENT, DEFAULT_JITTER_PERCENT)
        ),
        icon="mdi:chart-scatter-plot",
        unit="%",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    create_diagnostic_sensor(
        key="reduced_polling_start",
        value_fn=lambda c: str(
            c.config_entry.data.get(
                CONF_REDUCED_POLLING_START, DEFAULT_REDUCED_POLLING_START
            )
        ),
        icon="mdi:clock-start",
    ),
    create_diagnostic_sensor(
        key="reduced_polling_end",
        value_fn=lambda c: str(
            c.config_entry.data.get(
                CONF_REDUCED_POLLING_END, DEFAULT_REDUCED_POLLING_END
            )
        ),
        icon="mdi:clock-end",
    ),
    create_diagnostic_sensor(
        key="suppress_redundant_calls",
        value_fn=lambda c: bool(
            c.config_entry.data.get(
                CONF_SUPPRESS_REDUNDANT_CALLS, DEFAULT_SUPPRESS_REDUNDANT_CALLS
            )
        ),
        icon="mdi:phone-hangup",
        device_class=SensorDeviceClass.ENUM,
    ),
    create_diagnostic_sensor(
        key="suppress_redundant_buttons",
        value_fn=lambda c: bool(
            c.config_entry.data.get(
                CONF_SUPPRESS_REDUNDANT_BUTTONS, DEFAULT_SUPPRESS_REDUNDANT_BUTTONS
            )
        ),
        icon="mdi:gesture-double-tap",
        device_class=SensorDeviceClass.ENUM,
    ),
    create_zone_sensor(
        key="heating_power",
        supported_generations={"v3"},
        value_fn=lambda c, zid: v3_parsers.parse_heating_power(
            c.data.zone_states.get(str(zid)),
            c.zones_meta[zid].type if c.zones_meta.get(zid) else None,
        ),
        unit="%",
        state_class=SensorStateClass.MEASUREMENT,
        supported_zone_types={ZONE_TYPE_HEATING},
        unique_id_suffix="pwr",
    ),
    create_zone_sensor(
        key="heating_power",
        supported_generations={GEN_X},
        value_fn=lambda c, zid: tadox_parsers.parse_heating_power(
            c.data.zone_states.get(str(zid))
        ),
        unit="%",
        state_class=SensorStateClass.MEASUREMENT,
        unique_id_suffix="pwr",
    ),
    create_zone_sensor(
        key="humidity",
        value_fn=lambda c, zid: (
            float(state.sensor_data_points.humidity.percentage)
            if (state := c.data.zone_states.get(str(zid)))
            and hasattr(state, "sensor_data_points")
            and state.sensor_data_points
            and hasattr(state.sensor_data_points, "humidity")
            and state.sensor_data_points.humidity is not None
            else None
        ),
        unit="%",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.HUMIDITY,
        supported_zone_types={ZONE_TYPE_HEATING, ZONE_TYPE_AIR_CONDITIONING},
        unique_id_suffix="hum",
    ),
    create_diagnostic_zone_sensor(
        key="next_schedule_change",
        value_fn=lambda c, zid: (
            (state := c.data.zone_states.get(str(zid)))
            and (nsc := getattr(state, "next_schedule_change", None))
            and (start := getattr(nsc, "start", None))
            and dt_util.parse_datetime(start)
        )
        or None,
        device_class=SensorDeviceClass.TIMESTAMP,
        unique_id_suffix="next_sch",
    ),
    create_diagnostic_zone_sensor(
        key="next_schedule_temp",
        value_fn=lambda c, zid: v3_parsers.parse_next_schedule_temp(
            c.data.zone_states.get(str(zid))
        ),
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        unique_id_suffix="next_sch_temp",
        supported_generations={"v3"},
    ),
    create_diagnostic_zone_sensor(
        key="next_schedule_temp",
        value_fn=lambda c, zid: tadox_parsers.parse_next_schedule_temp(
            c.data.zone_states.get(str(zid))
        ),
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        unique_id_suffix="next_sch_temp",
        supported_generations={GEN_X},
    ),
    create_diagnostic_zone_sensor(
        key="next_schedule_mode",
        value_fn=lambda c, zid: v3_parsers.parse_next_schedule_mode(
            c.data.zone_states.get(str(zid))
        ),
        unique_id_suffix="next_sch_mode",
        supported_generations={"v3"},
    ),
    create_diagnostic_zone_sensor(
        key="next_schedule_mode",
        value_fn=lambda c, zid: tadox_parsers.parse_next_schedule_mode(
            c.data.zone_states.get(str(zid))
        ),
        unique_id_suffix="next_sch_mode",
        supported_generations={GEN_X},
    ),
    create_diagnostic_zone_sensor(
        key="next_time_block_start",
        value_fn=lambda c, zid: v3_parsers.parse_next_time_block_start(
            c.data.zone_states.get(str(zid))
        ),
        device_class=SensorDeviceClass.TIMESTAMP,
        unique_id_suffix="next_block_start",
        supported_generations={"v3"},
    ),
    create_diagnostic_zone_sensor(
        key="next_time_block_start",
        value_fn=lambda c, zid: tadox_parsers.parse_next_time_block_start(
            c.data.zone_states.get(str(zid))
        ),
        device_class=SensorDeviceClass.TIMESTAMP,
        unique_id_suffix="next_block_start",
        supported_generations={GEN_X},
    ),
    create_home_binary_sensor(
        key="reduced_polling_active",
        value_fn=lambda c: bool(
            c.config_entry.data.get(CONF_REDUCED_POLLING_ACTIVE, False)
        ),
        icon="mdi:sleep",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    create_home_binary_sensor(
        key="call_jitter_enabled",
        value_fn=lambda c: bool(c.config_entry.data.get(CONF_API_PROXY_URL)),
        icon="mdi:waveform",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    create_home_binary_sensor(
        key="disable_polling_when_throttled",
        value_fn=lambda c: bool(
            c.config_entry.data.get(CONF_DISABLE_POLLING_WHEN_THROTTLED, False)
        ),
        icon="mdi:stop-circle-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    create_home_binary_sensor(
        key="refresh_after_resume",
        value_fn=lambda c: bool(
            c.config_entry.data.get(
                CONF_REFRESH_AFTER_RESUME, DEFAULT_REFRESH_AFTER_RESUME
            )
        ),
        icon="mdi:refresh-auto",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    create_diagnostic_sensor(
        key="log_level",
        value_fn=lambda c: str(
            c.config_entry.data.get(CONF_LOG_LEVEL, DEFAULT_LOG_LEVEL)
        ),
        icon="mdi:math-log",
    ),
    create_device_binary_sensor(
        key="battery_state",
        value_fn=lambda c, serial: bool(
            c.devices_meta.get(serial)
            and c.devices_meta.get(serial).battery_state == "LOW"
        ),
        device_class=BinarySensorDeviceClass.BATTERY,
        unique_id_suffix="bat",
    ),
    create_device_binary_sensor(
        key="connection_state",
        value_fn=lambda c, serial: bool(
            c.devices_meta.get(serial) and c.devices_meta.get(serial).connection_state
        ),
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        unique_id_suffix="conn",
    ),
    create_bridge_binary_sensor(
        key="cloud_connection",
        value_fn=lambda c, serial: next(
            (
                bool(b.connection_state)
                for b in c.bridges
                if b.serial_no == serial and b.connection_state
            ),
            False,
        ),
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        translation_key="bridge_connection",
        unique_id_suffix="bridge",
    ),
    create_zone_binary_sensor(
        key="overlay",
        value_fn=lambda c, zid: bool(
            getattr(c.data.zone_states.get(str(zid)), "overlay_active", False)
        ),
        supported_zone_types={ZONE_TYPE_HOT_WATER},
        translation_key="overlay",
        unique_id_suffix="hw_overlay",
    ),
    create_zone_binary_sensor(
        key="power",
        value_fn=lambda c, zid: (
            (
                getattr(
                    getattr(c.data.zone_states.get(str(zid)), "setting", None),
                    "power",
                    "OFF",
                )
                == "ON"
            )
            if c.data.zone_states.get(str(zid))
            else False
        ),
        device_class=BinarySensorDeviceClass.POWER,
        supported_zone_types={ZONE_TYPE_HOT_WATER},
        translation_key="power",
        unique_id_suffix="hw_power",
    ),
    create_zone_binary_sensor(
        key="connectivity",
        value_fn=lambda c, zid: any(
            (
                c.devices_meta.get(d.serial_no)
                and c.devices_meta.get(d.serial_no).connection_state
            )
            for d in (c.zones_meta.get(zid).devices if c.zones_meta.get(zid) else [])
        ),
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        supported_zone_types={ZONE_TYPE_HOT_WATER},
        translation_key="connectivity",
        unique_id_suffix="hw_conn",
    ),
    create_device_number(
        key="temperature_offset",
        value_fn=lambda c, serial: v3_parsers.parse_temperature_offset(
            c.data.offsets.get(serial)
        ),
        set_fn=lambda c, serial, val: c.async_set_temperature_offset(serial, val),
        min_value=-10.0,
        max_value=10.0,
        step=0.1,
        unit=UnitOfTemperature.CELSIUS,
        optimistic_key="offset",
        entity_category=EntityCategory.CONFIG,
        unique_id_suffix="temperature_offset",
        use_legacy_unique_id_format=True,
        required_device_capabilities=[CAPABILITY_INSIDE_TEMP],
        supported_generations={"v3"},
    ),
    create_device_number(
        key="temperature_offset",
        value_fn=lambda c, serial: tadox_parsers.parse_temperature_offset(
            c.devices_meta.get(serial)
        ),
        set_fn=lambda c, serial, val: c.async_set_temperature_offset(serial, val),
        min_value=-10.0,
        max_value=10.0,
        step=0.1,
        unit=UnitOfTemperature.CELSIUS,
        optimistic_key="offset",
        entity_category=EntityCategory.CONFIG,
        unique_id_suffix="temperature_offset",
        use_legacy_unique_id_format=True,
        required_device_capabilities=[CAPABILITY_INSIDE_TEMP],
        supported_generations={GEN_X},
    ),
    create_zone_number(
        key="away_temperature",
        value_fn=lambda c, zid: (
            0.0 if (val := _get_away_temp(c, zid)) <= 5.0 else val
        ),
        set_fn=lambda c, zid, val: c.async_set_away_temperature(
            zid, None if val < 5.0 else val
        ),
        min_value=0,
        max_value=25.0,
        step=0.1,
        unit=UnitOfTemperature.CELSIUS,
        optimistic_key="away_temp",
        supported_zone_types={ZONE_TYPE_HEATING},
        entity_category=EntityCategory.CONFIG,
        unique_id_suffix="away_temperature",
        use_legacy_unique_id_format=True,
        is_supported_fn=lambda c, zid: c.generation
        == GEN_CLASSIC,  # v3 only - Tado X has no awayConfiguration API
    ),
    create_zone_number(
        key="target_temperature",
        value_fn=lambda c, zid: (
            float(state.setting.temperature.celsius)
            if (state := c.data.zone_states.get(str(zid)))
            and hasattr(state, "setting")
            and state.setting
            and hasattr(state.setting, "temperature")
            and state.setting.temperature is not None
            and hasattr(state.setting.temperature, "celsius")
            and state.setting.temperature.celsius is not None
            else None
        ),
        set_fn=lambda c, zid, val: (
            c.async_set_hot_water_heat(zid, val)
            if c.zones_meta.get(zid)
            and c.zones_meta.get(zid).type == ZONE_TYPE_HOT_WATER
            else c.async_set_ac_setting(zid, "temperature", str(val))
        ),
        min_fn=lambda c, zid: (
            float(caps.temperatures.celsius.min)
            if (caps := c.data_manager.capabilities_cache.get(zid))
            and caps.temperatures
            else (
                TEMP_MIN_HOT_WATER
                if c.zones_meta.get(zid)
                and c.zones_meta.get(zid).type == ZONE_TYPE_HOT_WATER
                else TEMP_MIN_AC
            )
        ),
        max_fn=lambda c, zid: (
            float(caps.temperatures.celsius.max)
            if (caps := c.data_manager.capabilities_cache.get(zid))
            and caps.temperatures
            else (
                TEMP_MAX_HOT_WATER_OVERRIDE
                if c.zones_meta.get(zid)
                and c.zones_meta.get(zid).type == ZONE_TYPE_HOT_WATER
                else TEMP_MAX_AC
            )
        ),
        step_fn=lambda c, zid: (
            float(caps.temperatures.celsius.step)
            if (caps := c.data_manager.capabilities_cache.get(zid))
            and caps.temperatures
            else 0.5
        ),
        unit=UnitOfTemperature.CELSIUS,
        optimistic_key="temperature",
        supported_zone_types={ZONE_TYPE_AIR_CONDITIONING, ZONE_TYPE_HOT_WATER},
        unique_id_suffix="target_temp",
        use_legacy_unique_id_format=True,
    ),
    create_zone_number(
        key="open_window_timeout",
        value_fn=lambda c, zid: (
            round(_get_owd_timeout(c, zid) / 60)
            if _get_owd_timeout(c, zid) >= 300
            else 0
        ),
        set_fn=lambda c, zid, val: c.async_set_open_window_detection(
            zid,
            enabled=val >= 5,
            timeout_seconds=int(val * 60) if val >= 5 else None,
        ),
        min_value=0,
        max_value=1439,
        step=1,
        unit=UnitOfTime.MINUTES,
        supported_zone_types={ZONE_TYPE_HEATING},
        entity_category=EntityCategory.CONFIG,
        unique_id_suffix="open_window_timeout",
        use_legacy_unique_id_format=True,
        is_supported_fn=lambda c, zid: (
            owd := getattr(c.zones_meta.get(zid), "open_window_detection", None)
        )
        and owd.supported,
        suggested_display_precision=0,
    ),
    create_home_button(
        key="refresh_metadata",
        press_fn=lambda c: c.async_manual_poll("metadata"),
        entity_category=EntityCategory.CONFIG,
    ),
    create_home_button(
        key="refresh_offsets",
        press_fn=lambda c: c.async_manual_poll("offsets"),
        entity_category=EntityCategory.CONFIG,
    ),
    create_home_button(
        key="refresh_away",
        press_fn=lambda c: c.async_manual_poll("away"),
        entity_category=EntityCategory.CONFIG,
    ),
    create_home_button(
        key="refresh_presence",
        press_fn=lambda c: c.async_manual_poll("presence"),
        entity_category=EntityCategory.CONFIG,
    ),
    create_home_button(
        key="full_manual_poll",
        press_fn=lambda c: c.async_manual_poll(),
        entity_category=EntityCategory.CONFIG,
    ),
    create_home_button(
        key="resume_all_schedules",
        press_fn=lambda c: c.async_resume_all_schedules(),
        unique_id_suffix="resume_all",
    ),
    create_home_button(
        key="turn_off_all_zones",
        press_fn=lambda c: c.async_turn_off_all_zones(),
        unique_id_suffix="turn_off_all",
    ),
    create_home_button(
        key="boost_all_zones",
        press_fn=lambda c: c.async_boost_all_zones(),
        unique_id_suffix="boost_all",
    ),
    create_zone_button(
        key="resume_schedule",
        press_fn=lambda c, zid: c.async_set_zone_auto(zid),
        supported_zone_types={ZONE_TYPE_HEATING},
        unique_id_suffix="resume",
    ),
    create_home_switch(
        key="away_mode",
        value_fn=lambda c: str(getattr(c.data.home_state, "presence", "")) == "AWAY",
        turn_on_fn=lambda c: c.async_set_presence_debounced("AWAY"),
        turn_off_fn=lambda c: c.async_set_presence_debounced("HOME"),
        optimistic_key="presence",
        optimistic_value_map={"AWAY": True, "HOME": False},
    ),
    create_home_switch(
        key="polling_active",
        value_fn=lambda c: c.is_polling_enabled,
        turn_on_fn=lambda c: c.async_set_polling_active(True),
        turn_off_fn=lambda c: c.async_set_polling_active(False),
        icon="mdi:sync",
        entity_category=EntityCategory.CONFIG,
    ),
    create_home_switch(
        key="reduced_polling_logic",
        value_fn=lambda c: c.is_reduced_polling_logic_enabled,
        turn_on_fn=lambda c: c.async_set_reduced_polling_logic(True),
        turn_off_fn=lambda c: c.async_set_reduced_polling_logic(False),
        icon="mdi:clock-check-outline",
        entity_category=EntityCategory.CONFIG,
    ),
    create_device_switch(
        key="child_lock",
        value_fn=lambda c, serial: bool(
            getattr(c.devices_meta.get(serial), "child_lock_enabled", False)
        ),
        turn_on_fn=lambda c, serial: c.async_set_child_lock(serial, True),
        turn_off_fn=lambda c, serial: c.async_set_child_lock(serial, False),
        optimistic_key="child_lock",
        entity_category=EntityCategory.CONFIG,
        unique_id_suffix="childlock",
        is_supported_fn=lambda c, serial: getattr(
            c.devices_meta.get(serial), "child_lock_enabled", None
        )
        is not None,
    ),
    create_zone_switch(
        key="schedule",
        value_fn=lambda c, zid: not bool(
            getattr(c.data.zone_states.get(str(zid)), "overlay_active", False)
        ),
        turn_on_fn=lambda c, zid: c.async_set_zone_auto(zid),
        turn_off_fn=lambda c, zid: c.async_set_zone_off(zid),
        optimistic_key="overlay",
        is_inverted=True,
        supported_zone_types={ZONE_TYPE_HEATING},
        translation_key="schedule",
        unique_id_suffix="sch",
    ),
    create_zone_switch(
        key="dazzle_mode",
        value_fn=lambda c, zid: bool(
            getattr(c.zones_meta.get(zid), "dazzle_enabled", False)
        ),
        turn_on_fn=lambda c, zid: c.async_set_dazzle_mode(zid, True),
        turn_off_fn=lambda c, zid: c.async_set_dazzle_mode(zid, False),
        optimistic_key="dazzle",
        entity_category=EntityCategory.CONFIG,
        translation_key="dazzle_mode",
        unique_id_suffix="dazzle",
        is_supported_fn=lambda c, zid: (
            c.generation == GEN_CLASSIC
            and getattr(c.zones_meta.get(zid), "supports_dazzle", False)
        ),  # v3 only - Tado X line_x models don't have dazzle_enabled
    ),
    create_zone_switch(
        key="early_start",
        value_fn=lambda c, zid: bool(
            getattr(c.zones_meta.get(zid), "early_start_enabled", False)
        ),
        turn_on_fn=lambda c, zid: c.async_set_early_start(zid, True),
        turn_off_fn=lambda c, zid: c.async_set_early_start(zid, False),
        optimistic_key="early_start",
        entity_category=EntityCategory.CONFIG,
        supported_zone_types={ZONE_TYPE_HEATING},
        translation_key="early_start",
        unique_id_suffix="early",
        is_supported_fn=lambda c, zid: c.generation
        == GEN_CLASSIC,  # v3 only - Tado X line_x models don't have early_start_enabled
    ),
    create_zone_select(
        key="fan_speed",
        value_fn=lambda c, zid: (
            getattr(c.data.zone_states.get(str(zid)).setting, "fan_speed", None)
            if c.data.zone_states.get(str(zid))
            and c.data.zone_states.get(str(zid)).setting
            else None
        ),
        options_fn=lambda c, zid: (
            get_ac_capabilities(c.data.capabilities.get(zid)).get("fan_speeds")
            if c.data.capabilities.get(zid)
            else []
        ),
        select_option_fn=lambda c, zid, val: c.async_set_ac_setting(
            zid, "fan_speed", val
        ),
    ),
    create_zone_select(
        key="vertical_swing",
        value_fn=lambda c, zid: c.optimistic.get_vertical_swing(zid)
        or (
            getattr(
                c.data.zone_states.get(str(zid)).setting,
                "vertical_swing",
                None,
            )
            if c.data.zone_states.get(str(zid))
            and c.data.zone_states.get(str(zid)).setting
            else None
        ),
        options_fn=lambda c, zid: (
            get_ac_capabilities(c.data.capabilities.get(zid)).get("vertical_swings")
            if c.data.capabilities.get(zid)
            else []
        ),
        select_option_fn=lambda c, zid, val: c.async_set_ac_setting(
            zid, "vertical_swing", val
        ),
        optimistic_key="vertical_swing",
    ),
    create_zone_select(
        key="horizontal_swing",
        value_fn=lambda c, zid: c.optimistic.get_horizontal_swing(zid)
        or (
            getattr(
                c.data.zone_states.get(str(zid)).setting,
                "horizontal_swing",
                None,
            )
            if c.data.zone_states.get(str(zid))
            and c.data.zone_states.get(str(zid)).setting
            else None
        ),
        options_fn=lambda c, zid: (
            get_ac_capabilities(c.data.capabilities.get(zid)).get("horizontal_swings")
            if c.data.capabilities.get(zid)
            else []
        ),
        select_option_fn=lambda c, zid, val: c.async_set_ac_setting(
            zid, "horizontal_swing", val
        ),
        optimistic_key="horizontal_swing",
    ),
]
