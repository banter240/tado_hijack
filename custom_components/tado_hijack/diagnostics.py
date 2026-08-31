"""Provides diagnostic support for the Tado Hijack integration."""

from __future__ import annotations

import hashlib
import re
import time
from typing import Any, cast

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import (
    DIAGNOSTICS_REDACTED_PLACEHOLDER,
    DIAGNOSTICS_TO_REDACT_CONFIG_KEYS,
    DIAGNOSTICS_TO_REDACT_DATA_KEYS,
    SECONDS_PER_DAY,
)
from .coordinator import TadoDataUpdateCoordinator
from .helpers.logging_utils import redact

__all__ = ["async_get_config_entry_diagnostics"]

_HARD_REDACT_KEYS = frozenset(
    {
        "homeid",
        "home_id",
        "userid",
        "user_id",
        "token",
        "refresh_token",
        "access_token",
        "proxy_token",
        "secret",
        "password",
        "email",
        "username",
        "latitude",
        "longitude",
        "auth",
        "authorization",
        "api_key",
        "serialno",
        "shortserialno",
        "macaddress",
    }
)
_HARD_REDACT_SUFFIXES = ("_token", "_secret", "_password", "_api_key")
_ENTITY_ID_DOMAINS = (
    "sensor",
    "binary_sensor",
    "switch",
    "number",
    "select",
    "button",
    "climate",
    "water_heater",
    "device_tracker",
    "person",
)
_KEEP_NAME_PREFIXES = ("Zone ", "Unknown")


def _is_entity_id_key(key: str) -> bool:
    """Return True if key looks like a Home Assistant entity_id."""
    return "." in key and key.startswith(_ENTITY_ID_DOMAINS)


def _should_hard_redact_key(key: str) -> bool:
    """Return True for secret field names (exact match or known suffix)."""
    if _is_entity_id_key(key):
        return False

    k_lower = key.lower()
    if k_lower in _HARD_REDACT_KEYS:
        return True
    return any(k_lower.endswith(suffix) for suffix in _HARD_REDACT_SUFFIXES)


def _mask_string(text: str) -> str:
    """Mask serial numbers and sensitive patterns in strings."""
    text = redact(text)

    email_pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
    text = re.sub(email_pattern, "**EMAIL-REDACTED**", text)

    if (
        "." in text
        and all(x not in text for x in ("T", "Z", "+"))
        and text.startswith(_ENTITY_ID_DOMAINS)
    ):
        parts = text.split(".")
        domain = parts[0]
        name_hash = hashlib.shake_128(parts[1].encode()).hexdigest(2)
        text = f"{domain}.entity_{name_hash}"

    return text


def _redact_pii(data: Any, coordinator: TadoDataUpdateCoordinator | None = None) -> Any:
    """Recursively redact serial numbers and sensitive names."""
    if isinstance(data, dict):
        new_data = {}
        for k, v in data.items():
            k_str = str(k)
            k_lower = k_str.lower()
            new_key = _mask_string(k_str)

            if _should_hard_redact_key(k_str):
                new_data[new_key] = "**REDACTED**"
            elif any(
                x in k_lower
                for x in ("name", "title", "assigned_to", "firstname", "lastname")
            ) and isinstance(v, str):
                new_data[new_key] = (
                    v
                    if any(v.startswith(p) for p in _KEEP_NAME_PREFIXES)
                    else "Anonymized Name"
                )
            else:
                new_data[new_key] = _redact_pii(v, coordinator)
        return new_data

    if isinstance(data, list):
        return [_redact_pii(item, coordinator) for item in data]

    return _mask_string(data) if isinstance(data, str) else data


def _serialize_tado_data(data: Any) -> dict[str, Any]:
    """Return counts and keys for coordinator TadoData (no nested API models)."""
    rate = getattr(data, "rate_limit", None)
    devices = getattr(data, "devices", None) or {}
    offsets = getattr(data, "offsets", None) or {}
    zone_states = getattr(data, "zone_states", None) or {}
    zones = getattr(data, "zones", None) or {}
    capabilities = getattr(data, "capabilities", None) or {}
    away = getattr(data, "away_config", None) or {}

    return {
        "api_status": getattr(data, "api_status", "unknown"),
        "home_state_present": getattr(data, "home_state", None) is not None,
        "zone_states_count": len(zone_states),
        "zone_state_keys": sorted(str(k) for k in zone_states),
        "zones_count": len(zones),
        "zone_ids": sorted(zones),
        "devices_count": len(devices),
        "device_serials": sorted(str(s) for s in devices),
        "capabilities_count": len(capabilities),
        "capability_zone_ids": sorted(capabilities),
        "offsets_count": len(offsets),
        "offset_device_serials": sorted(str(s) for s in offsets),
        "away_config_count": len(away),
        "away_zone_ids": sorted(away),
        "rate_limit": {
            "limit": getattr(rate, "limit", None),
            "remaining": getattr(rate, "remaining", None),
        },
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Generate and return diagnostics for a given config entry."""
    coordinator: TadoDataUpdateCoordinator | None = getattr(entry, "runtime_data", None)

    diag_data: dict[str, Any] = {
        "config_entry": _get_redacted_config_entry_info(entry),
    }

    if not coordinator:
        diag_data["error"] = "Coordinator not found in config entry runtime_data"
        return diag_data

    # Main components
    diag_data["coordinator"] = _get_coordinator_diagnostics(coordinator)
    diag_data["quota_status"] = _get_quota_diagnostics(coordinator)
    diag_data["internal_state"] = _get_internal_state_diagnostics(hass, coordinator)

    diag_data["entity_mappings"] = _get_entity_mappings(
        hass, entry.entry_id, coordinator
    )

    # AUTO: Collect all diagnostic sensors automatically
    diag_data["diagnostic_sensors_auto"] = _get_all_diagnostic_sensors(
        hass, entry.entry_id
    )

    # Redact everything for PII
    redacted = _redact_pii(diag_data, coordinator)

    # Final HA internal redaction for secrets
    return cast(
        dict[str, Any], async_redact_data(redacted, DIAGNOSTICS_TO_REDACT_DATA_KEYS)
    )


def _get_redacted_config_entry_info(entry: ConfigEntry) -> dict[str, Any]:
    """Return redacted configuration entry information."""
    return {
        "title": entry.title,
        "entry_id": entry.entry_id,
        "unique_id": DIAGNOSTICS_REDACTED_PLACEHOLDER if entry.unique_id else None,
        "data": async_redact_data(entry.data, DIAGNOSTICS_TO_REDACT_CONFIG_KEYS),
        "options": async_redact_data(entry.options, DIAGNOSTICS_TO_REDACT_CONFIG_KEYS),
    }


def _get_coordinator_diagnostics(
    coordinator: TadoDataUpdateCoordinator,
) -> dict[str, Any]:
    """Return diagnostic information about the DataUpdateCoordinator."""
    data = coordinator.data

    coordinator_diag: dict[str, Any] = {
        "last_update_success": coordinator.last_update_success,
        "api_status": getattr(data, "api_status", "unknown"),
        "rate_limit": {
            "limit": getattr(coordinator.rate_limit, "limit", 0),
            "remaining": getattr(coordinator.rate_limit, "remaining", 0),
            "is_throttled": getattr(coordinator.rate_limit, "is_throttled", False),
            "threshold": getattr(coordinator.rate_limit, "throttle_threshold", 0),
        },
    }

    if data:
        try:
            coordinator_diag["data"] = _serialize_tado_data(data)
        except Exception as e:
            coordinator_diag["data_error"] = f"Failed to serialize TadoData: {e}"

    # Metadata summaries (Fallback if JIT data is empty)
    coordinator_diag["metadata_cache"] = {
        "zones": list(coordinator.zones_meta.keys()),
        "devices": list(coordinator.devices_meta.keys()),
    }
    coordinator_diag["zones_count"] = len(coordinator.zones_meta)
    coordinator_diag["devices_count"] = len(coordinator.devices_meta)

    return coordinator_diag


def _get_quota_diagnostics(coordinator: TadoDataUpdateCoordinator) -> dict[str, Any]:
    """Return calculated quota diagnostics (sensors are auto-collected elsewhere).

    This function only returns CALCULATED values that don't exist as sensors.
    All sensor values (reset window, history, etc.) are automatically collected
    via _get_all_diagnostic_sensors().
    """
    dm = coordinator.data_manager
    res_total, res_breakdown = dm.estimate_daily_reserved_cost()

    # Timing calculations
    now_dt = dt_util.now()
    next_reset = coordinator.reset_tracker.get_next_reset_time()
    seconds_until_reset = int((next_reset - now_dt).total_seconds())
    seconds_since_reset = SECONDS_PER_DAY - seconds_until_reset
    progress_done = max(0.0, min(1.0, seconds_since_reset / SECONDS_PER_DAY))

    # Usage calculations (not available as sensors)
    limit = getattr(coordinator.rate_limit, "limit", 0)
    remaining = getattr(coordinator.rate_limit, "remaining", 0)
    polling_calls_today = coordinator._polling_calls_today
    actual_used = max(0, limit - remaining)
    expected_bg = res_total * progress_done
    user_calls = max(0, actual_used - polling_calls_today - expected_bg)
    threshold = getattr(coordinator.rate_limit, "throttle_threshold", 0)

    return {
        "polling_interval": str(coordinator.update_interval),
        "seconds_until_reset": seconds_until_reset,
        "day_progress": round(progress_done, 4),
        "reserved_24h": res_total,
        "reserved_breakdown": res_breakdown,
        "estimated_usage": {
            "polling_so_far": polling_calls_today,
            "user_so_far": int(user_calls),
            "user_excess": int(max(0, user_calls - threshold)),
        },
    }


def _get_device_linking_diagnostics(
    hass: HomeAssistant,
    coordinator: TadoDataUpdateCoordinator,
) -> dict[str, Any]:
    """Report local device linking status per cloud serial."""
    from .helpers.device_linker import (
        get_climate_entity_id,
        get_linked_device_identifiers,
    )
    from .helpers.discovery import yield_devices

    devices: dict[str, Any] = {}
    for device, zone_id in yield_devices(coordinator):
        serial = device.serial_no
        linked_ids = get_linked_device_identifiers(hass, serial, coordinator.generation)
        climate_id = get_climate_entity_id(hass, serial)
        devices[_mask_string(str(serial))] = {
            "device_type": getattr(device, "device_type", None),
            "zone_id": zone_id,
            "linked": bool(linked_ids),
            "local_identifier_domains": sorted({dom for dom, _ in linked_ids}),
            "climate_entity": (
                _mask_string(climate_id) if climate_id is not None else None
            ),
        }

    climate_map = getattr(coordinator, "_climate_to_zone", {})
    climate_to_zone = {
        _mask_string(str(entity_id)): zone_id
        for entity_id, zone_id in climate_map.items()
    }

    linked_count = sum(bool(d["linked"]) for d in devices.values())
    return {
        "generation": coordinator.generation,
        "full_cloud_mode": bool(coordinator.full_cloud_mode),
        "linked_count": linked_count,
        "device_count": len(devices),
        "climate_map_size": len(climate_map),
        "climate_to_zone": climate_to_zone,
        "devices": devices,
    }


def _get_internal_state_diagnostics(
    hass: HomeAssistant,
    coordinator: TadoDataUpdateCoordinator,
) -> dict[str, Any]:
    """Return internal component status."""
    dm = coordinator.data_manager
    am = coordinator.api_manager
    opt = coordinator.optimistic

    now = time.monotonic()

    return {
        "optimistic": {
            "zones_count": len(opt._store.get("zone", {})),
            "devices_count": len(opt._store.get("device", {})),
            "presence_global": opt.get_presence(),
        },
        "api_manager": {
            "queue_size": am._api_queue.qsize(),
            "pending_actions_keys": list(am._action_queue.keys()),
            "worker_active": am._worker_task is not None and not am._worker_task.done(),
        },
        "data_manager": {
            "last_zones_poll_age": round(now - dm._last_zones_poll, 1),
            "last_presence_poll_age": round(now - dm._last_presence_poll, 1),
            "last_slow_poll_age": round(now - dm._last_slow_poll, 1),
            "cache_status": {
                "zones_dirty": dm._zones_invalidated_at > dm._last_zones_poll,
                "presence_dirty": dm._presence_invalidated_at > dm._last_presence_poll,
                "offsets_dirty": dm._offset_invalidated_at > dm._last_offset_poll,
                "away_dirty": dm._away_invalidated_at > dm._last_away_poll,
            },
        },
        "device_linking": _get_device_linking_diagnostics(hass, coordinator),
    }


def _get_all_diagnostic_sensors(hass: HomeAssistant, entry_id: str) -> dict[str, Any]:
    """Automatically collect all diagnostic sensors for this integration.

    Instead of manually adding each sensor, this function introspects
    the entity registry and collects all entities marked as DIAGNOSTIC.
    """
    ent_reg = er.async_get(hass)
    diagnostic_entities: dict[str, Any] = {}

    for entity_entry in er.async_entries_for_config_entry(ent_reg, entry_id):
        if entity_entry.entity_category != er.EntityCategory.DIAGNOSTIC:
            continue

        if state := hass.states.get(entity_entry.entity_id):
            diagnostic_entities[entity_entry.entity_id] = {
                "state": state.state,
                "attributes": dict(state.attributes),
                "device_class": entity_entry.device_class,
                "unit_of_measurement": entity_entry.unit_of_measurement,
            }

    return diagnostic_entities


def _get_entity_mappings(
    hass: HomeAssistant, entry_id: str, coordinator: TadoDataUpdateCoordinator
) -> dict[str, Any]:
    """Analyze and return Hijack entity to Tado zone mappings."""
    ent_reg = er.async_get(hass)
    mappings = {}

    for entity_entry in er.async_entries_for_config_entry(ent_reg, entry_id):
        zone_id = coordinator.entity_resolver.parse_unique_id(entity_entry.unique_id)
        zone_info = "Unknown"
        if zone_id is not None:
            zone_info = f"Zone {zone_id}"

        mappings[entity_entry.entity_id] = {
            "unique_id": entity_entry.unique_id,
            "resolved_zone_id": zone_id,
            "assigned_to": zone_info,
            "disabled": entity_entry.disabled_by is not None,
        }

    return mappings
