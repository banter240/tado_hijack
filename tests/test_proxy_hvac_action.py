"""Action shown on the reverse-linked climate clone.

A Tado X Wireless Temperature Sensor reports no hvac_action over Matter,
so the clone falls back to the zone poll: power off is off, heating power
above 0 is heating, 0 is idle. Stale room states, an unknown source and
air conditioning show no action.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from homeassistant.components.climate import HVACAction, HVACMode

from custom_components.tado_hijack.helpers.local_proxy import proxy_hvac_action
from custom_components.tado_hijack.helpers.zone_utils import zone_states_are_live
from custom_components.tado_hijack.lib.tadox_models import TadoXZoneState


def _zone(percentage: float | None, power: str = "ON") -> SimpleNamespace:
    """Classic-shaped zone state: heating power under activity_data_points."""
    heating = None if percentage is None else SimpleNamespace(percentage=percentage)
    return SimpleNamespace(
        setting=SimpleNamespace(power=power),
        activity_data_points=SimpleNamespace(heating_power=heating),
    )


def _ac_zone(power: str = "ON") -> SimpleNamespace:
    """Classic air-conditioning zone: ac_power, no heating power."""
    return SimpleNamespace(
        setting=SimpleNamespace(power=power),
        activity_data_points=SimpleNamespace(
            ac_power=SimpleNamespace(value="ON"), heating_power=None
        ),
    )


def _tadox_zone(percentage: int, power: str = "ON") -> TadoXZoneState:
    payload: dict[str, Any] = {
        "id": 3,
        "name": "Living Room",
        "setting": {"power": power},
        "heatingPower": {"percentage": percentage},
    }
    return TadoXZoneState.model_validate(payload)


def test_source_action_wins_over_heating_power() -> None:
    assert proxy_hvac_action("idle", HVACMode.HEAT, _zone(60)) == HVACAction.IDLE


def test_source_action_wins_even_when_off() -> None:
    assert proxy_hvac_action("heating", HVACMode.OFF, _zone(0)) == HVACAction.HEATING


def test_heating_power_above_zero_is_heating() -> None:
    assert proxy_hvac_action(None, HVACMode.HEAT, _zone(1)) == HVACAction.HEATING


def test_zero_heating_power_is_idle() -> None:
    assert proxy_hvac_action(None, HVACMode.HEAT, _zone(0)) == HVACAction.IDLE


def test_auto_mode_uses_heating_power() -> None:
    assert proxy_hvac_action(None, HVACMode.AUTO, _zone(25)) == HVACAction.HEATING


def test_off_mode_is_off() -> None:
    assert proxy_hvac_action(None, HVACMode.OFF, _zone(40)) == HVACAction.OFF


def test_zone_powered_off_is_off_in_auto() -> None:
    zone = _zone(0, power="OFF")
    assert proxy_hvac_action(None, HVACMode.AUTO, zone) == HVACAction.OFF


def test_unknown_source_action_falls_back() -> None:
    assert proxy_hvac_action("bogus", HVACMode.HEAT, _zone(5)) == HVACAction.HEATING


def test_failed_poll_shows_no_action() -> None:
    zone = _zone(60)
    assert proxy_hvac_action(None, HVACMode.HEAT, zone, cloud_live=False) is None


def test_no_zone_data_shows_no_action() -> None:
    assert proxy_hvac_action(None, HVACMode.HEAT, None) is None
    assert proxy_hvac_action(None, HVACMode.HEAT, _zone(None)) is None


def test_real_tado_x_zone_state() -> None:
    assert proxy_hvac_action(None, HVACMode.HEAT, _tadox_zone(62)) == HVACAction.HEATING
    assert proxy_hvac_action(None, HVACMode.HEAT, _tadox_zone(0)) == HVACAction.IDLE
    off = _tadox_zone(0, power="OFF")
    assert proxy_hvac_action(None, HVACMode.AUTO, off) == HVACAction.OFF


def test_unknown_source_shows_no_action() -> None:
    assert proxy_hvac_action(None, None, _zone(60)) is None


def test_air_conditioning_zone_gets_no_fallback() -> None:
    assert proxy_hvac_action(None, HVACMode.COOL, _ac_zone()) is None


def test_air_conditioning_zone_powered_off_is_off() -> None:
    assert proxy_hvac_action(None, HVACMode.AUTO, _ac_zone("OFF")) == HVACAction.OFF


def test_room_states_within_two_polls_are_live() -> None:
    assert zone_states_are_live(1199, 600)
    assert not zone_states_are_live(1201, 600)


def test_short_interval_uses_five_minute_floor() -> None:
    assert zone_states_are_live(290, 20)
    assert not zone_states_are_live(310, 20)


def test_long_interval_is_capped_at_four_hours() -> None:
    assert zone_states_are_live(4 * 3600, 3 * 3600)
    assert not zone_states_are_live(4 * 3600 + 1, 3 * 3600)


def test_polling_off_uses_four_hour_cap() -> None:
    assert zone_states_are_live(3600, None)
    assert not zone_states_are_live(4 * 3600 + 1, None)


def test_no_room_states_yet_is_not_live() -> None:
    assert not zone_states_are_live(None, 60)
