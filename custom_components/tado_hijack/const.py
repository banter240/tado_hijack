"""Constants for Tado Hijack."""

import os
from typing import Final

DOMAIN: Final = "tado_hijack"

# Library Specifics
TADO_VERSION_PATCH: Final = "0.2.2"
TADO_USER_AGENT: Final = f"HomeAssistant/{TADO_VERSION_PATCH}"

# Configuration Keys
CONF_GENERATION: Final = "generation"
CONF_FULL_CLOUD_MODE: Final = "full_cloud_mode"
CONF_FETCH_EXTENDED_DATA: Final = "fetch_extended_data"
CONF_REFRESH_TOKEN: Final = "refresh_token"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_PRESENCE_POLL_INTERVAL: Final = "presence_poll_interval"
CONF_SLOW_POLL_INTERVAL: Final = "slow_poll_interval"
CONF_OFFSET_POLL_INTERVAL: Final = "offset_poll_interval"
CONF_THROTTLE_THRESHOLD: Final = "throttle_threshold"
CONF_DISABLE_POLLING_WHEN_THROTTLED: Final = "disable_polling_when_throttled"
CONF_LOG_LEVEL: Final = "log_level"
CONF_DEBOUNCE_TIME: Final = "debounce_time"
CONF_API_PROXY_URL: Final = "api_proxy_url"
CONF_PROXY_TOKEN: Final = "proxy_token"
CONF_AUTO_API_QUOTA_PERCENT: Final = "auto_api_quota_percent"
CONF_REFRESH_AFTER_RESUME: Final = "refresh_after_resume"
CONF_REDUCED_POLLING_ACTIVE: Final = "reduced_polling_active"
CONF_REDUCED_POLLING_START: Final = "reduced_polling_start"
CONF_REDUCED_POLLING_END: Final = "reduced_polling_end"
CONF_REDUCED_POLLING_INTERVAL: Final = "reduced_polling_interval"
CONF_CALL_JITTER_ENABLED: Final = "call_jitter_enabled"
CONF_JITTER_PERCENT: Final = "jitter_percent"
CONF_MIN_AUTO_QUOTA_INTERVAL_S: Final = "min_auto_quota_interval_s"
CONF_QUOTA_SAFETY_RESERVE: Final = "quota_safety_reserve"
CONF_SUPPRESS_REDUNDANT_CALLS: Final = "suppress_redundant_calls"
CONF_SUPPRESS_REDUNDANT_BUTTONS: Final = "suppress_redundant_buttons"
CONF_INITIAL_POLL_DONE: Final = "initial_poll_done"

# Feature Flags
CONF_FEATURE_DEW_POINT: Final = "feature_dew_point"
CONF_FEATURE_MOLD_DETECTION: Final = "feature_mold_detection"
CONF_OUTDOOR_WEATHER_ENTITY: Final = "outdoor_weather_entity"
CONF_VENTILATION_AH_THRESHOLD: Final = "ventilation_ah_threshold"
CONF_ZONE_TEMP_ENTITIES: Final = "zone_temp_entities"
CONF_ZONE_HUMIDITY_ENTITIES: Final = "zone_humidity_entities"

# Logging Levels
LOG_LEVELS: Final[list[str]] = ["DEBUG", "INFO", "WARNING", "ERROR"]
DEFAULT_LOG_LEVEL: Final = "INFO"

# [DUMMY_HOOK]
# Enable dummy zones for development/testing via environment variable
# Set TADO_ENABLE_DUMMIES=true before starting Home Assistant
CONF_ENABLE_DUMMY_ZONES: Final = (
    os.getenv("TADO_ENABLE_DUMMIES", "false").lower() == "true"
)

# Hardware Generations
GEN_CLASSIC: Final = "classic"  # V2/V3 (GW/IB01/GW01) - Classic API
GEN_X: Final = "x"  # Tado X (IB02) - Hops API

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
DEFAULT_JITTER_PERCENT: Final = 10.0  # 10% variation (+/- 10%)
DEFAULT_MIN_AUTO_QUOTA_INTERVAL_S: Final = 20  # Default minimum interval for auto quota
DEFAULT_QUOTA_SAFETY_RESERVE: Final = 2  # API calls reserved for reset window (12-13h)
DEFAULT_SUPPRESS_REDUNDANT_CALLS: Final = False  # Opt-in redundancy suppression
DEFAULT_SUPPRESS_REDUNDANT_BUTTONS: Final = (
    False  # Opt-in button redundancy suppression
)

# Feature Flag Defaults (all on by default — zero cost when unused)
DEFAULT_FEATURE_DEW_POINT: Final = True
DEFAULT_FEATURE_MOLD_DETECTION: Final = True
DEFAULT_VENTILATION_AH_THRESHOLD: Final = 1.0  # g/m³

# Quota Safety Reserve Limits
MIN_QUOTA_SAFETY_RESERVE: Final = 0  # 0 = disabled (not recommended)
MAX_QUOTA_SAFETY_RESERVE: Final = 50

# Minimums (0 = no periodic poll / disabled)
MIN_SCAN_INTERVAL: Final = 0
MIN_SLOW_POLL_INTERVAL: Final = 0
MIN_OFFSET_POLL_INTERVAL: Final = 0
MIN_DEBOUNCE_TIME: Final = 1
MIN_AUTO_QUOTA_INTERVAL_S: Final = 5  # Absolute minimum for dynamic polling (standard)
MIN_PROXY_INTERVAL_S: Final = 120  # Minimum for proxy usage
MAX_AUTO_QUOTA_INTERVAL_S: Final = 43200  # Maximum 12 hours (in seconds)
MAX_API_QUOTA: Final = 5000  # Default Tado daily limit

# Timing & Logic
SECONDS_PER_HOUR: Final = 3600
SECONDS_PER_DAY: Final = 86400
API_RESET_MIDPOINT_MINUTE: Final = 30  # Midpoint of 12:00-13:00 reset window
RATELIMIT_SMOOTHING_ALPHA: Final = 0.3  # Exponential moving average factor
OPTIMISTIC_GRACE_PERIOD_S: Final = 30
PROTECTION_MODE_TEMP: Final = 5.0  # Minimum safe temperature for manual override
BOOST_MODE_TEMP: Final = 25.0  # Temperature for Boost All
BATCH_LINGER_S: Final = 1.0  # Time to wait for more commands in batch
RESUME_REFRESH_DELAY_S: Final = (
    1.0  # Grace period to collect multiple resumes before refresh
)
INITIAL_RATE_LIMIT_GUESS: Final = 100  # Pessimistic initial guess
MIN_OWD_TIMEOUT_MIN: Final = 5  # Minimum open window detection timeout in minutes
MIN_OWD_TIMEOUT_S: Final = MIN_OWD_TIMEOUT_MIN * 60  # 300 seconds
TEMP_TOLERANCE: Final = 0.1  # Tolerance for temperature float comparisons (degrees)
TEMP_STRICT_TOLERANCE: Final = 0.01  # Strict tolerance for offset/away-temp checks
HOME_ID_MIN_DIGITS: Final = 6  # Home IDs are 6+ digit integers
SERIAL_SHORT_LENGTH: Final = 6  # Short serial number uses last 6 characters
SLOW_POLL_CYCLE_S: Final = 86400  # 24 Hours in seconds

# Zone Types
ZONE_TYPE_HEATING: Final = "HEATING"
ZONE_TYPE_HOT_WATER: Final = "HOT_WATER"
ZONE_TYPE_AIR_CONDITIONING: Final = "AIR_CONDITIONING"

# Power States
POWER_ON: Final = "ON"
POWER_OFF: Final = "OFF"

# Magic Values
OFF_MAGIC_TEMP: Final = (
    -1.0
)  # Magic temperature value to signal OFF mode in merged overlays

# Temperature Limits
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
API_RESET_MIN_PERCENT: Final = (
    0.80  # Minimum % to consider valid reset (guards against throttled 0→1 edge case)
)
API_RESET_MIN_PLANNING_HOURS: Final = 20  # Minimum hours to plan ahead (conservative)
API_RESET_MAX_PLANNING_HOURS: Final = (
    30  # Maximum hours to project ahead (prevent excessive stretching)
)
API_RESET_PATTERN_THRESHOLD: Final = 2  # Consecutive resets needed to learn pattern
API_RESET_HISTORY_SIZE: Final = 5  # Number of resets to keep in history
THROTTLE_RECOVERY_INTERVAL_S: Final = 900  # 15 minutes (Recovery check when throttled)

# Service Names
SERVICE_MANUAL_POLL = "manual_poll"
SERVICE_RESUME_ALL_SCHEDULES = "resume_all_schedules"
SERVICE_TURN_OFF_ALL_ZONES = "turn_off_all_zones"
SERVICE_BOOST_ALL_ZONES = "boost_all_zones"
SERVICE_SET_MODE = "set_mode"
SERVICE_SET_MODE_ALL = "set_mode_all_zones"
SERVICE_SET_WATER_HEATER_MODE = "set_water_heater_mode"
SERVICE_ADD_METER_READING = "add_meter_reading"


# Device Capabilities
CAPABILITY_INSIDE_TEMP: Final = "INSIDE_TEMPERATURE_MEASUREMENT"
TEMP_OFFSET_ATTR: Final = "temperatureOffset"

# Device Type Mapping (Single Source of Truth)
DEVICE_TYPE_MAP: Final[dict[str, str]] = {
    "GW": "Gateway (V2)",
    "IB01": "Internet Bridge",
    "IB02": "Bridge X",
    "GW01": "Internet Bridge (Gateway)",
    "VA01": "Smart Radiator Thermostat",
    "VA02": "Smart Radiator Thermostat",
    "VA04": "Smart Radiator Thermostat X",
    "RU01": "Smart Thermostat",
    "RU02": "Smart Thermostat",
    "RU04": "Smart Thermostat X",
    "WR02": "Wireless Receiver",
    "TR04": "Wireless Receiver X",
    "BU01": "Smart Radiator Thermostat (Vertical)",
    "SU04": "Temperature Sensor X",
}


# Helper to extract device type keys from map (validates existence)
def _get_device_type(code: str) -> str:
    """Get device type code from map (validates it exists)."""
    if code not in DEVICE_TYPE_MAP:
        raise ValueError(f"Device type {code} not in DEVICE_TYPE_MAP")
    return code


# Commonly used device type codes (derived from map keys, no duplication)
DEVICE_TYPE_GW: Final = _get_device_type("GW")
DEVICE_TYPE_IB01: Final = _get_device_type("IB01")
DEVICE_TYPE_IB02: Final = _get_device_type("IB02")
DEVICE_TYPE_GW01: Final = _get_device_type("GW01")
DEVICE_TYPE_VA01: Final = _get_device_type("VA01")
DEVICE_TYPE_RU01: Final = _get_device_type("RU01")

# Device type patterns
DEVICE_SUFFIX_TADO_X: Final = (
    "04"  # Tado X devices end with 04 (VA04, RU04, TR04, SU04)
)
DEVICE_PREFIX_BRIDGE: Final = "IB"  # Bridge devices start with IB (IB01, IB02)

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
