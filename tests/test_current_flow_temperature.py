"""Regression tests for issue #213: current auto-adapted flow temperature sensor."""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.tado_hijack.definitions import (
    _flow_temp_supported,
    _get_current_flow_temperature,
    _get_flow_auto_adaptation,
    _get_max_flow_temperature,
)


def _coord(ft: object | None) -> SimpleNamespace:
    return SimpleNamespace(data=SimpleNamespace(flow_temp=ft))


def _ft(
    max_temp: float = 64.0,
    *,
    adapt_enabled: bool = True,
    adapt_value: float | None = 56.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        max_flow_temperature=max_temp,
        auto_adaptation=SimpleNamespace(
            enabled=adapt_enabled,
            max_flow_temperature=adapt_value,
        ),
    )


def test_current_flow_returns_adapted_value() -> None:
    c = _coord(_ft())
    assert _get_current_flow_temperature(c) == 56.0
    assert _flow_temp_supported(c)
    assert _get_flow_auto_adaptation(c) is True


def test_current_flow_none_when_adaptation_disabled() -> None:
    c = _coord(_ft(adapt_enabled=False, adapt_value=None))
    assert _get_current_flow_temperature(c) is None
    assert _get_flow_auto_adaptation(c) is False


def test_current_flow_without_settings_is_none() -> None:
    assert _get_current_flow_temperature(_coord(None)) is None


def test_adaptation_object_missing_is_none() -> None:
    ft = SimpleNamespace(max_flow_temperature=64.0, auto_adaptation=None)
    assert _get_current_flow_temperature(_coord(ft)) is None


def test_adapted_value_above_max_is_reported_as_is() -> None:
    """The sensor mirrors the API; clamping is the cloud's job."""
    c = _coord(_ft(max_temp=50.0, adapt_value=56.0))
    assert _get_current_flow_temperature(c) == 56.0
    assert _get_max_flow_temperature(c) == 50.0


def test_int_value_coerced_to_float() -> None:
    c = _coord(_ft(adapt_value=56))
    assert _get_current_flow_temperature(c) == 56.0
    assert isinstance(_get_current_flow_temperature(c), float)
