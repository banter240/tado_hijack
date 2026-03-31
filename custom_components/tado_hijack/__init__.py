"""Tado Hijack Integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from homeassistant.const import CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from tadoasync import TadoAuthenticationError

from .const import (
    CONF_API_PROXY_URL,
    CONF_INITIAL_POLL_DONE,
    CONF_LOG_LEVEL,
    CONF_PRESENCE_POLL_INTERVAL,
    CONF_PROXY_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_SLOW_POLL_INTERVAL,
    DEFAULT_LOG_LEVEL,
    DEFAULT_PRESENCE_POLL_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLOW_POLL_INTERVAL,
)
from .coordinator import TadoDataUpdateCoordinator
from .helpers.client import TadoHijackClient
from .helpers.logging_utils import (
    TadoRedactionFilter,
    get_redacted_logger,
    set_redacted_log_level,
)
from .lib.patches import apply_patches
from .services import async_setup_services, async_unload_services

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

apply_patches()

logging.getLogger("tadoasync").addFilter(TadoRedactionFilter())
logging.getLogger("tadoasync.tadoasync").addFilter(TadoRedactionFilter())

_LOGGER = get_redacted_logger(__name__)


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
        entry.version = 2

    if entry.version == 2:  # noqa: PLR2004
        # scan_interval fix
        new_data = {**entry.data}
        if new_data.get(CONF_SCAN_INTERVAL) == DEFAULT_SCAN_INTERVAL:
            _LOGGER.info("Migrating scan_interval to 3600s (v3)")
            new_data[CONF_SCAN_INTERVAL] = 3600
        hass.config_entries.async_update_entry(entry, data=new_data, version=3)

    if entry.version == 3:  # noqa: PLR2004
        # Introduction of Presence Polling
        new_data = {**entry.data}
        if CONF_PRESENCE_POLL_INTERVAL not in new_data:
            _LOGGER.info("Introducing presence_poll_interval (v4)")
            new_data[CONF_PRESENCE_POLL_INTERVAL] = new_data.get(
                CONF_SCAN_INTERVAL, DEFAULT_PRESENCE_POLL_INTERVAL
            )
        hass.config_entries.async_update_entry(entry, data=new_data, version=4)

    if entry.version == 4:  # noqa: PLR2004
        # Cleanup of legacy hot water entities
        _LOGGER.info("Migrating to version 5: Cleaning up legacy hot water entities")
        from homeassistant.helpers import entity_registry as er

        ent_reg = er.async_get(hass)
        entries = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
        for entity in entries:
            if "_hw_" in entity.unique_id or "_climate_hw_" in entity.unique_id:
                _LOGGER.info(
                    "Removing legacy entity %s (unique_id: %s)",
                    entity.entity_id,
                    entity.unique_id,
                )
                ent_reg.async_remove(entity.entity_id)

        hass.config_entries.async_update_entry(entry, version=5)

    if entry.version < 6:  # noqa: PLR2004
        # Reset intervals to defaults to fix unit confusion
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

    if entry.version < 7:  # noqa: PLR2004
        # Cleanup open window detection switch entities (replaced by number)
        _LOGGER.info(
            "Migrating to version 7: Cleaning up legacy open window detection switch entities"
        )
        from homeassistant.helpers import entity_registry as er

        ent_reg = er.async_get(hass)
        entries = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
        for e in entries:
            if e.domain == "switch" and (
                "open_window_detection" in e.unique_id or "owd" in e.unique_id
            ):
                _LOGGER.info(
                    "Removing legacy open window detection entity %s (unique_id: %s)",
                    e.entity_id,
                    e.unique_id,
                )
                ent_reg.async_remove(e.entity_id)

        hass.config_entries.async_update_entry(entry, version=7)

    _LOGGER.info("Migration to version %s successful", entry.version)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: TadoConfigEntry) -> bool:
    """Set up Tado Hijack from a config entry."""

    if CONF_REFRESH_TOKEN not in entry.data:
        raise ConfigEntryAuthFailed

    _LOGGER.debug("Setting up Tado connection")

    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    proxy_url = entry.data.get(CONF_API_PROXY_URL)
    proxy_token = entry.data.get(CONF_PROXY_TOKEN)

    # Use log_level from options if available, otherwise from data
    log_level = entry.options.get(CONF_LOG_LEVEL) or entry.data.get(
        CONF_LOG_LEVEL, DEFAULT_LOG_LEVEL
    )

    set_redacted_log_level(log_level)

    if proxy_url:
        _LOGGER.info("Using Tado API Proxy at %s", proxy_url)

    client = TadoHijackClient(
        refresh_token=entry.data[CONF_REFRESH_TOKEN],
        session=async_get_clientsession(hass),
        debug=(log_level.upper() == "DEBUG"),
        proxy_url=proxy_url,
        proxy_token=proxy_token,
    )

    try:
        await client.async_init()
        _LOGGER.debug(
            "Client initialized: home_id=%s, token_status=%s",
            getattr(client, "_home_id", None),
            "SET" if getattr(client, "_access_token", None) else "NOT SET",
        )
    except TadoAuthenticationError as e:
        _LOGGER.error("Authentication failed during setup: %s", e)
        raise ConfigEntryAuthFailed from e
    except Exception as e:
        if "timeout" in str(e).lower():
            _LOGGER.warning("Timeout connecting to Tado API, will retry: %s", e)
            raise ConfigEntryNotReady from e

        _LOGGER.error("Failed to initialize Tado API: %s", e)
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
        raise ConfigEntryNotReady from e

    from .const import CONF_GENERATION, GEN_CLASSIC

    gen = entry.data.get(CONF_GENERATION, GEN_CLASSIC)
    _LOGGER.info("Setting up Tado Hijack entry: %s (Generation: %s)", entry.title, gen)

    coordinator = TadoDataUpdateCoordinator(hass, entry, client, scan_interval)
    await coordinator.async_setup()
    await coordinator.async_config_entry_first_refresh()

    if (
        not entry.data.get(CONF_INITIAL_POLL_DONE)
        and coordinator.rate_limit.limit >= 1000  # noqa: PLR2004
    ):
        _LOGGER.info(
            "Performing initial full poll (Limit: %d)", coordinator.rate_limit.limit
        )
        hass.async_create_task(coordinator.async_manual_poll(silent=True))

        new_data = {**entry.data, CONF_INITIAL_POLL_DONE: True}
        hass.config_entries.async_update_entry(entry, data=new_data)

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await async_setup_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: TadoConfigEntry) -> bool:
    """Unload a config entry."""
    entry.runtime_data.shutdown()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry.runtime_data = None
        await async_unload_services(hass)

    return cast(bool, unload_ok)
