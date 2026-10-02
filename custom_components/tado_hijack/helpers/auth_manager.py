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


def persist_refresh_token(
    hass: HomeAssistant, entry: ConfigEntry, token: str | None
) -> None:
    if not token or token == entry.data.get(CONF_REFRESH_TOKEN):
        return
    _LOGGER.debug("Storing rotated refresh token")
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONF_REFRESH_TOKEN: token},
    )


class AuthManager:
    """Saves the client refresh token when a poll finishes."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: Tado) -> None:
        """Initialize AuthManager."""
        self.hass = hass
        self.entry = entry
        self.client = client

    def check_and_update_token(self) -> None:
        persist_refresh_token(self.hass, self.entry, self.client.refresh_token)
