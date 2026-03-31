"""Pydantic models for Tado X aligned with original v3 parser structures."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from ..const import CAPABILITY_INSIDE_TEMP, SERIAL_SHORT_LENGTH

# --- Helper for nested activityDataPoints (v3 compatibility) ---


class HopsHeatingPower(BaseModel):
    """Heating power percentage."""

    percentage: int


# --- Helper for nested characteristics (v3 compatibility) ---


class HopsCharacteristics(BaseModel):
    """Simulates v3 characteristics structure."""

    capabilities: list[str] = []


# --- Hops Internal Components ---


class HopsConnection(BaseModel):
    """Model for device connection state."""

    state: str  # "CONNECTED" or "DISCONNECTED"
    # Future: Add timestamp or other fields if API provides them


class HopsTemperature(BaseModel):
    """Model for temperature values."""

    value: float

    @property
    def celsius(self) -> float:
        """Compatibility property for v3 code that expects .celsius attribute."""
        return self.value


class HopsHumidity(BaseModel):
    """Model for humidity values."""

    percentage: float


class HopsSensorData(BaseModel):
    """Model for room sensor data points."""

    inside_temperature: HopsTemperature = Field(alias="insideTemperature")
    humidity: HopsHumidity


class HopsSetting(BaseModel):
    """Model for room settings."""

    power: str
    temperature: HopsTemperature | None = None
    mode: str | None = None  # AC mode if present (COOL, HEAT, DRY, FAN, AUTO)
    type: str | None = None  # Setting type (HEATING, AIR_CONDITIONING)
    fan_level: str | None = Field(None, alias="fanLevel")
    fan_speed: str | None = Field(None, alias="fanSpeed")
    vertical_swing: str | None = Field(None, alias="verticalSwing")
    horizontal_swing: str | None = Field(None, alias="horizontalSwing")


class NextTimeBlock(BaseModel):
    """Model for next time block in schedule."""

    start: str  # ISO datetime format


class NextScheduleChangeSetting(BaseModel):
    """Model for next schedule change setting."""

    power: str | None = None
    temperature: HopsTemperature | None = None


class NextScheduleChange(BaseModel):
    """Model for next schedule change."""

    start: str  # ISO datetime format
    setting: NextScheduleChangeSetting


class ManualControlTermination(BaseModel):
    """Model for manual control termination (boost mode, overlay)."""

    type: str
    remaining_time_in_seconds: int | None = Field(None, alias="remainingTimeInSeconds")
    projected_expiry: str | None = Field(None, alias="projectedExpiry")  # ISO datetime


# --- Implementation for Rooms (Operational) ---


class TadoXZoneState(BaseModel):
    """Standardized Tado X Zone State matching v3 naming and structure."""

    room_id: int = Field(alias="id")
    name: str
    sensor_data_points: HopsSensorData = Field(alias="sensorDataPoints")
    setting: HopsSetting
    heating_power: HopsHeatingPower | None = Field(None, alias="heatingPower")
    connection: HopsConnection | None = None
    open_window: Any | None = Field(None, alias="openWindow")
    manual_control_termination: ManualControlTermination | None = Field(
        None, alias="manualControlTermination"
    )
    next_time_block: NextTimeBlock | None = Field(None, alias="nextTimeBlock")
    next_schedule_change: NextScheduleChange | None = Field(
        None, alias="nextScheduleChange"
    )
    boost_mode: ManualControlTermination | None = Field(None, alias="boostMode")
    balance_control: str | None = Field(None, alias="balanceControl")

    # Duck-Typing Properties for original v3 sensors
    @property
    def current_temp(self) -> float | None:
        """Return current temperature."""
        return self.sensor_data_points.inside_temperature.value

    @property
    def current_humidity(self) -> float | None:
        """Return current humidity."""
        return self.sensor_data_points.humidity.percentage

    @property
    def power(self) -> str:
        """Return power state."""
        return self.setting.power

    @property
    def connection_state(self) -> str:
        """Return connection state."""
        return self.connection.state if self.connection else "UNKNOWN"

    @property
    def open_window_detected(self) -> bool:
        """Return whether an open window is detected."""
        if self.open_window:
            return getattr(self.open_window, "activated", False)
        return False

    @property
    def overlay_active(self) -> bool:
        """Return whether a manual overlay is active."""
        return self.manual_control_termination is not None

    @property
    def activity_data_points(self) -> Any:
        """V3 compatibility wrapper."""

        class ActivityDataPoints:
            def __init__(self, heating_power: HopsHeatingPower | None):
                self.heating_power = heating_power

        return ActivityDataPoints(self.heating_power)


# --- Implementation for Devices (Metadata) ---


class TadoXDevice(BaseModel):
    """Standardized Tado X Device matching v3 naming."""

    serial_no: str = Field(alias="serialNumber")
    device_type: str = Field(alias="type")
    current_fw_version: str = Field(alias="firmwareVersion")
    connection: HopsConnection
    battery_state: str | None = Field(None, alias="batteryState")
    child_lock_enabled: bool | None = Field(None, alias="childLockEnabled")
    characteristics: HopsCharacteristics = Field(default_factory=HopsCharacteristics)
    temperature_offset: float | None = Field(None, alias="temperatureOffset")

    @model_validator(mode="after")
    def _infer_capabilities(self) -> TadoXDevice:
        """Infer v3-style capabilities from available device data fields."""
        if self.temperature_offset is not None:
            caps = self.characteristics.capabilities
            if CAPABILITY_INSIDE_TEMP not in caps:
                self.characteristics.capabilities = [*caps, CAPABILITY_INSIDE_TEMP]
        return self

    @property
    def short_serial_no(self) -> str:
        """Return short serial number (last 6 characters) for device identification."""
        return (
            self.serial_no[-SERIAL_SHORT_LENGTH:]
            if len(self.serial_no) >= SERIAL_SHORT_LENGTH
            else self.serial_no
        )

    @property
    def connection_state(self) -> Any:
        """Match v3 Enum structure (obj.connection_state.value)."""
        return type("State", (), {"value": self.connection.state == "CONNECTED"})


class HopsRoomSnapshot(BaseModel):
    """Model for a room snapshot within roomsAndDevices."""

    room_id: int = Field(alias="roomId")
    room_name: str = Field(alias="roomName")
    devices: list[TadoXDevice]


class HomePresence(BaseModel):
    """Model for home presence information."""

    presence: str  # "HOME", "AWAY", etc.


class HopsRoomsAndDevicesResponse(BaseModel):
    """Model for full roomsAndDevices response."""

    rooms: list[HopsRoomSnapshot]
    other_devices: list[TadoXDevice] = Field(alias="otherDevices")
    home: HomePresence | None = None  # Presence information
