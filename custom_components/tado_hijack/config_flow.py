"""Config flow for Tado Hijack."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant import config_entries, data_entry_flow
from homeassistant.components.sensor import SensorDeviceClass
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
from homeassistant.util import slugify
from tadoasync import Tado, TadoError
from yarl import URL

from .const import (
    CONF_API_PROXY_URL,
    CONF_AUTO_API_QUOTA_PERCENT,
    CONF_CALL_JITTER_ENABLED,
    CONF_DEBOUNCE_TIME,
    CONF_DISABLE_POLLING_WHEN_THROTTLED,
    CONF_FEATURE_DEW_POINT,
    CONF_FEATURE_FLOW_TEMP,
    CONF_FEATURE_MOLD_DETECTION,
    CONF_FEATURE_ZONE_CIRCUIT,
    CONF_FETCH_EXTENDED_DATA,
    CONF_FULL_CLOUD_MODE,
    CONF_GENERATION,
    CONF_HOME_ID,
    CONF_JITTER_PERCENT,
    CONF_LINK_LOCAL_DEVICES,
    CONF_LOG_LEVEL,
    CONF_LOG_VERSION_PREFIX,
    CONF_MIN_AUTO_QUOTA_INTERVAL_S,
    CONF_OFFSET_CAL_SEND_COOLDOWN_S,
    CONF_OFFSET_CAL_WINDOW_SETTLE_S,
    CONF_OFFSET_POLL_INTERVAL,
    CONF_OUTDOOR_HUMIDITY_ENTITY,
    CONF_OUTDOOR_TEMP_ENTITY,
    CONF_OUTDOOR_WEATHER_ENTITY,
    CONF_PRESENCE_POLL_INTERVAL,
    CONF_PROXY_LOCAL_ENTITIES,
    CONF_PROXY_TOKEN,
    CONF_QUOTA_SAFETY_RESERVE,
    CONF_RECOVERY_CLOUD_REPLAY,
    CONF_REDUCED_POLLING_ACTIVE,
    CONF_REDUCED_POLLING_END,
    CONF_REDUCED_POLLING_INTERVAL,
    CONF_REDUCED_POLLING_START,
    CONF_REFRESH_AFTER_RESUME,
    CONF_REFRESH_PLANS_AFTER_RESET,
    CONF_REFRESH_TOKEN,
    CONF_SLOW_POLL_INTERVAL,
    CONF_SUPPRESS_REDUNDANT_BUTTONS,
    CONF_SUPPRESS_REDUNDANT_CALLS,
    CONF_THROTTLE_THRESHOLD,
    CONF_VENTILATION_AH_THRESHOLD,
    CONF_WINDOW_RESUME_BATCH,
    CONF_WINDOW_RESUME_BATCH_S,
    DEFAULT_AUTO_API_QUOTA_PERCENT,
    DEFAULT_DEBOUNCE_TIME,
    DEFAULT_FEATURE_DEW_POINT,
    DEFAULT_FEATURE_FLOW_TEMP,
    DEFAULT_FEATURE_MOLD_DETECTION,
    DEFAULT_FEATURE_ZONE_CIRCUIT,
    DEFAULT_JITTER_PERCENT,
    DEFAULT_LINK_LOCAL_DEVICES,
    DEFAULT_LOG_LEVEL,
    DEFAULT_LOG_VERSION_PREFIX,
    DEFAULT_MIN_AUTO_QUOTA_INTERVAL_S,
    DEFAULT_OFFSET_CAL_SEND_COOLDOWN_S,
    DEFAULT_OFFSET_CAL_WINDOW_SETTLE_S,
    DEFAULT_OFFSET_POLL_INTERVAL,
    DEFAULT_PRESENCE_POLL_INTERVAL,
    DEFAULT_PROXY_LOCAL_ENTITIES,
    DEFAULT_QUOTA_SAFETY_RESERVE,
    DEFAULT_RECOVERY_CLOUD_REPLAY,
    DEFAULT_REDUCED_POLLING_END,
    DEFAULT_REDUCED_POLLING_INTERVAL,
    DEFAULT_REDUCED_POLLING_START,
    DEFAULT_REFRESH_AFTER_RESUME,
    DEFAULT_REFRESH_PLANS_AFTER_RESET,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLOW_POLL_INTERVAL,
    DEFAULT_SUPPRESS_REDUNDANT_BUTTONS,
    DEFAULT_SUPPRESS_REDUNDANT_CALLS,
    DEFAULT_THROTTLE_THRESHOLD,
    DEFAULT_VENTILATION_AH_THRESHOLD,
    DEFAULT_WINDOW_RESUME_BATCH,
    DEFAULT_WINDOW_RESUME_BATCH_S,
    DOMAIN,
    GEN_CLASSIC,
    GEN_X,
    LOG_LEVELS,
    MAX_API_QUOTA,
    MAX_AUTO_QUOTA_INTERVAL_S,
    MAX_OFFSET_CAL_COOLDOWN_S,
    MAX_QUOTA_SAFETY_RESERVE,
    MAX_WINDOW_RESUME_BATCH_S,
    MIN_AUTO_QUOTA_INTERVAL_S,
    MIN_DEBOUNCE_TIME,
    MIN_OFFSET_POLL_INTERVAL,
    MIN_QUOTA_SAFETY_RESERVE,
    MIN_SCAN_INTERVAL,
    MIN_SLOW_POLL_INTERVAL,
    MIN_WINDOW_RESUME_BATCH_S,
)
from .entity import entry_home_label
from .helpers.logging_utils import get_redacted_logger
from .lib.patches import apply_patches

apply_patches()

_LOGGER = get_redacted_logger(__name__)


def _home_choice_labels(homes: list[tuple[int, str]]) -> dict[str, str]:
    """Dropdown labels. A repeated home name keeps the home id so it can be told apart."""
    counts: dict[str, int] = {}
    for _, name in homes:
        counts[name] = counts.get(name, 0) + 1
    return {
        str(home_id): name if counts[name] == 1 else f"{name} ({home_id})"
        for home_id, name in homes
    }


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
                CONF_REFRESH_PLANS_AFTER_RESET,
            ],
            "reduced_polling": [
                CONF_REDUCED_POLLING_ACTIVE,
                CONF_REDUCED_POLLING_START,
                CONF_REDUCED_POLLING_END,
                CONF_REDUCED_POLLING_INTERVAL,
            ],
            "api_quota": [
                CONF_AUTO_API_QUOTA_PERCENT,
                CONF_THROTTLE_THRESHOLD,
                CONF_DISABLE_POLLING_WHEN_THROTTLED,
                CONF_SUPPRESS_REDUNDANT_CALLS,
                CONF_SUPPRESS_REDUNDANT_BUTTONS,
                CONF_MIN_AUTO_QUOTA_INTERVAL_S,
                CONF_QUOTA_SAFETY_RESERVE,
            ],
            "window": [
                CONF_WINDOW_RESUME_BATCH,
                CONF_WINDOW_RESUME_BATCH_S,
                CONF_OFFSET_CAL_WINDOW_SETTLE_S,
            ],
            "offset": [
                CONF_OFFSET_POLL_INTERVAL,
                CONF_OFFSET_CAL_SEND_COOLDOWN_S,
            ],
            "recovery": [
                CONF_RECOVERY_CLOUD_REPLAY,
                CONF_REFRESH_AFTER_RESUME,
            ],
            "features": [
                CONF_LINK_LOCAL_DEVICES,
                CONF_PROXY_LOCAL_ENTITIES,
                CONF_FEATURE_DEW_POINT,
                CONF_FEATURE_FLOW_TEMP,
                CONF_FEATURE_ZONE_CIRCUIT,
                CONF_FEATURE_MOLD_DETECTION,
                CONF_OUTDOOR_WEATHER_ENTITY,
                CONF_OUTDOOR_TEMP_ENTITY,
                CONF_OUTDOOR_HUMIDITY_ENTITY,
                CONF_VENTILATION_AH_THRESHOLD,
            ],
            "advanced": [
                CONF_API_PROXY_URL,
                CONF_PROXY_TOKEN,
                CONF_CALL_JITTER_ENABLED,
                CONF_JITTER_PERCENT,
                CONF_DEBOUNCE_TIME,
                CONF_LOG_LEVEL,
                CONF_LOG_VERSION_PREFIX,
            ],
        }

        for section_name, keys in sections.items():
            if section_name in user_input:
                section_data = user_input[section_name]
                for key in keys:
                    if key in section_data:
                        val = section_data[key]
                        # Handle empty string to None conversion for optional fields
                        if key in (
                            CONF_OUTDOOR_WEATHER_ENTITY,
                            CONF_OUTDOOR_TEMP_ENTITY,
                            CONF_OUTDOOR_HUMIDITY_ENTITY,
                        ):
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
                                CONF_REFRESH_PLANS_AFTER_RESET,
                                default=self._get_current_data(
                                    CONF_REFRESH_PLANS_AFTER_RESET,
                                    DEFAULT_REFRESH_PLANS_AFTER_RESET,
                                ),
                            ): BooleanSelector(),
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
                vol.Required("window"): data_entry_flow.section(
                    vol.Schema(
                        {
                            vol.Optional(
                                CONF_WINDOW_RESUME_BATCH,
                                default=self._get_current_data(
                                    CONF_WINDOW_RESUME_BATCH,
                                    DEFAULT_WINDOW_RESUME_BATCH,
                                ),
                            ): BooleanSelector(),
                            vol.Optional(
                                CONF_WINDOW_RESUME_BATCH_S,
                                default=self._get_current_data(
                                    CONF_WINDOW_RESUME_BATCH_S,
                                    DEFAULT_WINDOW_RESUME_BATCH_S,
                                ),
                            ): NumberSelector(
                                NumberSelectorConfig(
                                    min=MIN_WINDOW_RESUME_BATCH_S,
                                    max=MAX_WINDOW_RESUME_BATCH_S,
                                    step=10,
                                    unit_of_measurement="s",
                                    mode=NumberSelectorMode.BOX,
                                )
                            ),
                            vol.Optional(
                                CONF_OFFSET_CAL_WINDOW_SETTLE_S,
                                default=self._get_current_data(
                                    CONF_OFFSET_CAL_WINDOW_SETTLE_S,
                                    DEFAULT_OFFSET_CAL_WINDOW_SETTLE_S,
                                ),
                            ): NumberSelector(
                                NumberSelectorConfig(
                                    min=0,
                                    max=MAX_OFFSET_CAL_COOLDOWN_S,
                                    step=30,
                                    unit_of_measurement="s",
                                    mode=NumberSelectorMode.BOX,
                                )
                            ),
                        }
                    ),
                    {"collapsed": True},
                ),
                vol.Required("offset"): data_entry_flow.section(
                    vol.Schema(
                        {
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
                            vol.Optional(
                                CONF_OFFSET_CAL_SEND_COOLDOWN_S,
                                default=self._get_current_data(
                                    CONF_OFFSET_CAL_SEND_COOLDOWN_S,
                                    DEFAULT_OFFSET_CAL_SEND_COOLDOWN_S,
                                ),
                            ): NumberSelector(
                                NumberSelectorConfig(
                                    min=0,
                                    max=MAX_OFFSET_CAL_COOLDOWN_S,
                                    step=30,
                                    unit_of_measurement="s",
                                    mode=NumberSelectorMode.BOX,
                                )
                            ),
                        }
                    ),
                    {"collapsed": True},
                ),
                vol.Required("recovery"): data_entry_flow.section(
                    vol.Schema(
                        {
                            vol.Optional(
                                CONF_RECOVERY_CLOUD_REPLAY,
                                default=self._get_current_data(
                                    CONF_RECOVERY_CLOUD_REPLAY,
                                    DEFAULT_RECOVERY_CLOUD_REPLAY,
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
                vol.Required("features"): data_entry_flow.section(
                    vol.Schema(
                        {
                            vol.Optional(
                                CONF_LINK_LOCAL_DEVICES,
                                default=self._get_current_data(
                                    CONF_LINK_LOCAL_DEVICES,
                                    DEFAULT_LINK_LOCAL_DEVICES,
                                ),
                            ): BooleanSelector(),
                            vol.Optional(
                                CONF_PROXY_LOCAL_ENTITIES,
                                default=self._get_current_data(
                                    CONF_PROXY_LOCAL_ENTITIES,
                                    DEFAULT_PROXY_LOCAL_ENTITIES,
                                ),
                            ): BooleanSelector(),
                            vol.Optional(
                                CONF_FEATURE_DEW_POINT,
                                default=self._get_current_data(
                                    CONF_FEATURE_DEW_POINT,
                                    DEFAULT_FEATURE_DEW_POINT,
                                ),
                            ): BooleanSelector(),
                            vol.Optional(
                                CONF_FEATURE_FLOW_TEMP,
                                default=self._get_current_data(
                                    CONF_FEATURE_FLOW_TEMP,
                                    DEFAULT_FEATURE_FLOW_TEMP,
                                ),
                            ): BooleanSelector(),
                            vol.Optional(
                                CONF_FEATURE_ZONE_CIRCUIT,
                                default=self._get_current_data(
                                    CONF_FEATURE_ZONE_CIRCUIT,
                                    DEFAULT_FEATURE_ZONE_CIRCUIT,
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
                                CONF_OUTDOOR_TEMP_ENTITY,
                                description={
                                    "suggested_value": self._get_current_data(
                                        CONF_OUTDOOR_TEMP_ENTITY, None
                                    )
                                },
                            ): EntitySelector(
                                EntitySelectorConfig(
                                    domain="sensor",
                                    device_class=SensorDeviceClass.TEMPERATURE,
                                )
                            ),
                            vol.Optional(
                                CONF_OUTDOOR_HUMIDITY_ENTITY,
                                description={
                                    "suggested_value": self._get_current_data(
                                        CONF_OUTDOOR_HUMIDITY_ENTITY, None
                                    )
                                },
                            ): EntitySelector(
                                EntitySelectorConfig(
                                    domain="sensor",
                                    device_class=SensorDeviceClass.HUMIDITY,
                                )
                            ),
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
                            vol.Required(
                                CONF_LOG_VERSION_PREFIX,
                                default=self._get_current_data(
                                    CONF_LOG_VERSION_PREFIX,
                                    DEFAULT_LOG_VERSION_PREFIX,
                                ),
                            ): BooleanSelector(),
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

    VERSION = 13
    login_task: asyncio.Task[Any] | None = None
    refresh_token: str | None = None
    tado: Tado | None = None

    def __init__(self) -> None:
        """Initialize config flow."""
        self._data: dict[str, Any] = {}
        self._generation: str | None = None
        self._homes: list[tuple[int, str]] = []
        self._chosen_home: tuple[int, str] | None = None

    def _configured_home_ids(self) -> set[str]:
        """Home ids that already have an entry."""
        found: set[str] = set()
        for entry in self._async_current_entries():
            if entry.unique_id and str(entry.unique_id).isdigit():
                found.add(str(entry.unique_id))
            raw = entry.data.get(CONF_HOME_ID)
            if raw is not None:
                found.add(str(raw))
        return found

    def _available_homes(self, homes: list[tuple[int, str]]) -> list[tuple[int, str]]:
        """Homes that can still be added."""
        taken = self._configured_home_ids()
        return [home for home in homes if str(home[0]) not in taken]

    async def _async_generation_for_home(self, home_id: int) -> str:
        """Default the generation form from the home. ``LINE_X`` is Tado X."""
        if self.tado is None:
            return GEN_CLASSIC
        try:
            raw = await self.tado._request(f"homes/{home_id}")
            detail = json.loads(raw)
        except TadoError, TypeError, ValueError:
            _LOGGER.debug("Home generation lookup failed")
            return GEN_CLASSIC
        if isinstance(detail, dict) and detail.get("generation") == "LINE_X":
            return GEN_X
        return GEN_CLASSIC

    async def _async_open_home_setup(
        self, home: tuple[int, str] | None
    ) -> ConfigFlowResult:
        """Store the home, then show its settings."""
        self._chosen_home = home
        self._generation = (
            GEN_CLASSIC
            if home is None
            else await self._async_generation_for_home(home[0])
        )
        return await self.async_step_hardware()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Log in first so the account's homes can be listed."""
        return await self.async_step_tado_auth()

    async def async_step_hardware(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Generation and cloud settings for the home just chosen."""
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
            step_id="hardware",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_GENERATION, default=self._generation or GEN_CLASSIC
                    ): SelectSelector(
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

        if api_proxy_url and not self.refresh_token:
            _LOGGER.info("Proxy detected, skipping Tado Cloud Auth")
            self.refresh_token = "proxy_managed"
            await self.async_set_unique_id(f"proxy_{api_proxy_url}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"Tado Hijack (Proxy - {self._generation})",
                data={CONF_REFRESH_TOKEN: self.refresh_token, **self._data},
            )

        if self.refresh_token:
            return await self._async_create_home_entry(self._chosen_home)
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

    async def _async_load_homes(self) -> list[tuple[int, str]]:
        """Homes on this account. ``GET /me`` returns every home, not one."""
        if self._homes:
            return self._homes
        if self.tado is None:
            return []
        tado_me = await self.tado.get_me()
        self._homes = [(home.id, home.name) for home in tado_me.homes]
        return self._homes

    async def async_step_finish_login(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """After login, pick one free home, then its settings."""
        if self.source == config_entries.SOURCE_REAUTH:
            reauth_entry = self._get_reauth_entry()
            return self.async_update_reload_and_abort(
                reauth_entry,
                data={**reauth_entry.data, CONF_REFRESH_TOKEN: self.refresh_token},
            )

        homes = await self._async_load_homes()
        available = self._available_homes(homes)
        if homes and not available:
            return self.async_abort(reason="all_homes_configured")
        if len(homes) <= 1:
            only = available[0] if available else None
            return await self._async_open_home_setup(only)
        return await self.async_step_select_home()

    async def async_step_select_home(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick one home that is not set up yet."""
        homes = self._available_homes(await self._async_load_homes())
        if not homes:
            return self.async_abort(reason="all_homes_configured")
        if user_input is not None:
            selected = int(user_input[CONF_HOME_ID])
            if str(selected) in self._configured_home_ids():
                return self.async_abort(reason="already_configured")
            home = next((item for item in homes if item[0] == selected), None)
            if home is None:
                return self.async_abort(reason="no_homes")
            return await self._async_open_home_setup(home)

        return self.async_show_form(
            step_id="select_home",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOME_ID): vol.In(_home_choice_labels(homes)),
                }
            ),
        )

    def _available_title(self, name: str) -> str:
        """Title that does not share a name slug with an entry already added."""
        base = f"Tado {name}"
        entries = self._async_current_entries()
        used_titles = {entry.title for entry in entries}
        used_slugs = {slugify(entry_home_label(entry)) or "home" for entry in entries}

        def taken(title: str) -> bool:
            label = title[5:].strip() if title.startswith("Tado ") else title
            return title in used_titles or (slugify(label) or "home") in used_slugs

        if not taken(base):
            return base
        number = 2
        while taken(f"{base} {number}"):
            number += 1
        return f"{base} {number}"

    async def _async_create_home_entry(
        self, home: tuple[int, str] | None
    ) -> ConfigFlowResult:
        """Create the entry for one home. The same home cannot be added twice."""
        title = "Tado X Home"
        if home is not None:
            home_id, name = home
            await self.async_set_unique_id(str(home_id))
            self._abort_if_unique_id_configured()
            title = self._available_title(name)
            self._data[CONF_HOME_ID] = home_id

        self._data[CONF_GENERATION] = self._generation
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
