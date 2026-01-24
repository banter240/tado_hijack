"""Config flow for Tado Hijack."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Mapping
from typing import Any, cast

from tadoasync import Tado, TadoError
import voluptuous as vol
from yarl import URL

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    CONF_API_PROXY_URL,
    CONF_AUTO_API_QUOTA_PERCENT,
    CONF_DEBOUNCE_TIME,
    CONF_DEBUG_LOGGING,
    CONF_DISABLE_POLLING_WHEN_THROTTLED,
    CONF_OFFSET_POLL_INTERVAL,
    CONF_REFRESH_TOKEN,
    CONF_SLOW_POLL_INTERVAL,
    CONF_THROTTLE_THRESHOLD,
    DEFAULT_AUTO_API_QUOTA_PERCENT,
    DEFAULT_DEBOUNCE_TIME,
    DEFAULT_OFFSET_POLL_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLOW_POLL_INTERVAL,
    DEFAULT_THROTTLE_THRESHOLD,
    DOMAIN,
    MIN_DEBOUNCE_TIME,
    MIN_OFFSET_POLL_INTERVAL,
    MIN_SCAN_INTERVAL,
    MIN_SLOW_POLL_INTERVAL,
)
from .helpers.patch import apply_patch

# Apply monkey-patches to tadoasync library
apply_patch()

_LOGGER = logging.getLogger(__name__)


class TadoHijackConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Handle a config flow for Tado Hijack."""

    VERSION = 3
    login_task: asyncio.Task | None = None
    refresh_token: str | None = None
    tado: Tado | None = None

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauth."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauth."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")

        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if self.tado is None:
            try:
                self.tado = Tado(
                    debug=False, session=async_get_clientsession(self.hass)
                )
                await self.tado.async_init()
            except TadoError:
                _LOGGER.exception("Error initiating Tado")
                return self.async_abort(reason="cannot_connect")

            tado_device_url = self.tado.device_verification_url
            if tado_device_url is None:
                return self.async_abort(reason="cannot_connect")
            user_code = URL(tado_device_url).query["user_code"]

        async def _wait_for_login() -> None:
            if self.tado is None:
                raise CannotConnect("Tado client not initialized")
            try:
                await self.tado.device_activation()
            except Exception as ex:
                raise CannotConnect from ex

            if self.tado.device_activation_status != "COMPLETED":
                raise CannotConnect

        if self.login_task is None:
            self.login_task = self.hass.async_create_task(_wait_for_login())

        if self.login_task.done():
            if self.login_task.exception():
                return self.async_show_progress_done(next_step_id="timeout")
            self.refresh_token = self.tado.refresh_token
            return self.async_show_progress_done(next_step_id="finish_login")

        return self.async_show_progress(
            step_id="user",
            progress_action="wait_for_device",
            description_placeholders={
                "url": str(tado_device_url),
                "code": str(user_code),
            },
            progress_task=self.login_task,
        )

    async def async_step_finish_login(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Finish the login process."""
        if self.tado is None:
            return self.async_abort(reason="cannot_connect")
        tado_me = await self.tado.get_me()

        if tado_me.homes is None or len(tado_me.homes) == 0:
            return self.async_abort(reason="no_homes")

        home = tado_me.homes[0]
        cast(dict[str, Any], self.context)["home_name"] = home.name

        if self.source != config_entries.SOURCE_REAUTH:
            unique_id = str(home.id)
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            return await self.async_step_config()

        return self.async_update_reload_and_abort(
            self._get_reauth_entry(),
            data={
                **self._get_reauth_entry().data,
                CONF_REFRESH_TOKEN: self.refresh_token,
            },
        )

    async def async_step_config(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the configuration of the polling intervals."""
        if user_input is not None:
            return self.async_create_entry(
                title=f"Tado {self.context.get('home_name', 'Hijack')}",
                data={
                    CONF_REFRESH_TOKEN: self.refresh_token,
                    CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                    CONF_SLOW_POLL_INTERVAL: user_input[CONF_SLOW_POLL_INTERVAL],
                    CONF_OFFSET_POLL_INTERVAL: user_input.get(
                        CONF_OFFSET_POLL_INTERVAL, DEFAULT_OFFSET_POLL_INTERVAL
                    ),
                    CONF_THROTTLE_THRESHOLD: user_input.get(
                        CONF_THROTTLE_THRESHOLD, DEFAULT_THROTTLE_THRESHOLD
                    ),
                    CONF_DISABLE_POLLING_WHEN_THROTTLED: user_input.get(
                        CONF_DISABLE_POLLING_WHEN_THROTTLED, False
                    ),
                    CONF_DEBOUNCE_TIME: user_input.get(
                        CONF_DEBOUNCE_TIME, DEFAULT_DEBOUNCE_TIME
                    ),
                    CONF_AUTO_API_QUOTA_PERCENT: user_input.get(
                        CONF_AUTO_API_QUOTA_PERCENT, DEFAULT_AUTO_API_QUOTA_PERCENT
                    ),
                    CONF_API_PROXY_URL: user_input.get(CONF_API_PROXY_URL),
                    CONF_DEBUG_LOGGING: user_input.get(CONF_DEBUG_LOGGING, False),
                },
            )

        return self.async_show_form(
            step_id="config",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)),
                    vol.Optional(
                        CONF_AUTO_API_QUOTA_PERCENT,
                        default=DEFAULT_AUTO_API_QUOTA_PERCENT,
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0, max=100, step=1, mode=NumberSelectorMode.BOX
                        )
                    ),
                    vol.Required(
                        CONF_SLOW_POLL_INTERVAL, default=DEFAULT_SLOW_POLL_INTERVAL
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SLOW_POLL_INTERVAL)),
                    vol.Optional(
                        CONF_OFFSET_POLL_INTERVAL, default=DEFAULT_OFFSET_POLL_INTERVAL
                    ): vol.All(
                        vol.Coerce(int), vol.Range(min=MIN_OFFSET_POLL_INTERVAL)
                    ),
                    vol.Optional(
                        CONF_DEBOUNCE_TIME, default=DEFAULT_DEBOUNCE_TIME
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_DEBOUNCE_TIME)),
                    vol.Optional(
                        CONF_THROTTLE_THRESHOLD, default=DEFAULT_THROTTLE_THRESHOLD
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0, max=5000, step=1, mode=NumberSelectorMode.BOX
                        )
                    ),
                    vol.Optional(
                        CONF_DISABLE_POLLING_WHEN_THROTTLED, default=False
                    ): bool,
                    vol.Optional(CONF_API_PROXY_URL): vol.Any(None, str),
                    vol.Optional(CONF_DEBUG_LOGGING, default=False): bool,
                }
            ),
        )

    async def async_step_timeout(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle issues that need transition away from progress step."""
        if user_input is None:
            return self.async_show_form(step_id="timeout")
        if self.login_task and not self.login_task.done():
            self.login_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.login_task
        self.login_task = None
        self.tado = None
        return await self.async_step_user()

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> TadoHijackOptionsFlowHandler:
        """Get the options flow."""
        return TadoHijackOptionsFlowHandler()


class TadoHijackOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for Tado Hijack."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Initialize the options flow."""
        if user_input:
            # Update entry.data directly (not options) so coordinator sees changes
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={**self.config_entry.data, **user_input},
            )
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(data={})

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.data.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)),
                    vol.Optional(
                        CONF_AUTO_API_QUOTA_PERCENT,
                        default=self.config_entry.data.get(
                            CONF_AUTO_API_QUOTA_PERCENT, DEFAULT_AUTO_API_QUOTA_PERCENT
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0, max=100, step=1, mode=NumberSelectorMode.BOX
                        )
                    ),
                    vol.Optional(
                        CONF_SLOW_POLL_INTERVAL,
                        default=self.config_entry.data.get(
                            CONF_SLOW_POLL_INTERVAL, DEFAULT_SLOW_POLL_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SLOW_POLL_INTERVAL)),
                    vol.Optional(
                        CONF_OFFSET_POLL_INTERVAL,
                        default=self.config_entry.data.get(
                            CONF_OFFSET_POLL_INTERVAL, DEFAULT_OFFSET_POLL_INTERVAL
                        ),
                    ): vol.All(
                        vol.Coerce(int), vol.Range(min=MIN_OFFSET_POLL_INTERVAL)
                    ),
                    vol.Optional(
                        CONF_DEBOUNCE_TIME,
                        default=self.config_entry.data.get(
                            CONF_DEBOUNCE_TIME, DEFAULT_DEBOUNCE_TIME
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_DEBOUNCE_TIME)),
                    vol.Optional(
                        CONF_THROTTLE_THRESHOLD,
                        default=self.config_entry.data.get(
                            CONF_THROTTLE_THRESHOLD, DEFAULT_THROTTLE_THRESHOLD
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0, max=5000, step=1, mode=NumberSelectorMode.BOX
                        )
                    ),
                    vol.Optional(
                        CONF_DISABLE_POLLING_WHEN_THROTTLED,
                        default=self.config_entry.data.get(
                            CONF_DISABLE_POLLING_WHEN_THROTTLED, False
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_API_PROXY_URL,
                        default=self.config_entry.data.get(CONF_API_PROXY_URL, ""),
                    ): vol.Any(None, str),
                    vol.Optional(
                        CONF_DEBUG_LOGGING,
                        default=self.config_entry.data.get(CONF_DEBUG_LOGGING, False),
                    ): bool,
                }
            ),
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""
