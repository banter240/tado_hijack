"""Manages authentication token synchronization."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant

from ..const import CONF_REFRESH_TOKEN
from .logging_utils import get_redacted_logger

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from tadoasync import Tado

_LOGGER = get_redacted_logger(__name__)


class AuthManager:
    """Manages token rotation and config entry updates."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: Tado) -> None:
        """Initialize AuthManager."""
        self.hass = hass
        self.entry = entry
        self.client = client
        self._current_refresh_token: str | None = entry.data.get(CONF_REFRESH_TOKEN)

    def check_and_update_token(self) -> None:
        """Check if token rotated and update config entry if necessary."""
        new_token = self.client.refresh_token
        if new_token and new_token != self._current_refresh_token:
            _LOGGER.debug("AuthManager: Syncing rotated refresh token")
            self._current_refresh_token = new_token
            self.hass.config_entries.async_update_entry(
                self.entry,
                data={**self.entry.data, CONF_REFRESH_TOKEN: new_token},
            )
