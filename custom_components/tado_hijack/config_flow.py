"""Config flow for Tado Hijack."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any, TYPE_CHECKING

from tadoasync import Tado, TadoError
import voluptuous as vol
from yarl import URL

from homeassistant import config_entries, data_entry_flow
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TimeSelector,
)

from .const import (
    CONF_API_PROXY_URL,
    CONF_PROXY_TOKEN,
    CONF_AUTO_API_QUOTA_PERCENT,
    CONF_CALL_JITTER_ENABLED,
    CONF_LOG_LEVEL,
    CONF_DEBOUNCE_TIME,
    CONF_DISABLE_POLLING_WHEN_THROTTLED,
    CONF_JITTER_PERCENT,
    CONF_MIN_AUTO_QUOTA_INTERVAL_S,
    CONF_OFFSET_POLL_INTERVAL,
    CONF_PRESENCE_POLL_INTERVAL,
    CONF_REDUCED_POLLING_ACTIVE,
    CONF_REDUCED_POLLING_END,
    CONF_REDUCED_POLLING_INTERVAL,
    CONF_REDUCED_POLLING_START,
    CONF_REFRESH_AFTER_RESUME,
    CONF_REFRESH_TOKEN,
    CONF_SLOW_POLL_INTERVAL,
    CONF_THROTTLE_THRESHOLD,
    DEFAULT_AUTO_API_QUOTA_PERCENT,
    DEFAULT_DEBOUNCE_TIME,
    DEFAULT_JITTER_PERCENT,
    DEFAULT_LOG_LEVEL,
    DEFAULT_MIN_AUTO_QUOTA_INTERVAL_S,
    DEFAULT_OFFSET_POLL_INTERVAL,
    DEFAULT_REDUCED_POLLING_END,
    DEFAULT_REDUCED_POLLING_INTERVAL,
    DEFAULT_REDUCED_POLLING_START,
    DEFAULT_PRESENCE_POLL_INTERVAL,
    DEFAULT_REFRESH_AFTER_RESUME,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLOW_POLL_INTERVAL,
    DEFAULT_THROTTLE_THRESHOLD,
    DOMAIN,
    LOG_LEVELS,
    MAX_API_QUOTA,
    MAX_AUTO_QUOTA_INTERVAL_S,
    MIN_AUTO_QUOTA_INTERVAL_S,
    MIN_DEBOUNCE_TIME,
    MIN_OFFSET_POLL_INTERVAL,
    MIN_SCAN_INTERVAL,
    MIN_SLOW_POLL_INTERVAL,
)
from .helpers.logging_utils import get_redacted_logger
from .helpers.patch import apply_patch

apply_patch()

_LOGGER = get_redacted_logger(__name__)


class TadoHijackCommonFlow:
    """Mixin for shared logic between ConfigFlow and OptionsFlow."""

    _data: dict[str, Any]
    hass: Any

    if TYPE_CHECKING:

        def async_show_form(
            self,
            *,
            step_id: str,
            data_schema: vol.Schema | None = None,
            errors: dict[str, str] | None = None,
            description_placeholders: dict[str, str] | None = None,
            last_step: bool | None = None,
            title: str | None = None,
        ) -> ConfigFlowResult:
            """Stub for Mypy."""
            ...

    def _get_current_data(self, key: str, default: Any) -> Any:
        """Get current value from config entry or existing data buffer."""
        if key in self._data:
            return self._data[key]
        if hasattr(self, "config_entry") and self.config_entry:
            return self.config_entry.data.get(key, default)
        return default

    def _flatten_section_data(self, user_input: dict[str, Any]) -> dict[str, Any]:
        """Flatten nested section data into flat configuration.

        Sections like 'general_polling', 'api_quota', etc. are unpacked
        into top-level config keys.
        """
        processed_input = {}

        # Flatten general_polling section
        if "general_polling" in user_input:
            polling = user_input["general_polling"]
            for key in [
                CONF_SCAN_INTERVAL,
                CONF_PRESENCE_POLL_INTERVAL,
                CONF_SLOW_POLL_INTERVAL,
                CONF_OFFSET_POLL_INTERVAL,
            ]:
                if key in polling:
                    processed_input[key] = polling[key]

        # Flatten api_quota section
        if "api_quota" in user_input:
            quota = user_input["api_quota"]
            for key in [
                CONF_AUTO_API_QUOTA_PERCENT,
                CONF_THROTTLE_THRESHOLD,
                CONF_DISABLE_POLLING_WHEN_THROTTLED,
                CONF_REFRESH_AFTER_RESUME,
            ]:
                if key in quota:
                    processed_input[key] = quota[key]

        # Flatten reduced_polling section
        if "reduced_polling" in user_input:
            schedule = user_input["reduced_polling"]
            for key in [
                CONF_REDUCED_POLLING_ACTIVE,
                CONF_REDUCED_POLLING_START,
                CONF_REDUCED_POLLING_END,
                CONF_REDUCED_POLLING_INTERVAL,
            ]:
                if key in schedule:
                    processed_input[key] = schedule[key]

        # Flatten advanced section
        if "advanced" in user_input:
            advanced = user_input["advanced"]
            for key in [
                CONF_API_PROXY_URL,
                CONF_PROXY_TOKEN,
                CONF_CALL_JITTER_ENABLED,
                CONF_JITTER_PERCENT,
                CONF_DEBOUNCE_TIME,
                CONF_MIN_AUTO_QUOTA_INTERVAL_S,
                CONF_LOG_LEVEL,
            ]:
                if key in advanced:
                    processed_input[key] = advanced[key]

        return processed_input

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle single-page configuration with collapsible sections."""
        if user_input is None:
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema(
                    {
                        # === General Polling Intervals ===
                        vol.Required("general_polling"): data_entry_flow.section(
                            vol.Schema(
                                {
                                    vol.Required(
                                        CONF_SCAN_INTERVAL,
                                        default=self._get_current_data(
                                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                                        ),
                                    ): vol.All(
                                        vol.Coerce(int),
                                        vol.Range(min=MIN_SCAN_INTERVAL),
                                    ),
                                    vol.Required(
                                        CONF_PRESENCE_POLL_INTERVAL,
                                        default=self._get_current_data(
                                            CONF_PRESENCE_POLL_INTERVAL,
                                            DEFAULT_PRESENCE_POLL_INTERVAL,
                                        ),
                                    ): vol.All(
                                        vol.Coerce(int),
                                        vol.Range(min=MIN_SCAN_INTERVAL),
                                    ),
                                    vol.Required(
                                        CONF_SLOW_POLL_INTERVAL,
                                        default=self._get_current_data(
                                            CONF_SLOW_POLL_INTERVAL,
                                            DEFAULT_SLOW_POLL_INTERVAL,
                                        ),
                                    ): vol.All(
                                        vol.Coerce(int),
                                        vol.Range(min=MIN_SLOW_POLL_INTERVAL),
                                    ),
                                    vol.Optional(
                                        CONF_OFFSET_POLL_INTERVAL,
                                        default=self._get_current_data(
                                            CONF_OFFSET_POLL_INTERVAL,
                                            DEFAULT_OFFSET_POLL_INTERVAL,
                                        ),
                                    ): vol.All(
                                        vol.Coerce(int),
                                        vol.Range(min=MIN_OFFSET_POLL_INTERVAL),
                                    ),
                                }
                            ),
                            {"collapsed": True},
                        ),
                        # === API Quota & Safety ===
                        vol.Required("api_quota"): data_entry_flow.section(
                            vol.Schema(
                                {
                                    vol.Optional(
                                        CONF_AUTO_API_QUOTA_PERCENT,
                                        default=self._get_current_data(
                                            CONF_AUTO_API_QUOTA_PERCENT,
                                            DEFAULT_AUTO_API_QUOTA_PERCENT,
                                        ),
                                    ): NumberSelector(
                                        NumberSelectorConfig(
                                            min=0,
                                            max=100,
                                            step=1,
                                            mode=NumberSelectorMode.BOX,
                                        )
                                    ),
                                    vol.Optional(
                                        CONF_THROTTLE_THRESHOLD,
                                        default=self._get_current_data(
                                            CONF_THROTTLE_THRESHOLD,
                                            DEFAULT_THROTTLE_THRESHOLD,
                                        ),
                                    ): NumberSelector(
                                        NumberSelectorConfig(
                                            min=0,
                                            max=MAX_API_QUOTA,
                                            step=1,
                                            mode=NumberSelectorMode.BOX,
                                        )
                                    ),
                                    vol.Optional(
                                        CONF_DISABLE_POLLING_WHEN_THROTTLED,
                                        default=self._get_current_data(
                                            CONF_DISABLE_POLLING_WHEN_THROTTLED, False
                                        ),
                                    ): BooleanSelector(),
                                    vol.Optional(
                                        CONF_REFRESH_AFTER_RESUME,
                                        default=self._get_current_data(
                                            CONF_REFRESH_AFTER_RESUME,
                                            DEFAULT_REFRESH_AFTER_RESUME,
                                        ),
                                    ): BooleanSelector(),
                                }
                            ),
                            {"collapsed": True},
                        ),
                        # === Reduced Polling Schedule ===
                        vol.Required("reduced_polling"): data_entry_flow.section(
                            vol.Schema(
                                {
                                    vol.Optional(
                                        CONF_REDUCED_POLLING_ACTIVE,
                                        default=self._get_current_data(
                                            CONF_REDUCED_POLLING_ACTIVE, False
                                        ),
                                    ): BooleanSelector(),
                                    vol.Optional(
                                        CONF_REDUCED_POLLING_START,
                                        default=self._get_current_data(
                                            CONF_REDUCED_POLLING_START,
                                            DEFAULT_REDUCED_POLLING_START,
                                        ),
                                    ): TimeSelector(),
                                    vol.Optional(
                                        CONF_REDUCED_POLLING_END,
                                        default=self._get_current_data(
                                            CONF_REDUCED_POLLING_END,
                                            DEFAULT_REDUCED_POLLING_END,
                                        ),
                                    ): TimeSelector(),
                                    vol.Optional(
                                        CONF_REDUCED_POLLING_INTERVAL,
                                        default=self._get_current_data(
                                            CONF_REDUCED_POLLING_INTERVAL,
                                            DEFAULT_REDUCED_POLLING_INTERVAL,
                                        ),
                                    ): vol.All(vol.Coerce(int), vol.Range(min=0)),
                                }
                            ),
                            {"collapsed": True},
                        ),
                        # === Advanced & Debug ===
                        vol.Required("advanced"): data_entry_flow.section(
                            vol.Schema(
                                {
                                    vol.Optional(
                                        CONF_API_PROXY_URL,
                                        description={
                                            "suggested_value": self._get_current_data(
                                                CONF_API_PROXY_URL, ""
                                            )
                                        },
                                    ): vol.Any(None, str),
                                    vol.Optional(
                                        CONF_PROXY_TOKEN,
                                        description={
                                            "suggested_value": self._get_current_data(
                                                CONF_PROXY_TOKEN, ""
                                            )
                                        },
                                    ): vol.Any(None, str),
                                    vol.Optional(
                                        CONF_CALL_JITTER_ENABLED,
                                        default=self._get_current_data(
                                            CONF_CALL_JITTER_ENABLED, False
                                        ),
                                    ): BooleanSelector(),
                                    vol.Optional(
                                        CONF_JITTER_PERCENT,
                                        default=self._get_current_data(
                                            CONF_JITTER_PERCENT, DEFAULT_JITTER_PERCENT
                                        ),
                                    ): NumberSelector(
                                        NumberSelectorConfig(
                                            min=0,
                                            max=50,
                                            step=0.1,
                                            mode=NumberSelectorMode.BOX,
                                        )
                                    ),
                                    vol.Optional(
                                        CONF_DEBOUNCE_TIME,
                                        default=self._get_current_data(
                                            CONF_DEBOUNCE_TIME, DEFAULT_DEBOUNCE_TIME
                                        ),
                                    ): vol.All(
                                        vol.Coerce(int),
                                        vol.Range(min=MIN_DEBOUNCE_TIME),
                                    ),
                                    vol.Optional(
                                        CONF_MIN_AUTO_QUOTA_INTERVAL_S,
                                        default=self._get_current_data(
                                            CONF_MIN_AUTO_QUOTA_INTERVAL_S,
                                            DEFAULT_MIN_AUTO_QUOTA_INTERVAL_S,
                                        ),
                                    ): vol.All(
                                        vol.Coerce(int),
                                        vol.Range(
                                            min=MIN_AUTO_QUOTA_INTERVAL_S,
                                            max=MAX_AUTO_QUOTA_INTERVAL_S,
                                        ),
                                    ),
                                    vol.Required(
                                        CONF_LOG_LEVEL,
                                        default=self._get_current_data(
                                            CONF_LOG_LEVEL, DEFAULT_LOG_LEVEL
                                        ),
                                    ): SelectSelector(
                                        SelectSelectorConfig(
                                            options=LOG_LEVELS,
                                            mode=SelectSelectorMode.DROPDOWN,
                                        )
                                    ),
                                }
                            ),
                            {"collapsed": True},
                        ),
                    }
                ),
            )
        # Flatten nested section data
        processed_input = self._flatten_section_data(user_input)

        # Handle proxy URL cleanup
        proxy_url = processed_input.get(CONF_API_PROXY_URL, "")
        if not proxy_url or not str(proxy_url).strip():
            processed_input[CONF_API_PROXY_URL] = None

        proxy_token = processed_input.get(CONF_PROXY_TOKEN, "")
        if not proxy_token or not str(proxy_token).strip():
            processed_input[CONF_PROXY_TOKEN] = None

        self._data.update(processed_input)
        return await self._async_finish_flow()

    async def _async_finish_flow(self) -> ConfigFlowResult:
        """Finalize the flow."""
        raise NotImplementedError


class TadoHijackConfigFlow(
    TadoHijackCommonFlow, config_entries.ConfigFlow, domain=DOMAIN
):  # type: ignore[call-arg]
    """Handle a config flow for Tado Hijack."""

    VERSION = 7
    login_task: asyncio.Task | None = None
    refresh_token: str | None = None
    tado: Tado | None = None

    def __init__(self) -> None:
        """Initialize config flow."""
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start the configuration (Auth-Last)."""
        return await self.async_step_init()

    async def _async_finish_flow(self) -> ConfigFlowResult:
        """Finalize wizard and decide if OAuth is needed."""
        api_proxy_url = self._data.get(CONF_API_PROXY_URL)
        if not api_proxy_url:
            self._data[CONF_API_PROXY_URL] = None

        api_proxy_token = self._data.get(CONF_PROXY_TOKEN)
        if not api_proxy_token:
            self._data[CONF_PROXY_TOKEN] = None

        if api_proxy_url:
            _LOGGER.info("Proxy detected, skipping Tado Cloud Auth")
            self.refresh_token = "proxy_managed"
            await self.async_set_unique_id(f"proxy_{api_proxy_url}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="Tado Hijack (Proxy)",
                data={CONF_REFRESH_TOKEN: self.refresh_token, **self._data},
            )

        return await self.async_step_tado_auth()

    async def async_step_tado_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Authenticate with Tado Cloud."""
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
                raise CannotConnect
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
            step_id="tado_auth",
            progress_action="wait_for_device",
            description_placeholders={
                "url": str(tado_device_url),
                "code": str(user_code),
            },
            progress_task=self.login_task,
        )

    async def async_step_finish_login(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Complete the OAuth flow and create entry."""
        if self.tado is None:
            return self.async_abort(reason="cannot_connect")
        tado_me = await self.tado.get_me()
        if not tado_me.homes:
            return self.async_abort(reason="no_homes")

        home = tado_me.homes[0]
        await self.async_set_unique_id(str(home.id))

        if self.source == config_entries.SOURCE_REAUTH:
            reauth_entry = self._get_reauth_entry()
            return self.async_update_reload_and_abort(
                reauth_entry,
                data={**reauth_entry.data, CONF_REFRESH_TOKEN: self.refresh_token},
            )

        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=f"Tado {home.name}",
            data={CONF_REFRESH_TOKEN: self.refresh_token, **self._data},
        )

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
        return await self.async_step_tado_auth()

    async def async_step_timeout(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle issue cleanup."""
        if user_input is None:
            return self.async_show_form(step_id="timeout")
        self.login_task = None
        self.tado = None
        return await self.async_step_tado_auth()

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> TadoHijackOptionsFlowHandler:
        """Get the options flow."""
        return TadoHijackOptionsFlowHandler()


class TadoHijackOptionsFlowHandler(TadoHijackCommonFlow, config_entries.OptionsFlow):
    """Handle options for Tado Hijack."""

    def __init__(self) -> None:
        """Initialize options flow."""
        self._data: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start the options wizard."""
        return await super().async_step_init(user_input)

    async def _async_finish_flow(self) -> ConfigFlowResult:
        """Update the config entry."""
        new_data = dict(self.config_entry.data)
        new_data |= self._data

        if (
            not new_data.get(CONF_API_PROXY_URL)
            or not str(new_data.get(CONF_API_PROXY_URL, "")).strip()
        ):
            new_data[CONF_API_PROXY_URL] = None

        if (
            not new_data.get(CONF_PROXY_TOKEN)
            or not str(new_data.get(CONF_PROXY_TOKEN, "")).strip()
        ):
            new_data[CONF_PROXY_TOKEN] = None

        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data=new_data,
        )
        await self.hass.config_entries.async_reload(self.config_entry.entry_id)
        return self.async_create_entry(data={})


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""
