"""Config entry migration steps for Tado Hijack."""

from __future__ import annotations

from datetime import UTC
from typing import TYPE_CHECKING, Any

from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..const import (
    CONF_PRESENCE_POLL_INTERVAL,
    CONF_SLOW_POLL_INTERVAL,
    DEFAULT_PRESENCE_POLL_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLOW_POLL_INTERVAL,
)

if TYPE_CHECKING:
    from .. import TadoConfigEntry


def _v3(hass: HomeAssistant, entry: TadoConfigEntry) -> None:
    """v3: Fix scan_interval default."""
    new_data = {**entry.data}
    if new_data.get(CONF_SCAN_INTERVAL) == DEFAULT_SCAN_INTERVAL:
        new_data[CONF_SCAN_INTERVAL] = 3600
    hass.config_entries.async_update_entry(entry, data=new_data)


def _v4(hass: HomeAssistant, entry: TadoConfigEntry) -> None:
    """v4: Introduce presence_poll_interval."""
    new_data = {**entry.data}
    if CONF_PRESENCE_POLL_INTERVAL not in new_data:
        new_data[CONF_PRESENCE_POLL_INTERVAL] = new_data.get(
            CONF_SCAN_INTERVAL, DEFAULT_PRESENCE_POLL_INTERVAL
        )
    hass.config_entries.async_update_entry(entry, data=new_data)


def _v5(hass: HomeAssistant, entry: TadoConfigEntry) -> None:
    """v5: Remove legacy hot water entities."""
    from homeassistant.helpers import entity_registry as er

    ent_reg = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if "_hw_" in entity.unique_id or "_climate_hw_" in entity.unique_id:
            ent_reg.async_remove(entity.entity_id)


def _v6(hass: HomeAssistant, entry: TadoConfigEntry) -> None:
    """v6: Reset intervals to defaults to fix unit confusion."""
    new_data = {
        **entry.data,
        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,  # gitleaks:allow
        CONF_PRESENCE_POLL_INTERVAL: DEFAULT_PRESENCE_POLL_INTERVAL,  # gitleaks:allow
        CONF_SLOW_POLL_INTERVAL: DEFAULT_SLOW_POLL_INTERVAL,  # gitleaks:allow
    }
    hass.config_entries.async_update_entry(entry, data=new_data)


def _v7(hass: HomeAssistant, entry: TadoConfigEntry) -> None:
    """v7: Remove open window detection switch entities (replaced by number)."""
    from homeassistant.helpers import entity_registry as er

    ent_reg = er.async_get(hass)
    for e in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if e.domain == "switch" and (
            "open_window_detection" in e.unique_id or "owd" in e.unique_id
        ):
            ent_reg.async_remove(e.entity_id)


def _v8(hass: HomeAssistant, entry: TadoConfigEntry) -> None:
    """v8: Remove legacy away_mode switch (replaced by presence_mode select)."""
    from homeassistant.helpers import entity_registry as er

    ent_reg = er.async_get(hass)
    if entity := ent_reg.async_get_entity_id(
        "switch", "tado_hijack", f"{entry.entry_id}_away_mode"
    ):
        ent_reg.async_remove(entity)


def _v9(hass: HomeAssistant, entry: TadoConfigEntry) -> None:
    """v9: Re-run away_mode removal for installs that skipped v8 (dev.1 set VERSION=8)."""
    from homeassistant.helpers import entity_registry as er

    ent_reg = er.async_get(hass)
    if entity := ent_reg.async_get_entity_id(
        "switch", "tado_hijack", f"{entry.entry_id}_away_mode"
    ):
        ent_reg.async_remove(entity)


async def _v10(hass: HomeAssistant, entry: TadoConfigEntry) -> None:
    """v10: Migrate reset_tracker history from Berlin local time to UTC.

    Pre-v10 installs stored history in Europe/Berlin tz. After a DST transition
    the learned reset hour would shift by 1h, causing the integration to predict
    the wrong reset time. This migration converts stored entries to UTC once so
    the learned hour stays stable across DST changes.
    """
    from .reset_window_tracker import ResetWindowTracker
    from .storage import TadoStorage

    storage = TadoStorage(hass, entry.entry_id)
    tracker_data: dict[str, Any] | None = await storage.async_get("reset_tracker")
    if not tracker_data:
        return

    if tracker_data.get("data_version", 1) >= ResetWindowTracker.DATA_VERSION:
        return  # Already in UTC format

    history: list[str] = tracker_data.get("history", [])
    migrated: list[str] = []
    for iso_str in history:
        if dt := dt_util.parse_datetime(iso_str):
            migrated.append(dt.astimezone(UTC).isoformat())
        else:
            migrated.append(iso_str)

    await storage.async_update(
        "reset_tracker",
        {
            **tracker_data,
            "history": migrated,
            "data_version": ResetWindowTracker.DATA_VERSION,
        },
    )


# Ordered list of (target_version, migration_fn) pairs.
# Each step runs when entry.version < target_version.
MIGRATION_STEPS: list[tuple[int, Any]] = [
    (3, _v3),
    (4, _v4),
    (5, _v5),
    (6, _v6),
    (7, _v7),
    (8, _v8),
    (9, _v9),
    (10, _v10),
]
