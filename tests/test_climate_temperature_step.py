"""Regression tests for climate target temperature precision."""

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "tado_hijack"
    / "climate_entity.py"
)


def load_temperature_method():
    """Load the actual method without initializing Home Assistant."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    methods = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "async_set_temperature"
    ]
    assert len(methods) == 1

    method = methods[0]
    method.decorator_list = []
    module = ast.Module(body=[method], type_ignores=[])

    namespace = {
        "Any": object,
        "ATTR_TEMPERATURE": "temperature",
        "POWER_ON": "ON",
        "OVERLAY_ROOM": "room",
        "TadoAirConditioning": type("TadoAirConditioning", (), {}),
    }

    exec(compile(module, str(SOURCE), "exec"), namespace)
    return namespace["async_set_temperature"]


@pytest.mark.parametrize(
    ("temperature", "step", "expected"),
    [
        (17.5, 0.5, 17.5),
        (18.5, 0.5, 18.5),
        (19.5, 0.5, 19.5),
        (20.5, 0.5, 20.5),
        (19.0, 0.5, 19.0),
        (19.4, 0.5, 19.5),
        (19.4, 1.0, 19.0),
        (19.6, 1.0, 20.0),
        (19.6, None, 20.0),
    ],
)
def test_target_temperature_precision(temperature, step, expected):
    """Preserve supported temperature increments."""
    coordinator = SimpleNamespace(async_set_multiple_zone_overlays=AsyncMock())

    entity = SimpleNamespace(
        target_temperature_step=step,
        _zone_id=1,
        _store_last_state=Mock(),
        tado_coordinator=coordinator,
    )

    method = load_temperature_method()

    asyncio.run(method(entity, temperature=temperature))

    entity._store_last_state.assert_called_once_with(
        "target_temperature", float(expected)
    )

    coordinator.async_set_multiple_zone_overlays.assert_awaited_once_with(
        zone_ids=[1],
        power="ON",
        temperature=expected,
        overlay_mode="room",
        ac_mode=None,
    )


def test_missing_temperature_is_ignored():
    """Do not send an overlay without a temperature."""
    coordinator = SimpleNamespace(async_set_multiple_zone_overlays=AsyncMock())

    entity = SimpleNamespace(
        target_temperature_step=0.5,
        _zone_id=1,
        _store_last_state=Mock(),
        tado_coordinator=coordinator,
    )

    asyncio.run(load_temperature_method()(entity))

    coordinator.async_set_multiple_zone_overlays.assert_not_awaited()
    entity._store_last_state.assert_not_called()
