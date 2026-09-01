"""Matter local-device matching for Tado X."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntry

from ..device_link import (
    has_local_domain,
    identifier_pairs,
    identifier_root,
    normalize_serial,
    serial_equals,
    serial_in_identifiers,
)

LOCAL_ID_DOMAINS = frozenset({"matter"})
_MATTER_SERIAL_PREFIX = "SERIAL_"


def matches_serial(device: DeviceEntry, serial_no: str) -> bool:
    """Return True if this Matter device carries the cloud serial."""
    needle = normalize_serial(serial_no)
    if not needle or not has_local_domain(device, LOCAL_ID_DOMAINS):
        return False
    if serial_equals(device.serial_number, needle) or serial_in_identifiers(
        device, needle, LOCAL_ID_DOMAINS
    ):
        return True
    for namespace, ident in identifier_pairs(device.identifiers):
        if identifier_root(namespace) not in LOCAL_ID_DOMAINS:
            continue
        if normalize_serial(ident).removeprefix(_MATTER_SERIAL_PREFIX) == needle:
            return True
    name = device.name
    return isinstance(name, str) and needle in name.upper()
