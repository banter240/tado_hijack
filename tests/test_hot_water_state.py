"""Regression tests for the Tado X hot water boost state parsing (issue #201).

The tado X app writes `BOOST` to the programmer state endpoint while its
own boost is running; integration-initiated boosts read back `BOOST_ON`.
"""

from __future__ import annotations

from custom_components.tado_hijack.lib.tadox_models import (
    TadoXHotWaterState,
    is_hot_water_boost,
)


def test_app_boost_state_is_boost() -> None:
    assert is_hot_water_boost("BOOST")


def test_integration_boost_state_is_boost() -> None:
    assert is_hot_water_boost("BOOST_ON")


def test_forced_off_is_not_boost() -> None:
    assert not is_hot_water_boost("BOOST_OFF")


def test_schedule_states_are_not_boost() -> None:
    assert not is_hot_water_boost("SCHEDULE_ON")
    assert not is_hot_water_boost("SCHEDULE_OFF")


def test_state_matching_is_case_insensitive() -> None:
    assert is_hot_water_boost(" boost ")


def test_empty_or_missing_state_is_not_boost() -> None:
    assert not is_hot_water_boost("")
    assert not is_hot_water_boost("NONE")


def test_model_is_boost_property_tracks_state() -> None:
    hw = TadoXHotWaterState.model_validate(
        {"state": "BOOST", "nextStateChange": "2026-11-15T08:46:00Z"}
    )
    assert hw.is_boost
    assert hw.overlay_active

    hw_off = TadoXHotWaterState.model_validate({"state": "SCHEDULE_OFF"})
    assert not hw_off.is_boost
    assert not hw_off.overlay_active
