"""Tests for the Classic boiler flow temperature rescue (client-side)."""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.tado_hijack.definitions import (
    _boiler_flow_supported,
    _find_boiler_flow_temp,
)


def _coord(states: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(data=SimpleNamespace(zone_states=states))


def test_reports_flow_from_reporting_zone() -> None:
    c = _coord(
        {
            "1": SimpleNamespace(boiler_flow_temp=52.5),
            "2": SimpleNamespace(),
        }
    )
    found = _find_boiler_flow_temp(c)
    assert found == (52.5, "1")
    assert _boiler_flow_supported(c)


def test_no_flow_reported_means_unsupported() -> None:
    c = _coord({"1": SimpleNamespace(), "2": SimpleNamespace()})
    assert _find_boiler_flow_temp(c) is None
    assert not _boiler_flow_supported(c)


def test_empty_states_mean_unsupported() -> None:
    c = _coord({})
    assert not _boiler_flow_supported(c)


def test_zero_flow_is_still_a_reading() -> None:
    c = _coord({"1": SimpleNamespace(boiler_flow_temp=0.0)})
    assert _find_boiler_flow_temp(c) == (0.0, "1")


def test_float_coercion() -> None:
    c = _coord({"1": SimpleNamespace(boiler_flow_temp="61.25")})
    assert _find_boiler_flow_temp(c) == (61.25, "1")
