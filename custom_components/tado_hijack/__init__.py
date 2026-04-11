"""Tado Hijack Integration."""

from __future__ import annotations

import inspect
import logging
from typing import TYPE_CHECKING, cast

from homeassistant.const import CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from tadoasync import TadoAuthenticationError

from .const import (
    API_QUOTA_STANDARD,
    CONF_API_PROXY_URL,
    CONF_INITIAL_POLL_DONE,
    CONF_LOG_LEVEL,
    CONF_LOG_VERSION_PREFIX,
    CONF_PROXY_TOKEN,
    CONF_REFRESH_TOKEN,
    DEFAULT_LOG_LEVEL,
    DEFAULT_LOG_VERSION_PREFIX,
    DEFAULT_SCAN_INTERVAL,
    HTTP_BAD_REQUEST,
    HTTP_UNAUTHORIZED,
)
from .coordinator import TadoDataUpdateCoordinator
from .helpers.client import TadoHijackClient
from .helpers.logging_utils import (
    INTEGRATION_VERSION,
    TadoRedactionFilter,
    get_redacted_logger,
    set_redacted_log_level,
    set_version_prefix_enabled,
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
    from .helpers.migration import MIGRATION_STEPS

    _LOGGER.debug("Migrating from version %s", entry.version)

    for target_version, step in MIGRATION_STEPS:
        if entry.version < target_version:
            _LOGGER.info("Migrating to version %s", target_version)
            if inspect.iscoroutinefunction(step):
                await step(hass, entry)
            else:
                step(hass, entry)
            hass.config_entries.async_update_entry(entry, version=target_version)

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
    log_version_prefix = entry.options.get(
        CONF_LOG_VERSION_PREFIX,
        entry.data.get(CONF_LOG_VERSION_PREFIX, DEFAULT_LOG_VERSION_PREFIX),
    )

    set_redacted_log_level(log_level)
    set_version_prefix_enabled(bool(log_version_prefix))

    from .const import CONF_GENERATION, GEN_CLASSIC

    _LOGGER.info(
        "Tado Hijack %s starting (Generation: %s)",
        INTEGRATION_VERSION,
        entry.data.get(CONF_GENERATION, GEN_CLASSIC),
    )

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
            or str(HTTP_BAD_REQUEST) in error_str
            or str(HTTP_UNAUTHORIZED) in error_str
            or "unauthorized" in error_str
            or ("invalid" in error_str and "token" in error_str)
        ):
            _LOGGER.warning(
                "Token likely invalid (HTTP %s/%s or auth error), triggering reauth",
                HTTP_BAD_REQUEST,
                HTTP_UNAUTHORIZED,
            )
            raise ConfigEntryAuthFailed from e
        raise ConfigEntryNotReady from e

    coordinator = TadoDataUpdateCoordinator(hass, entry, client, scan_interval)
    await coordinator.async_setup()
    await coordinator.async_config_entry_first_refresh()

    if (
        not entry.data.get(CONF_INITIAL_POLL_DONE)
        and coordinator.rate_limit.limit >= API_QUOTA_STANDARD
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
