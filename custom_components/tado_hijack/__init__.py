"""Tado Hijack Integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from homeassistant.const import CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from tadoasync import TadoAuthenticationError

from .const import CONF_REFRESH_TOKEN, DEFAULT_SCAN_INTERVAL
from .coordinator import TadoDataUpdateCoordinator
from .helpers.client import TadoHijackClient
from .helpers.logging_utils import TadoRedactionFilter
from .helpers.patch import apply_patch
from .services import async_setup_services, async_unload_services

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

apply_patch()

logging.getLogger("tadoasync").addFilter(TadoRedactionFilter())
logging.getLogger("tadoasync.tadoasync").addFilter(TadoRedactionFilter())

_LOGGER = logging.getLogger(__name__)

__version__ = "1.0.0"

type TadoConfigEntry = ConfigEntry[TadoDataUpdateCoordinator]

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
]


async def async_setup_entry(hass: HomeAssistant, entry: TadoConfigEntry) -> bool:
    """Set up Tado Hijack from a config entry."""

    if CONF_REFRESH_TOKEN not in entry.data:
        raise ConfigEntryAuthFailed

    _LOGGER.debug("Setting up Tado connection")

    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    client = TadoHijackClient(
        refresh_token=entry.data[CONF_REFRESH_TOKEN],
        session=async_get_clientsession(hass),
        debug=True,
    )

    try:
        await client.async_init()
    except TadoAuthenticationError as e:
        _LOGGER.error("Authentication failed during setup: %s", e)
        raise ConfigEntryAuthFailed from e
    except Exception as e:
        _LOGGER.error("Failed to initialize Tado API: %s", e)
        if "Bad Request" in str(e) or "400" in str(e):
            _LOGGER.warning("Token likely invalid (400 Bad Request), triggering reauth")
            raise ConfigEntryAuthFailed from e
        return False

    coordinator = TadoDataUpdateCoordinator(hass, entry, client, scan_interval)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await async_setup_services(hass, coordinator)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: TadoConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await async_unload_services(hass)

    return cast(bool, unload_ok)
