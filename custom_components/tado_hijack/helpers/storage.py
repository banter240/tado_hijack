"""Persistent storage helper for Tado Hijack.

Provides a generic interface to save and load integration data
across Home Assistant reboots using the official Store API.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from ..const import DOMAIN

STORAGE_VERSION = 1


class TadoStorage:
    """Manages persistent storage for the integration."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the storage helper.

        Args:
            hass: Home Assistant instance
            entry_id: Config entry ID to keep storage separate per instance

        """
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}_{entry_id}_cache"
        )
        self._data: dict[str, Any] | None = None

    async def async_load(self) -> dict[str, Any]:
        """Load data from storage."""
        if self._data is None:
            data = await self._store.async_load()
            self._data = data if data is not None else {}
        return self._data

    async def async_save(self, data: dict[str, Any]) -> None:
        """Save data to storage."""
        self._data = data
        await self._store.async_save(self._data)

    async def async_update(self, key: str, value: Any) -> None:
        """Update a specific key in the storage."""
        data = await self.async_load()
        data[key] = value
        await self.async_save(data)

    async def async_get(self, key: str, default: Any = None) -> Any:
        """Get a specific key from the storage."""
        data = await self.async_load()
        return data.get(key, default)
