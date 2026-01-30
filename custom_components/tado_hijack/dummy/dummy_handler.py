"""Central handler for Tado Hijack Dummy Environment."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

from .const import DUMMY_ZONE_ID_AC, DUMMY_ZONE_ID_HOT_WATER

if TYPE_CHECKING:
    from ..coordinator import TadoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


class TadoDummyHandler:
    """Manages injection and interception for dummy zones."""

    def __init__(self, coordinator: TadoDataUpdateCoordinator) -> None:
        """Initialize the dummy handler."""
        self.coordinator = coordinator
        self._states: dict[int, Any] = {}
        self._init_dummy_states()

    def _init_dummy_states(self) -> None:
        """Initialize internal dummy state objects."""
        # 1. Hot Water Dummy
        self._states[DUMMY_ZONE_ID_HOT_WATER] = SimpleNamespace(
            setting=SimpleNamespace(
                type="HOT_WATER",
                power="OFF",
                temperature=SimpleNamespace(celsius=50.0, fahrenheit=122.0),
            ),
            overlay=None,
            overlay_active=False,
            sensor_data_points=SimpleNamespace(
                inside_temperature=SimpleNamespace(celsius=45.0, fahrenheit=113.0)
            ),
            activity_data_points=SimpleNamespace(
                heating_power=SimpleNamespace(percentage=0.0, type="PERCENTAGE")
            ),
            connection_state=SimpleNamespace(
                value=True, timestamp="2026-01-30T17:00:00Z"
            ),
            link=SimpleNamespace(
                state=f"/api/v2/homes/DUMMY/zones/{DUMMY_ZONE_ID_HOT_WATER}/state"
            ),
        )

        # 2. AC Dummy
        self._states[DUMMY_ZONE_ID_AC] = SimpleNamespace(
            setting=SimpleNamespace(
                type="AIR_CONDITIONING",
                power="OFF",
                temperature=SimpleNamespace(celsius=21.0, fahrenheit=69.8),
                mode="COOL",
                fan_speed="AUTO",
                vertical_swing="OFF",
                horizontal_swing="OFF",
                light="ON",
            ),
            overlay=None,
            overlay_active=False,
            sensor_data_points=SimpleNamespace(
                inside_temperature=SimpleNamespace(celsius=24.0, fahrenheit=75.2),
                humidity=SimpleNamespace(percentage=60.0),
            ),
            activity_data_points=SimpleNamespace(
                ac_power=SimpleNamespace(value="OFF", timestamp="2026-01-30T17:00:00Z")
            ),
            connection_state=SimpleNamespace(
                value=True, timestamp="2026-01-30T17:00:00Z"
            ),
            link=SimpleNamespace(
                state=f"/api/v2/homes/DUMMY/zones/{DUMMY_ZONE_ID_AC}/state"
            ),
        )

    def is_dummy_zone(self, zone_id: int) -> bool:
        """Check if a zone ID belongs to a dummy zone."""
        return zone_id in (DUMMY_ZONE_ID_AC, DUMMY_ZONE_ID_HOT_WATER)

    def split_zones(self, zone_ids: list[int]) -> tuple[list[int], list[int]]:
        """Split a list of zone IDs into real and dummy buckets."""
        real, dummy = [], []
        for zid in zone_ids:
            if self.is_dummy_zone(zid):
                dummy.append(zid)
            else:
                real.append(zid)
        return real, dummy

    def split_overlays(
        self, overlays: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Split a list of bulk overlays into real and dummy buckets."""
        real, dummy = [], []
        for ov in overlays:
            zid = ov.get("room")
            if isinstance(zid, int) and self.is_dummy_zone(zid):
                dummy.append(ov)
            else:
                real.append(ov)
        return real, dummy

    def filter_and_intercept_resume(self, zones: list[int]) -> list[int]:
        """Intercept dummy resumes and return remaining real zones."""
        real, dummy = self.split_zones(zones)
        for zid in dummy:
            self.intercept_command(zid, None)
        return real

    def filter_and_intercept_overlays(
        self, overlays: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Intercept dummy overlays and return remaining real overlays."""
        real, dummy = self.split_overlays(overlays)
        for ov in dummy:
            zid = cast(int, ov["room"])
            self.intercept_command(zid, ov["overlay"])
        return real

    def inject_metadata(
        self,
        zones: dict[int, Any],
        devices: dict[str, Any],
        capabilities: dict[int, Any],
    ) -> None:
        """Inject dummy zone metadata into real data."""
        _LOGGER.info("DUMMY ZONES ENABLED - Injecting fake zones")
        # Inject Hot Water Zone
        zones[DUMMY_ZONE_ID_HOT_WATER] = self._create_hw_metadata()
        capabilities[DUMMY_ZONE_ID_HOT_WATER] = self._create_hw_capabilities()

        # Inject AC Zone
        zones[DUMMY_ZONE_ID_AC] = self._create_ac_metadata()
        capabilities[DUMMY_ZONE_ID_AC] = self._create_ac_capabilities()

        # Inject mock devices for connectivity sensors  # [DUMMY_HOOK]
        for zid in (DUMMY_ZONE_ID_AC, DUMMY_ZONE_ID_HOT_WATER):
            serial = f"DUMMY_DEV_{zid}"
            devices[serial] = SimpleNamespace(
                serial_no=serial,
                short_serial_no=f"DUMMY{zid}",
                device_type="VA01" if zid == DUMMY_ZONE_ID_AC else "RU01",
                current_fw_version="1.0.0",
                connection_state=SimpleNamespace(
                    value=True, timestamp="2026-01-30T17:00:00Z"
                ),
                characteristics=SimpleNamespace(capabilities=[]),
                battery_state="NORMAL",
            )
            # Add device to its zone
            if zone := zones.get(zid):
                if not hasattr(zone, "devices") or not zone.devices:
                    zone.devices = [devices[serial]]

    def inject_states(self, states: dict[str, Any]) -> None:
        """Inject current dummy states into real state data."""
        for zid, state in self._states.items():
            self._update_activity(zid, state)
            states[str(zid)] = state

    def intercept_command(
        self, zone_id: int, overlay_data: dict[str, Any] | None
    ) -> bool:
        """Intercept a command if it targets a dummy zone. Returns True if handled."""
        if not self.is_dummy_zone(zone_id):
            return False

        _LOGGER.debug("Intercepted command for dummy zone %d", zone_id)
        state = self._states.get(zone_id)
        if not state:
            return True

        if overlay_data is None:
            state.overlay = None
            state.overlay_active = False
            return True

        state.overlay = overlay_data
        state.overlay_active = True

        new_setting = overlay_data.get("setting", {})
        if "power" in new_setting:
            state.setting.power = new_setting["power"]
        if "mode" in new_setting:
            state.setting.mode = new_setting["mode"]
        if "temperature" in new_setting and new_setting["temperature"]:
            state.setting.temperature = SimpleNamespace(
                celsius=new_setting["temperature"].get("celsius"),
                fahrenheit=new_setting["temperature"].get("fahrenheit"),
            )

        # Map AC specific settings (camelCase from payload to snake_case in state)
        key_map = {
            "fanSpeed": "fan_speed",
            "verticalSwing": "vertical_swing",
            "horizontalSwing": "horizontal_swing",
            "light": "light",
            "fanLevel": "fan_level",
        }
        for api_key, attr_name in key_map.items():
            if api_key in new_setting:
                setattr(state.setting, attr_name, new_setting[api_key])

        return True

    def get_away_configuration(self, zone_id: int) -> dict[str, Any]:
        """Return a mock away configuration."""
        return {
            "type": "HEATING",
            "preheatingLevel": "MEDIUM",
            "minimumAwayTemperature": {"celsius": 15.0, "fahrenheit": 59.0},
        }

    def get_capabilities(self, zone_id: int) -> Any:
        """Return mock capabilities for a zone."""
        if zone_id == DUMMY_ZONE_ID_HOT_WATER:
            return self._create_hw_capabilities()
        return self._create_ac_capabilities() if zone_id == DUMMY_ZONE_ID_AC else None

    def _update_activity(self, zone_id: int, state: Any) -> None:
        """Simulate device activity based on state."""
        if zone_id == DUMMY_ZONE_ID_AC:
            current_temp = getattr(
                state.sensor_data_points.inside_temperature, "celsius", 24.0
            )
            target_temp = getattr(state.setting.temperature, "celsius", None)
            mode = getattr(state.setting, "mode", "COOL")

            is_working = False
            if state.setting.power == "ON":
                if mode in ("COOL", "DRY") and target_temp is not None:
                    is_working = current_temp > target_temp
                elif mode == "HEAT" and target_temp is not None:
                    is_working = current_temp < target_temp
                else:
                    # FAN mode is always working if power is ON
                    is_working = True
            state.activity_data_points.ac_power.value = "ON" if is_working else "OFF"

        elif zone_id == DUMMY_ZONE_ID_HOT_WATER:
            is_on = state.setting.power == "ON"
            state.activity_data_points.heating_power = SimpleNamespace(
                percentage=100.0 if is_on else 0.0, type="PERCENTAGE"
            )

    def _create_hw_metadata(self) -> Any:
        class DummyZone:
            id = DUMMY_ZONE_ID_HOT_WATER
            name = "DUMMY Hot Water"
            type = "HOT_WATER"
            device_types = ["RU01"]
            devices: list[Any] = []

        return DummyZone()

    def _create_ac_metadata(self) -> Any:
        class DummyZone:
            id = DUMMY_ZONE_ID_AC
            name = "DUMMY Air Conditioning"
            type = "AIR_CONDITIONING"
            device_types = ["VA01"]
            devices: list[Any] = []

        return DummyZone()

    def _create_hw_capabilities(self) -> Any:
        return SimpleNamespace(
            type="HOT_WATER",
            temperatures=SimpleNamespace(
                celsius=SimpleNamespace(min=30, max=65, step=1.0)
            ),
        )

    def _create_ac_capabilities(self) -> Any:
        return SimpleNamespace(
            type="AIR_CONDITIONING",
            temperatures=SimpleNamespace(
                celsius=SimpleNamespace(min=16, max=30, step=1.0)
            ),
            cool=self._create_ac_mode_cap(),
            heat=self._create_ac_mode_cap(),
            fan=self._create_ac_mode_cap(fan_only=True),
            dry=self._create_ac_mode_cap(),
            auto=self._create_ac_mode_cap(),
        )

    def _create_ac_mode_cap(self, fan_only: bool = False) -> Any:
        return SimpleNamespace(
            fan_speeds=["HIGH", "LOW", "MIDDLE"]
            if fan_only
            else ["AUTO", "HIGH", "LOW", "MIDDLE"],
            fan_level=None,
            vertical_swing=["OFF", "ON"],
            horizontal_swing=["OFF", "ON"],
            swing=None,
            temperatures=None if fan_only else True,  # Just a marker
        )
