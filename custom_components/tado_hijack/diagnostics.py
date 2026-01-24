"""Provides diagnostic support for the Tado Hijack integration."""

from __future__ import annotations

__version__ = "1.0.0"
__all__ = ["async_get_config_entry_diagnostics"]

import dataclasses
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    DIAGNOSTICS_REDACTED_PLACEHOLDER,
    DIAGNOSTICS_TO_REDACT_CONFIG_KEYS,
    DIAGNOSTICS_TO_REDACT_DATA_KEYS,
    DOMAIN,
)
from .coordinator import TadoDataUpdateCoordinator
from .helpers.logging_utils import get_redacted_logger

_LOGGER = get_redacted_logger(__name__)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Generate and return diagnostics for a given config entry."""
    coordinator: TadoDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    return {
        "config_entry": _get_redacted_config_entry_info(entry),
        "coordinator": _get_coordinator_diagnostics(coordinator),
    }


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
    coordinator_diag: dict[str, Any] = {
        "last_update_success": coordinator.last_update_success,
        "api_status": coordinator.data.api_status,
        "is_throttled": coordinator.rate_limit.is_throttled,
        "rate_limit": {
            "limit": coordinator.rate_limit.limit,
            "remaining": coordinator.rate_limit.remaining,
            "is_throttled": coordinator.rate_limit.is_throttled,
        },
    }

    if coordinator.data:
        # Redact sensitive data from API response
        coordinator_diag["data"] = async_redact_data(
            dataclasses.asdict(coordinator.data), DIAGNOSTICS_TO_REDACT_DATA_KEYS
        )

    # Clean metadata
    if coordinator.zones_meta:
        coordinator_diag["zones_meta"] = async_redact_data(
            {str(k): v for k, v in coordinator.zones_meta.items()},
            DIAGNOSTICS_TO_REDACT_DATA_KEYS,
        )

    if coordinator.devices_meta:
        coordinator_diag["devices_meta"] = async_redact_data(
            coordinator.devices_meta, DIAGNOSTICS_TO_REDACT_DATA_KEYS
        )

    return coordinator_diag
