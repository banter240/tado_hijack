"""Constants for Tado Hijack."""

from typing import Final

DOMAIN: Final = "tado_hijack"

# Library Specifics
TADO_VERSION_PATCH: Final = "0.2.2"
TADO_USER_AGENT: Final = f"HomeAssistant/{TADO_VERSION_PATCH}"

# Configuration Keys
CONF_REFRESH_TOKEN: Final = "refresh_token"
CONF_SLOW_POLL_INTERVAL: Final = "slow_poll_interval"
CONF_OFFSET_POLL_INTERVAL: Final = "offset_poll_interval"
CONF_THROTTLE_THRESHOLD: Final = "throttle_threshold"
CONF_DISABLE_POLLING_WHEN_THROTTLED: Final = "disable_polling_when_throttled"
CONF_DEBOUNCE_TIME: Final = "debounce_time"
CONF_API_PROXY_URL: Final = "api_proxy_url"

# Default Intervals
DEFAULT_SCAN_INTERVAL: Final = 3600
DEFAULT_SLOW_POLL_INTERVAL: Final = 24  # Hours
DEFAULT_OFFSET_POLL_INTERVAL: Final = 0  # Hours (0 = disabled)
DEFAULT_DEBOUNCE_TIME: Final = 5  # Seconds
DEFAULT_THROTTLE_THRESHOLD: Final = (
    0  # 0 = disabled, >0 = throttle when remaining < threshold
)

# Minimums (scan_interval 0 = no periodic poll, offset 0 = disabled)
MIN_SCAN_INTERVAL: Final = 0
MIN_SLOW_POLL_INTERVAL: Final = 1  # Hour
MIN_OFFSET_POLL_INTERVAL: Final = 0  # 0 = disabled
MIN_DEBOUNCE_TIME: Final = 1  # Second

# Timing & Logic
DEBOUNCE_COOLDOWN_S: Final = 5  # Legacy fallback / initial value
OPTIMISTIC_GRACE_PERIOD_S: Final = 30
PROTECTION_MODE_TEMP: Final = 5.0  # Minimum safe temperature for manual override
BOOST_MODE_TEMP: Final = 25.0  # Temperature for Boost All
BATCH_LINGER_S: Final = 1.0  # Time to wait for more commands in batch
INITIAL_RATE_LIMIT_GUESS: Final = 100  # Pessimistic initial guess
SLOW_POLL_CYCLE_S: Final = 86400  # 24 Hours in seconds

# Service Names
SERVICE_MANUAL_POLL: Final = "manual_poll"
SERVICE_RESUME_ALL_SCHEDULES: Final = "resume_all_schedules"
SERVICE_TURN_OFF_ALL_ZONES: Final = "turn_off_all_zones"
SERVICE_BOOST_ALL_ZONES: Final = "boost_all_zones"

# Device Capabilities
CAPABILITY_INSIDE_TEMP: Final = "INSIDE_TEMPERATURE_MEASUREMENT"
TEMP_OFFSET_ATTR: Final = "temperatureOffset"

# Device Type Mapping
DEVICE_TYPE_MAP: Final[dict[str, str]] = {
    "VA02": "Smart Radiator Thermostat",
    "RU01": "Smart Thermostat",
    "RU02": "Smart Thermostat",
    "IB01": "Internet Bridge",
    "WR02": "Wireless Receiver",
    "BU01": "Smart Radiator Thermostat (Vertical)",
}

# Diagnostics Redaction
DIAGNOSTICS_REDACTED_PLACEHOLDER: Final = "**REDACTED**"
DIAGNOSTICS_TO_REDACT_CONFIG_KEYS: Final = {
    CONF_REFRESH_TOKEN,
    "user_code",
    "home_id",
}
DIAGNOSTICS_TO_REDACT_DATA_KEYS: Final = {
    "email",
    "username",
    "password",
    "refresh_token",
    "access_token",
    "homeId",
    "userId",
    "serialNo",
    "shortSerialNo",
    "macAddress",
    "latitude",
    "longitude",
}
