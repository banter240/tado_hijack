"""Tado X device type filter.

Second-generation hardware reports a type ending in 05 (the Wireless
Temperature Sensor X reports SU05). It is the same product line and must
be discovered and linked like the 04 devices.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from custom_components.tado_hijack.const import DEVICE_TYPE_MAP
from custom_components.tado_hijack.helpers.tadox.mapper import TadoXMapper


@pytest.fixture
def mapper() -> TadoXMapper:
    return TadoXMapper(cast(Any, None))


@pytest.mark.parametrize("device_type", ["VA04", "RU04", "SU04", "TR04", "PR04"])
def test_first_generation_devices_are_compatible(
    mapper: TadoXMapper, device_type: str
) -> None:
    assert mapper.is_device_compatible(device_type)


def test_second_generation_sensor_is_compatible(mapper: TadoXMapper) -> None:
    assert mapper.is_device_compatible("SU05")


def test_bridge_x_is_compatible(mapper: TadoXMapper) -> None:
    assert mapper.is_device_compatible("IB02")


@pytest.mark.parametrize(
    "device_type", ["VA01", "VA02", "RU01", "RU02", "WR02", "BU01", "IB01", "GW"]
)
def test_classic_devices_are_not_compatible(
    mapper: TadoXMapper, device_type: str
) -> None:
    assert not mapper.is_device_compatible(device_type)


def test_second_generation_sensor_has_a_model_name() -> None:
    assert DEVICE_TYPE_MAP["SU05"] == "Temperature Sensor X"
