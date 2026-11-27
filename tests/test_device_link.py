"""Unit tests for serial matching and v3 devices_meta keying."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from homeassistant.core import HomeAssistant
from pytest import MonkeyPatch

from custom_components.tado_hijack.helpers.device_link import serial_equals
from custom_components.tado_hijack.helpers.device_linker import (
    _serial_aliases,
    _serial_candidates,
    get_zone_device_link,
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


class TestZoneDeviceLink:
    """get_zone_device_link resolves parent zone links for DeviceInfo kwargs."""

    def test_registered_zone_returns_link(self, monkeypatch: MonkeyPatch) -> None:
        seen: dict[str, object] = {}

        def fake_lookup(
            hass: object,
            identifier: tuple[str, str],
            *,
            config_entry_id: str,
        ) -> str:
            seen["identifier"] = identifier
            seen["config_entry_id"] = config_entry_id
            return "device-42"

        monkeypatch.setattr(
            "custom_components.tado_hijack.helpers.device_linker.dr"
            ".async_get_device_id_by_identifier",
            fake_lookup,
        )

        link = get_zone_device_link(cast(HomeAssistant, object()), "entry-1", 3)

        assert link == {"via_device_id": "device-42"}
        assert seen["identifier"] == ("tado_hijack", "entry-1_zone_3")
        assert seen["config_entry_id"] == "entry-1"

    def test_unregistered_zone_returns_empty_mapping(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        def fake_lookup(
            hass: object,
            identifier: tuple[str, str],
            *,
            config_entry_id: str,
        ) -> str:
            raise ValueError("no device")

        monkeypatch.setattr(
            "custom_components.tado_hijack.helpers.device_linker.dr"
            ".async_get_device_id_by_identifier",
            fake_lookup,
        )

        assert get_zone_device_link(cast(HomeAssistant, object()), "entry-1", 3) == {}


class TestNoDeprecatedDeviceInfoWrites:
    """DeviceInfo metadata must be supplied via constructor kwargs, not item writes."""

    def test_no_via_device_id_item_assignment(self) -> None:
        component_dir = (
            Path(__file__).resolve().parent.parent / "custom_components" / "tado_hijack"
        )
        offenders = [
            str(path.relative_to(component_dir.parent))
            for path in sorted(component_dir.rglob("*.py"))
            if path.read_text(encoding="utf-8").count('["via_device_id"]')
        ]
        assert not offenders, (
            "DeviceInfo['via_device_id'] item assignment is deprecated since "
            "HA 2026.12 (removal 2027.12); pass via_device_id as a DeviceInfo "
            f"constructor kwarg instead. Offending files: {offenders}"
        )
