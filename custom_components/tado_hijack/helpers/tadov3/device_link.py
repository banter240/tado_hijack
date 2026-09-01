"""HomeKit local-device matching for classic Tado."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntry

from ..device_link import (
    has_local_domain,
    normalize_serial,
    serial_equals,
    serial_in_identifiers,
)

LOCAL_ID_DOMAINS = frozenset({"homekit", "homekit_controller"})


def matches_serial(device: DeviceEntry, serial_no: str) -> bool:
    """Return True if this HomeKit device carries the cloud serial."""
    needle = normalize_serial(serial_no)
    if not needle or not has_local_domain(device, LOCAL_ID_DOMAINS):
        return False
    return serial_equals(device.serial_number, needle) or serial_in_identifiers(
        device, needle, LOCAL_ID_DOMAINS
    )
