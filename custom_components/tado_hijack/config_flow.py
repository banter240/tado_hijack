"""Config flow for Tado Hijack."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant import config_entries, data_entry_flow
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TimeSelector,
)
from tadoasync import Tado, TadoError
from yarl import URL

from .const import (
    CONF_API_PROXY_URL,
    CONF_AUTO_API_QUOTA_PERCENT,
    CONF_CALL_JITTER_ENABLED,
    CONF_DEBOUNCE_TIME,
    CONF_DISABLE_POLLING_WHEN_THROTTLED,
    CONF_FEATURE_DEW_POINT,
    CONF_FEATURE_MOLD_DETECTION,
    CONF_FETCH_EXTENDED_DATA,
    CONF_FULL_CLOUD_MODE,
    CONF_GENERATION,
    CONF_JITTER_PERCENT,
    CONF_LOG_LEVEL,
    CONF_MIN_AUTO_QUOTA_INTERVAL_S,
    CONF_OFFSET_POLL_INTERVAL,
    CONF_OUTDOOR_WEATHER_ENTITY,
    CONF_PRESENCE_POLL_INTERVAL,
    CONF_PROXY_TOKEN,
    CONF_QUOTA_SAFETY_RESERVE,
    CONF_REDUCED_POLLING_ACTIVE,
    CONF_REDUCED_POLLING_END,
    CONF_REDUCED_POLLING_INTERVAL,
    CONF_REDUCED_POLLING_START,
    CONF_REFRESH_AFTER_RESUME,
    CONF_REFRESH_TOKEN,
    CONF_SLOW_POLL_INTERVAL,
    CONF_SUPPRESS_REDUNDANT_BUTTONS,
    CONF_SUPPRESS_REDUNDANT_CALLS,
    CONF_THROTTLE_THRESHOLD,
    CONF_VENTILATION_AH_THRESHOLD,
    DEFAULT_AUTO_API_QUOTA_PERCENT,
    DEFAULT_DEBOUNCE_TIME,
    DEFAULT_FEATURE_DEW_POINT,
    DEFAULT_FEATURE_MOLD_DETECTION,
    DEFAULT_JITTER_PERCENT,
    DEFAULT_LOG_LEVEL,
    DEFAULT_MIN_AUTO_QUOTA_INTERVAL_S,
    DEFAULT_OFFSET_POLL_INTERVAL,
    DEFAULT_PRESENCE_POLL_INTERVAL,
    DEFAULT_QUOTA_SAFETY_RESERVE,
    DEFAULT_REDUCED_POLLING_END,
    DEFAULT_REDUCED_POLLING_INTERVAL,
    DEFAULT_REDUCED_POLLING_START,
    DEFAULT_REFRESH_AFTER_RESUME,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLOW_POLL_INTERVAL,
    DEFAULT_SUPPRESS_REDUNDANT_BUTTONS,
    DEFAULT_SUPPRESS_REDUNDANT_CALLS,
    DEFAULT_THROTTLE_THRESHOLD,
    DEFAULT_VENTILATION_AH_THRESHOLD,
    DOMAIN,
    GEN_CLASSIC,
    GEN_X,
    LOG_LEVELS,
    MAX_API_QUOTA,
    MAX_AUTO_QUOTA_INTERVAL_S,
    MAX_QUOTA_SAFETY_RESERVE,
    MIN_AUTO_QUOTA_INTERVAL_S,
    MIN_DEBOUNCE_TIME,
    MIN_OFFSET_POLL_INTERVAL,
    MIN_QUOTA_SAFETY_RESERVE,
    MIN_SCAN_INTERVAL,
    MIN_SLOW_POLL_INTERVAL,
)
from .helpers.logging_utils import get_redacted_logger
from .lib.patches import apply_patches

apply_patches()

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
            """Show the form to the user."""
            ...

        def async_create_entry(
            self,
            *,
            title: str,
            data: Mapping[str, Any],
            description: str | None = None,
            description_placeholders: dict[str, str] | None = None,
            options: Mapping[str, Any] | None = None,
        ) -> ConfigFlowResult:
            """Finish config flow and create a config entry."""
            ...

        def async_abort(
            self, *, reason: str, description_placeholders: dict[str, str] | None = None
        ) -> ConfigFlowResult:
            """Abort the config flow."""
            ...

    def _get_current_data(self, key: str, default: Any) -> Any:
        """Get current value from config entry or existing data buffer."""
        if key in self._data:
            return self._data[key]
        if hasattr(self, "config_entry") and self.config_entry:
            return self.config_entry.data.get(key, default)
        return default

    def _flatten_section_data(self, user_input: dict[str, Any]) -> dict[str, Any]:
        """Flatten nested section data into flat configuration."""
        processed_input = {}

        sections = {
            "general_polling": [
                CONF_SCAN_INTERVAL,
                CONF_PRESENCE_POLL_INTERVAL,
                CONF_SLOW_POLL_INTERVAL,
                CONF_OFFSET_POLL_INTERVAL,
            ],
            "api_quota": [
                CONF_AUTO_API_QUOTA_PERCENT,
                CONF_THROTTLE_THRESHOLD,
                CONF_DISABLE_POLLING_WHEN_THROTTLED,
                CONF_REFRESH_AFTER_RESUME,
                CONF_SUPPRESS_REDUNDANT_CALLS,
                CONF_SUPPRESS_REDUNDANT_BUTTONS,
                CONF_MIN_AUTO_QUOTA_INTERVAL_S,
                CONF_QUOTA_SAFETY_RESERVE,
            ],
            "reduced_polling": [
                CONF_REDUCED_POLLING_ACTIVE,
                CONF_REDUCED_POLLING_START,
                CONF_REDUCED_POLLING_END,
                CONF_REDUCED_POLLING_INTERVAL,
            ],
            "advanced": [
                CONF_API_PROXY_URL,
                CONF_PROXY_TOKEN,
                CONF_CALL_JITTER_ENABLED,
                CONF_JITTER_PERCENT,
                CONF_DEBOUNCE_TIME,
                CONF_LOG_LEVEL,
            ],
            "features": [
                CONF_FEATURE_DEW_POINT,
                CONF_FEATURE_MOLD_DETECTION,
                CONF_OUTDOOR_WEATHER_ENTITY,
                CONF_VENTILATION_AH_THRESHOLD,
            ],
        }

        for section_name, keys in sections.items():
            if section_name in user_input:
                section_data = user_input[section_name]
                for key in keys:
                    if key in section_data:
                        val = section_data[key]
                        # Handle empty string to None conversion for optional fields
                        if key == CONF_OUTDOOR_WEATHER_ENTITY:
                            val = val or None
                        processed_input[key] = val

        return processed_input

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle single-page configuration with collapsible sections."""
        if user_input is None:
            _schema: dict[Any, Any] = {
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
                            vol.Optional(
                                CONF_SUPPRESS_REDUNDANT_CALLS,
                                default=self._get_current_data(
                                    CONF_SUPPRESS_REDUNDANT_CALLS,
                                    DEFAULT_SUPPRESS_REDUNDANT_CALLS,
                                ),
                            ): BooleanSelector(),
                            vol.Optional(
                                CONF_SUPPRESS_REDUNDANT_BUTTONS,
                                default=self._get_current_data(
                                    CONF_SUPPRESS_REDUNDANT_BUTTONS,
                                    DEFAULT_SUPPRESS_REDUNDANT_BUTTONS,
                                ),
                            ): BooleanSelector(),
                            vol.Optional(
                                CONF_MIN_AUTO_QUOTA_INTERVAL_S,
                                default=self._get_current_data(
                                    CONF_MIN_AUTO_QUOTA_INTERVAL_S,
                                    DEFAULT_MIN_AUTO_QUOTA_INTERVAL_S,
                                ),
                            ): NumberSelector(
                                NumberSelectorConfig(
                                    min=MIN_AUTO_QUOTA_INTERVAL_S,
                                    max=MAX_AUTO_QUOTA_INTERVAL_S,
                                    step=1,
                                    mode=NumberSelectorMode.BOX,
                                )
                            ),
                            vol.Optional(
                                CONF_QUOTA_SAFETY_RESERVE,
                                default=self._get_current_data(
                                    CONF_QUOTA_SAFETY_RESERVE,
                                    DEFAULT_QUOTA_SAFETY_RESERVE,
                                ),
                            ): NumberSelector(
                                NumberSelectorConfig(
                                    min=MIN_QUOTA_SAFETY_RESERVE,
                                    max=MAX_QUOTA_SAFETY_RESERVE,
                                    step=1,
                                    mode=NumberSelectorMode.BOX,
                                )
                            ),
                        }
                    ),
                    {"collapsed": True},
                ),
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
                vol.Required("features"): data_entry_flow.section(
                    vol.Schema(
                        {
                            vol.Optional(
                                CONF_FEATURE_DEW_POINT,
                                default=self._get_current_data(
                                    CONF_FEATURE_DEW_POINT,
                                    DEFAULT_FEATURE_DEW_POINT,
                                ),
                            ): BooleanSelector(),
                            vol.Optional(
                                CONF_FEATURE_MOLD_DETECTION,
                                default=self._get_current_data(
                                    CONF_FEATURE_MOLD_DETECTION,
                                    DEFAULT_FEATURE_MOLD_DETECTION,
                                ),
                            ): BooleanSelector(),
                            vol.Optional(
                                CONF_OUTDOOR_WEATHER_ENTITY,
                                description={
                                    "suggested_value": self._get_current_data(
                                        CONF_OUTDOOR_WEATHER_ENTITY, None
                                    )
                                },
                            ): EntitySelector(EntitySelectorConfig(domain="weather")),
                            vol.Optional(
                                CONF_VENTILATION_AH_THRESHOLD,
                                default=self._get_current_data(
                                    CONF_VENTILATION_AH_THRESHOLD,
                                    DEFAULT_VENTILATION_AH_THRESHOLD,
                                ),
                            ): NumberSelector(
                                NumberSelectorConfig(
                                    min=0.1,
                                    max=5.0,
                                    step=0.1,
                                    unit_of_measurement="g/m³",
                                    mode=NumberSelectorMode.BOX,
                                )
                            ),
                        }
                    ),
                    {"collapsed": True},
                ),
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
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema(_schema),
            )
        processed_input = self._flatten_section_data(user_input)

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

    VERSION = 8
    login_task: asyncio.Task[Any] | None = None
    refresh_token: str | None = None
    tado: Tado | None = None

    def __init__(self) -> None:
        """Initialize config flow."""
        self._data: dict[str, Any] = {}
        self._generation: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: Choice of Tado Generation and Cloud Mode."""
        if user_input is not None:
            self._generation = user_input[CONF_GENERATION]
            self._data[CONF_FULL_CLOUD_MODE] = user_input.get(
                CONF_FULL_CLOUD_MODE, False
            )
            self._data[CONF_FETCH_EXTENDED_DATA] = user_input.get(
                CONF_FETCH_EXTENDED_DATA, True
            )
            return await self.async_step_init()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_GENERATION, default=GEN_CLASSIC): SelectSelector(
                        SelectSelectorConfig(
                            options=[GEN_CLASSIC, GEN_X],
                            mode=SelectSelectorMode.LIST,
                            translation_key="generation",
                        )
                    ),
                    vol.Optional(
                        CONF_FULL_CLOUD_MODE, default=False
                    ): BooleanSelector(),
                    vol.Optional(
                        CONF_FETCH_EXTENDED_DATA, default=True
                    ): BooleanSelector(),
                }
            ),
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start the configuration (Auth-Last)."""
        self._data[CONF_GENERATION] = self._generation
        return await super().async_step_init(user_input)

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
                title=f"Tado Hijack (Proxy - {self._generation})",
                data={CONF_REFRESH_TOKEN: self.refresh_token, **self._data},
            )

        return await self.async_step_tado_auth()

    async def async_step_tado_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Authenticate with Tado Cloud (Library Flow)."""
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
            """Poll for login status via library."""
            if self.tado is None:
                raise CannotConnect
            try:
                await self.tado.device_activation()
            except KeyError as ex:
                if "homes" in str(ex):
                    raise NoHomesReturnedError from ex
                raise CannotConnect from ex
            except Exception as ex:
                raise CannotConnect from ex
            if self.tado.device_activation_status != "COMPLETED":
                raise CannotConnect

        if self.login_task is None:
            self.login_task = self.hass.async_create_task(_wait_for_login())

        if self.login_task.done():
            exc = self.login_task.exception()
            if exc:
                if isinstance(exc, NoHomesReturnedError):
                    return self.async_show_progress_done(
                        next_step_id="no_homes_returned"
                    )
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

    async def async_step_no_homes_returned(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show error that the API returned no homes."""
        return self.async_abort(reason="no_homes_returned")

    async def async_step_finish_login(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Complete login and create entry."""
        # Use simple title for Tado X, detailed for v3
        title = "Tado X Home"
        if self.tado:
            tado_me = await self.tado.get_me()
            if tado_me.homes:
                home = tado_me.homes[0]
                await self.async_set_unique_id(str(home.id))
                title = f"Tado {home.name}"

        # Store generation as-is (no detection needed)
        self._data[CONF_GENERATION] = self._generation

        if self.source == config_entries.SOURCE_REAUTH:
            reauth_entry = self._get_reauth_entry()
            return self.async_update_reload_and_abort(
                reauth_entry,
                data={**reauth_entry.data, CONF_REFRESH_TOKEN: self.refresh_token},
            )

        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=title,
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
        return self.async_create_entry(title="", data={})


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class NoHomesReturnedError(HomeAssistantError):
    """Error to indicate the API did not return a 'homes' array."""
