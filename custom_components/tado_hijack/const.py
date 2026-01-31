"""Constants for Tado Hijack."""

import os
from typing import Final

DOMAIN: Final = "tado_hijack"

# Library Specifics
TADO_VERSION_PATCH: Final = "0.2.2"
TADO_USER_AGENT: Final = f"HomeAssistant/{TADO_VERSION_PATCH}"

# Configuration Keys
CONF_REFRESH_TOKEN: Final = "refresh_token"
CONF_SCAN_INTERVAL: Final = "scan_interval"  # Zone polling
CONF_PRESENCE_POLL_INTERVAL: Final = "presence_poll_interval"
CONF_SLOW_POLL_INTERVAL: Final = "slow_poll_interval"
CONF_OFFSET_POLL_INTERVAL: Final = "offset_poll_interval"
CONF_THROTTLE_THRESHOLD: Final = "throttle_threshold"
CONF_DISABLE_POLLING_WHEN_THROTTLED: Final = "disable_polling_when_throttled"
CONF_DEBOUNCE_TIME: Final = "debounce_time"
CONF_API_PROXY_URL: Final = "api_proxy_url"
CONF_DEBUG_LOGGING: Final = "debug_logging"
CONF_AUTO_API_QUOTA_PERCENT: Final = "auto_api_quota_percent"
CONF_REFRESH_AFTER_RESUME: Final = "refresh_after_resume"
CONF_REDUCED_POLLING_ACTIVE: Final = "reduced_polling_active"
CONF_REDUCED_POLLING_START: Final = "reduced_polling_start"
CONF_REDUCED_POLLING_END: Final = "reduced_polling_end"
CONF_REDUCED_POLLING_INTERVAL: Final = "reduced_polling_interval"
CONF_CALL_JITTER_ENABLED: Final = "call_jitter_enabled"
CONF_JITTER_PERCENT: Final = "jitter_percent"

# [DUMMY_HOOK]
# Enable dummy zones for development/testing via environment variable
# Set TADO_ENABLE_DUMMIES=true before starting Home Assistant
CONF_ENABLE_DUMMY_ZONES: Final = (
    os.getenv("TADO_ENABLE_DUMMIES", "false").lower() == "true"
)

# Default Intervals
DEFAULT_SCAN_INTERVAL: Final = 1800  # 30 minutes (Zone States)
DEFAULT_PRESENCE_POLL_INTERVAL: Final = 43200  # 12 hours
DEFAULT_SLOW_POLL_INTERVAL: Final = 86400  # 24 hours (Hardware Metadata)
DEFAULT_OFFSET_POLL_INTERVAL: Final = 0  # Disabled by default
DEFAULT_AUTO_API_QUOTA_PERCENT: Final = 80  # Use 80% of daily quota by default
DEFAULT_DEBOUNCE_TIME: Final = 5  # Seconds
DEFAULT_THROTTLE_THRESHOLD: Final = 20  # Reserve last 20 calls for external use
DEFAULT_REFRESH_AFTER_RESUME: Final = True  # Refresh state after resume schedule
DEFAULT_REDUCED_POLLING_START: Final = "22:00"
DEFAULT_REDUCED_POLLING_END: Final = "07:00"
DEFAULT_REDUCED_POLLING_INTERVAL: Final = 3600  # 1 hour
DEFAULT_JITTER_ENABLED: Final = False
DEFAULT_JITTER_PERCENT: Final = 10.0  # 10% variation (+/- 10%)

# Minimums (0 = no periodic poll / disabled)
MIN_SCAN_INTERVAL: Final = 0
MIN_PRESENCE_POLL_INTERVAL: Final = 0
MIN_SLOW_POLL_INTERVAL: Final = 0
MIN_OFFSET_POLL_INTERVAL: Final = 0
MIN_DEBOUNCE_TIME: Final = 1  # Second
MIN_AUTO_QUOTA_INTERVAL_S: Final = 45  # Safety floor for dynamic polling
MIN_PROXY_INTERVAL_S: Final = 120  # Minimum for proxy usage
MIN_REDUCED_POLLING_INTERVAL: Final = 0  # 0 = complete pause during timeframe
MAX_API_QUOTA: Final = 5000  # Default Tado daily limit

# Timing & Logic
SECONDS_PER_HOUR: Final = 3600
SECONDS_PER_DAY: Final = 86400
RATELIMIT_SMOOTHING_ALPHA: Final = 0.3  # Exponential moving average factor
DEBOUNCE_COOLDOWN_S: Final = 5  # Legacy fallback / initial value
OPTIMISTIC_GRACE_PERIOD_S: Final = 30
PROTECTION_MODE_TEMP: Final = 5.0  # Minimum safe temperature for manual override
BOOST_MODE_TEMP: Final = 25.0  # Temperature for Boost All
BATCH_LINGER_S: Final = 1.0  # Time to wait for more commands in batch
RESUME_REFRESH_DELAY_S: Final = (
    1.0  # Grace period to collect multiple resumes before refresh
)
INITIAL_RATE_LIMIT_GUESS: Final = 100  # Pessimistic initial guess
SLOW_POLL_CYCLE_S: Final = 86400  # 24 Hours in seconds
MAX_OVERLAY_DURATION_MIN: Final = 1440  # 24 Hours in minutes

# Zone Types
ZONE_TYPE_HEATING: Final = "HEATING"
ZONE_TYPE_HOT_WATER: Final = "HOT_WATER"
ZONE_TYPE_AIR_CONDITIONING: Final = "AIR_CONDITIONING"

# Power States
POWER_ON: Final = "ON"
POWER_OFF: Final = "OFF"

# Temperature Limits
TEMP_MIN_HEATING: Final = 5.0
TEMP_MAX_HEATING: Final = 25.0
TEMP_MIN_HOT_WATER: Final = 30.0
TEMP_MAX_HOT_WATER: Final = 65.0
TEMP_MAX_HOT_WATER_OVERRIDE: Final = 70.0  # Absolute limit for HW sliders
TEMP_MIN_AC: Final = 16.0
TEMP_MAX_AC: Final = 30.0
TEMP_DEFAULT_HEATING: Final = 21.0
TEMP_DEFAULT_HOT_WATER: Final = 30.0
TEMP_DEFAULT_AC: Final = 22.0

# Temperature Steps
TEMP_STEP_TRV: Final = 0.1
TEMP_STEP_HOT_WATER: Final = 1.0
TEMP_STEP_AC: Final = 1.0

# Overlay/Termination Types
OVERLAY_MANUAL: Final = "manual"
OVERLAY_TIMER: Final = "timer"
OVERLAY_AUTO: Final = "auto"
OVERLAY_NEXT_BLOCK: Final = "next_block"
OVERLAY_PRESENCE: Final = "presence"
TERMINATION_MANUAL: Final = "MANUAL"
TERMINATION_TIMER: Final = "TIMER"
TERMINATION_TADO_MODE: Final = "TADO_MODE"
TERMINATION_NEXT_TIME_BLOCK: Final = "NEXT_TIME_BLOCK"

# Auto API Quota
# Reset happens somewhere in this window (Berlin time)
API_RESET_HOUR_START: Final = 12
API_RESET_HOUR_END: Final = 13
API_RESET_RECOVERY_THRESHOLD: Final = 0.9
API_RESET_BUFFER_MINUTES: Final = 1
THROTTLE_RECOVERY_INTERVAL_S: Final = 900  # 15 minutes (Recovery check when throttled)

# Service Names
SERVICE_MANUAL_POLL = "manual_poll"
SERVICE_RESUME_ALL_SCHEDULES = "resume_all_schedules"
SERVICE_TURN_OFF_ALL_ZONES = "turn_off_all_zones"
SERVICE_BOOST_ALL_ZONES = "boost_all_zones"
SERVICE_SET_MODE = "set_mode"
SERVICE_SET_MODE_ALL = "set_mode_all_zones"
SERVICE_SET_WATER_HEATER_MODE = "set_water_heater_mode"


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
