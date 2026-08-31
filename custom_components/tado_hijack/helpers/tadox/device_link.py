"""Matter local-device matching for Tado X."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntry

from ..device_link import (
    has_local_domain,
    identifier_root,
    normalize_serial,
    serial_equals,
)

LOCAL_ID_DOMAINS = frozenset({"matter"})


def matches_serial(device: DeviceEntry, serial_no: str) -> bool:
    """Return True if this Matter device carries the cloud serial."""
    needle = normalize_serial(serial_no)
    if not needle or not has_local_domain(device, LOCAL_ID_DOMAINS):
        return False
    if serial_equals(device.serial_number, needle):
        return True
    for domain, ident in device.identifiers:
        if identifier_root(domain) not in LOCAL_ID_DOMAINS:
            continue
        if serial_equals(ident, needle):
            return True
        if (
            isinstance(ident, str)
            and normalize_serial(ident).removeprefix("SERIAL_") == needle
        ):
            return True
    name = device.name
    return isinstance(name, str) and needle in name.upper()
