"""Unit tests for serial matching and v3 devices_meta keying."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any, cast

from custom_components.tado_hijack.helpers.device_link import serial_equals
from custom_components.tado_hijack.helpers.device_linker import (
    _serial_aliases,
    _serial_candidates,
    update_serial_aliases,
)
from custom_components.tado_hijack.helpers.tadov3.device_link import matches_serial
from custom_components.tado_hijack.helpers.tadov3.mapper import TadoV3Mapper


class TestSerialEquals:
    def test_exact_match(self) -> None:
        assert serial_equals("SU0001112233", "SU0001112233")

    def test_normalizes_case_and_whitespace(self) -> None:
        assert serial_equals(" su0001112233 ", "SU0001112233")

    def test_short_serial_is_no_tail_of_long_serial(self) -> None:
        # Old RU shape: the short serial shares only the prefix, not the tail.
        assert not serial_equals("RU9988776655", "RU0000ZZ00009988776655")
        assert not serial_equals("RU0000ZZ00009988776655", "RU9988776655")

    def test_unrelated_serials_do_not_match(self) -> None:
        assert not serial_equals("SU0001112233", "SU0001112244")

    def test_none_or_empty_never_matches(self) -> None:
        assert not serial_equals(None, "SU0001112233")
        assert not serial_equals("", "")


class TestShortSerialAlias:
    def test_alias_expands_the_candidate_set(self) -> None:
        update_serial_aliases(
            {
                "RU0000ZZ00009988776655": SimpleNamespace(
                    serial_no="RU0000ZZ00009988776655",
                    short_serial_no="RU9988776655",
                )
            }
        )
        try:
            assert _serial_candidates("RU0000ZZ00009988776655") == (
                "RU0000ZZ00009988776655",
                "RU9988776655",
            )
            assert _serial_candidates("su0001112233") == ("SU0001112233",)
            assert _serial_candidates("") == ()
        finally:
            _serial_aliases.pop("RU0000ZZ00009988776655", None)

    def test_equal_serials_add_no_alias(self) -> None:
        update_serial_aliases(
            {
                "SU0001112233": SimpleNamespace(
                    serial_no="SU0001112233",
                    short_serial_no="SU0001112233",
                )
            }
        )
        try:
            assert _serial_candidates("SU0001112233") == ("SU0001112233",)
        finally:
            _serial_aliases.pop("SU0001112233", None)
            assert not _serial_aliases


class TestHomeKitMatching:
    def test_short_serial_candidate_matches_homekit_device(self) -> None:
        device = SimpleNamespace(
            serial_number="RU9988776655",
            identifiers=(
                ["homekit_controller:accessory-id", "aa:bb:cc:dd:ee:ff:aid:10"],
            ),
        )
        assert matches_serial(cast(Any, device), "RU9988776655")

    def test_long_serial_alone_never_matches_a_short_homekit_device(self) -> None:
        device = SimpleNamespace(
            serial_number="RU9988776655",
            identifiers=(
                ["homekit_controller:accessory-id", "aa:bb:cc:dd:ee:ff:aid:10"],
            ),
        )
        assert not matches_serial(cast(Any, device), "RU0000ZZ00009988776655")


class TestV3MapperKeying:
    def test_devices_meta_keyed_by_long_serial(self) -> None:
        devices = [
            SimpleNamespace(
                serial_no="SU0001112233",
                short_serial_no="SU0001112233",
            ),
            SimpleNamespace(
                serial_no="RU0000ZZ00009988776655",
                short_serial_no="RU9988776655",
            ),
        ]
        client = SimpleNamespace(
            get_zones=_async_return([SimpleNamespace(id=1)]),
            get_devices=_async_return(devices),
        )
        mapper = TadoV3Mapper(cast(Any, client))
        _zones, keyed = asyncio.run(mapper.async_fetch_metadata())
        assert set(keyed) == {
            "SU0001112233",
            "RU0000ZZ00009988776655",
        }
        assert keyed["RU0000ZZ00009988776655"].short_serial_no == "RU9988776655"


def _async_return(items: Sequence[object]) -> Any:
    async def run() -> Sequence[object]:
        return items

    return run
