"""Unit tests for serial matching and v3 devices_meta keying."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any, cast

from custom_components.tado_hijack.helpers.device_link import serial_equals
from custom_components.tado_hijack.helpers.tadov3.mapper import TadoV3Mapper


class TestSerialEquals:
    def test_exact_match(self) -> None:
        assert serial_equals("SU0347549696", "SU0347549696")

    def test_normalizes_case_and_whitespace(self) -> None:
        assert serial_equals(" su0347549696 ", "SU0347549696")

    def test_long_cloud_serial_matches_tail(self) -> None:
        # Old RU units: long factory serial in the cloud, tail via HomeKit
        assert serial_equals("RU1411FT0105RU2023817216", "RU2023817216")

    def test_match_works_in_both_argument_orders(self) -> None:
        assert serial_equals("RU2023817216", "RU1411FT0105RU2023817216")

    def test_short_tails_do_not_match(self) -> None:
        assert not serial_equals("RU7216", "RU1411FT0105RU2023817216")
        assert not serial_equals("RU1411FT0105RU2023817216", "RU7216")

    def test_unrelated_serials_do_not_match(self) -> None:
        assert not serial_equals("SU0347549696", "SU0347549697")
        assert not serial_equals("RU1411FT0105RU2023817216", "SU0347549696")

    def test_none_or_empty_never_matches(self) -> None:
        assert not serial_equals(None, "SU0347549696")
        assert not serial_equals("", "")
        assert not serial_equals("SU0347549696", "")


class TestV3MapperKeying:
    def test_devices_meta_keyed_by_long_serial(self) -> None:
        devices = [
            SimpleNamespace(
                serial_no="SU0347549696",
                short_serial_no="SU0347549696",
            ),
            SimpleNamespace(
                serial_no="RU1411FT0105RU2023817216",
                short_serial_no="RU2023817216",
            ),
        ]
        client = SimpleNamespace(
            get_zones=_async_return([SimpleNamespace(id=1)]),
            get_devices=_async_return(devices),
        )
        mapper = TadoV3Mapper(cast(Any, client))
        _zones, keyed = asyncio.run(mapper.async_fetch_metadata())
        assert set(keyed) == {"SU0347549696", "RU1411FT0105RU2023817216"}
        assert keyed["RU1411FT0105RU2023817216"].short_serial_no == "RU2023817216"


def _async_return(items: Sequence[object]) -> Any:
    async def run() -> Sequence[object]:
        return items

    return run
