"""Provides diagnostic support for the Tado Hijack integration."""

from __future__ import annotations

import dataclasses
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
    API_RESET_HOUR_END,
    API_RESET_HOUR_START,
    DIAGNOSTICS_REDACTED_PLACEHOLDER,
    DIAGNOSTICS_TO_REDACT_CONFIG_KEYS,
    DIAGNOSTICS_TO_REDACT_DATA_KEYS,
    SECONDS_PER_DAY,
)
from .coordinator import TadoDataUpdateCoordinator
from .helpers.quota_math import get_next_reset_time

__all__ = ["async_get_config_entry_diagnostics"]


def _mask_string(text: str) -> str:
    """Mask serial numbers and sensitive patterns in strings."""
    # 1. Pattern for Tado serials: VA/RU/IB/WR + 10 digits
    serial_pattern = r"(?i)(va|ru|ib|wr|id|sn|zo|home|user)\d{4,}"
    text = re.sub(serial_pattern, r"\1********", text)

    # 2. Pattern for Emails
    email_pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
    text = re.sub(email_pattern, "**EMAIL-REDACTED**", text)

    # 3. Pattern for entity names in keys (Home Assistant Domains)
    if "." in text and all(x not in text for x in ("T", "Z", "+")):
        domains = (
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
        if text.startswith(domains):
            parts = text.split(".")
            domain = parts[0]
            # Create a unique short hash from the original name part
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

            # 1. Mask the Key itself
            new_key = _mask_string(k_str)

            # 2. Redact technical values based on key name
            if any(
                x in k_lower
                for x in {
                    "homeid",
                    "userid",
                    "token",
                    "secret",
                    "auth",
                    "key",
                    "password",
                    "email",
                    "username",
                    "latitude",
                    "longitude",
                }
            ):
                # Hard redaction for these specific fields
                new_data[new_key] = "**REDACTED**"
            elif any(
                x in k_lower
                for x in {"name", "title", "assigned_to", "firstname", "lastname"}
            ) and isinstance(v, str):
                # If it's already a technical ID (like "Zone 30"), keep it
                new_data[new_key] = v if v.startswith("Zone ") else "Anonymized Name"
            else:
                new_data[new_key] = _redact_pii(v, coordinator)
        return new_data

    if isinstance(data, list):
        return [_redact_pii(item, coordinator) for item in data]

    return _mask_string(data) if isinstance(data, str) else data


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
    diag_data["internal_state"] = _get_internal_state_diagnostics(coordinator)

    # Analyze actual Hijack entity mappings for this entry
    diag_data["entity_mappings"] = _get_entity_mappings(
        hass, entry.entry_id, coordinator
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
        # Convert dataclass to dict safely
        try:
            coordinator_diag["data"] = dataclasses.asdict(data)
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
    """Return diagnostic information about the auto API quota system."""
    dm = coordinator.data_manager
    res_total, res_breakdown = dm.estimate_daily_reserved_cost()

    # Timing (Aware)
    now_dt = dt_util.now()
    next_reset = get_next_reset_time()
    seconds_until_reset = int((next_reset - now_dt).total_seconds())
    seconds_since_reset = SECONDS_PER_DAY - seconds_until_reset
    progress_done = max(0.0, min(1.0, seconds_since_reset / SECONDS_PER_DAY))

    # Adaptive Calculation
    limit = getattr(coordinator.rate_limit, "limit", 0)
    remaining = getattr(coordinator.rate_limit, "remaining", 0)
    expected_poll_usage = res_total * progress_done
    actual_used = max(0, limit - remaining)
    user_calls = max(0, actual_used - expected_poll_usage)
    threshold = getattr(coordinator.rate_limit, "throttle_threshold", 0)

    return {
        "polling_interval": str(coordinator.update_interval),
        "quota_reset_window_berlin": f"{API_RESET_HOUR_START:02d}:00-{API_RESET_HOUR_END:02d}:00",
        "seconds_until_reset": seconds_until_reset,
        "day_progress": round(progress_done, 4),
        "reserved_24h": res_total,
        "reserved_breakdown": res_breakdown,
        "estimated_usage": {
            "api_limit": limit,
            "api_remaining": remaining,
            "polling_so_far": int(expected_poll_usage),
            "user_so_far": int(user_calls),
            "user_excess": int(max(0, user_calls - threshold)),
        },
        "auto_quota_config": {
            "percent": getattr(coordinator, "_auto_api_quota_percent", 0),
            "threshold": threshold,
        },
    }


def _get_internal_state_diagnostics(
    coordinator: TadoDataUpdateCoordinator,
) -> dict[str, Any]:
    """Return internal component status."""
    dm = coordinator.data_manager
    am = coordinator.api_manager
    opt = coordinator.optimistic

    now = time.monotonic()
    home_kit_map = getattr(coordinator, "_climate_to_zone", {})

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
        "home_kit": {
            "active": len(home_kit_map) > 0,
            "mapping": home_kit_map,
        },
    }


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
