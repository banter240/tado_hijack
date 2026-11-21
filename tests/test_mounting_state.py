"""Tests for the mounting state diagnostic sensor definition."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from homeassistant.helpers.entity import EntityCategory

from custom_components.tado_hijack.definitions import ENTITY_DEFINITIONS
from custom_components.tado_hijack.models import TadoEntityDefinition


def _definition() -> TadoEntityDefinition:
    return next(d for d in ENTITY_DEFINITIONS if d["key"] == "mounting_state")


def _coord(device: object) -> SimpleNamespace:
    return SimpleNamespace(devices_meta={"SU0001112233": device})


def test_reports_the_raw_field() -> None:
    device = SimpleNamespace(mounting_state_with_error="CALIBRATED")
    value_fn = cast("Any", _definition()["value_fn"])
    assert value_fn(_coord(device), "SU0001112233") == "CALIBRATED"


def test_missing_device_yields_none() -> None:
    value_fn = cast("Any", _definition()["value_fn"])
    assert value_fn(_coord(SimpleNamespace()), "SU0001112233") is None


def test_supported_only_when_the_field_exists() -> None:
    is_supported = cast("Any", _definition()["is_supported_fn"])
    assert is_supported(
        _coord(SimpleNamespace(mounting_state_with_error="CALIBRATED")),
        "SU0001112233",
    )
    assert not is_supported(
        _coord(SimpleNamespace(mounting_state_with_error=None)), "SU0001112233"
    )
    assert not is_supported(_coord(SimpleNamespace()), "SU0001112233")


def test_is_a_device_scoped_diagnostic_sensor() -> None:
    definition = _definition()
    assert definition["platform"] == "sensor"
    assert definition["scope"] == "device"
    assert definition["entity_category"] == EntityCategory.DIAGNOSTIC
    assert definition["supported_generations"] == {"classic"}
