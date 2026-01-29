"""Tado Hijack Integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from homeassistant.const import CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from tadoasync import TadoAuthenticationError

from .const import (
    CONF_API_PROXY_URL,
    CONF_DEBUG_LOGGING,
    CONF_PRESENCE_POLL_INTERVAL,
    CONF_REFRESH_TOKEN,
    CONF_SLOW_POLL_INTERVAL,
    DEFAULT_PRESENCE_POLL_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLOW_POLL_INTERVAL,
)
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
    Platform.NUMBER,
    Platform.SELECT,
    Platform.CLIMATE,
    Platform.WATER_HEATER,
]


async def async_migrate_entry(hass: HomeAssistant, entry: TadoConfigEntry) -> bool:
    """Migrate old entry."""
    _LOGGER.debug("Migrating from version %s", entry.version)

    if entry.version == 1:
        # Migration to version 2 (Initial refactor)
        entry.version = 2

    if entry.version == 2:
        # Migration to version 3 (Legacy scan_interval fix)
        new_data = {**entry.data}
        if new_data.get(CONF_SCAN_INTERVAL) == 1800:
            _LOGGER.info("Migrating scan_interval to 3600s (v3)")
            new_data[CONF_SCAN_INTERVAL] = 3600
        hass.config_entries.async_update_entry(entry, data=new_data, version=3)

    if entry.version == 3:
        # Migration to version 4 (Introduction of Presence Polling)
        new_data = {**entry.data}
        if CONF_PRESENCE_POLL_INTERVAL not in new_data:
            _LOGGER.info("Introducing presence_poll_interval (v4)")
            new_data[CONF_PRESENCE_POLL_INTERVAL] = new_data.get(
                CONF_SCAN_INTERVAL, DEFAULT_PRESENCE_POLL_INTERVAL
            )
        hass.config_entries.async_update_entry(entry, data=new_data, version=4)

    if entry.version == 4:
        # Migration to version 5 (Cleanup of legacy hot water entities)
        _LOGGER.info("Migrating to version 5: Cleaning up legacy hot water entities")
        from homeassistant.helpers import entity_registry as er

        ent_reg = er.async_get(hass)
        entries = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
        for entity in entries:
            # Match any entity with legacy HW suffixes to prevent name collisions
            if "_hw_" in entity.unique_id or "_climate_hw_" in entity.unique_id:
                _LOGGER.info(
                    "Removing legacy entity %s (unique_id: %s)",
                    entity.entity_id,
                    entity.unique_id,
                )
                ent_reg.async_remove(entity.entity_id)

        hass.config_entries.async_update_entry(entry, version=5)

    if entry.version < 6:
        # Migration to version 6 (Reset intervals to defaults to fix unit confusion)
        _LOGGER.info("Migrating to version 6: Resetting intervals to defaults")
        new_data = {
            **entry.data,
            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,  # gitleaks:allow
        }
        new_data[CONF_PRESENCE_POLL_INTERVAL] = (
            DEFAULT_PRESENCE_POLL_INTERVAL  # gitleaks:allow
        )
        new_data[CONF_SLOW_POLL_INTERVAL] = DEFAULT_SLOW_POLL_INTERVAL  # gitleaks:allow
        hass.config_entries.async_update_entry(entry, data=new_data, version=6)

    _LOGGER.info("Migration to version %s successful", entry.version)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: TadoConfigEntry) -> bool:
    """Set up Tado Hijack from a config entry."""

    if CONF_REFRESH_TOKEN not in entry.data:
        raise ConfigEntryAuthFailed

    _LOGGER.debug("Setting up Tado connection")

    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    proxy_url = entry.data.get(CONF_API_PROXY_URL)
    debug_logging = entry.data.get(CONF_DEBUG_LOGGING, False)

    if debug_logging:
        _LOGGER.setLevel(logging.DEBUG)
        logging.getLogger("tadoasync").setLevel(logging.DEBUG)
        _LOGGER.debug("Debug logging enabled for Tado Hijack")

    if proxy_url:
        _LOGGER.info("Using Tado API Proxy at %s", proxy_url)

    client = TadoHijackClient(
        refresh_token=entry.data[CONF_REFRESH_TOKEN],
        session=async_get_clientsession(hass),
        debug=debug_logging,
        proxy_url=proxy_url,
    )

    try:
        await client.async_init()
    except TadoAuthenticationError as e:
        _LOGGER.error("Authentication failed during setup: %s", e)
        raise ConfigEntryAuthFailed from e
    except Exception as e:
        _LOGGER.error("Failed to initialize Tado API: %s", e)
        # Check for HTTP 400/401 status codes or authentication-related errors
        error_str = str(e).lower()
        if (
            "bad request" in error_str
            or "400" in error_str
            or "401" in error_str
            or "unauthorized" in error_str
            or ("invalid" in error_str and "token" in error_str)
        ):
            _LOGGER.warning(
                "Token likely invalid (HTTP 400/401 or auth error), triggering reauth"
            )
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
    entry.runtime_data.shutdown()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await async_unload_services(hass)

    return cast(bool, unload_ok)
