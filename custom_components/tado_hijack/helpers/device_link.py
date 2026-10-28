"""Shared identifier helpers for HomeKit / Matter serial matching."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator

from homeassistant.helpers.device_registry import DeviceEntry

from ..const import DOMAIN, IDENTIFIER_DOMAIN_KIND_VALUE, IDENTIFIER_NS_VALUE
from .logging_utils import get_redacted_logger

_LOGGER = get_redacted_logger(__name__)


def device_identifier(value: str) -> tuple[str, str]:
    """Identifier this integration registers for one home, bridge, or serial."""
    return (DOMAIN, value)


def home_device_key(unique_id: str | None, entry_id: str) -> str:
    """Value half of the home device identifier."""
    return unique_id or entry_id


def home_device_identifier(unique_id: str | None, entry_id: str) -> tuple[str, str]:
    """Identifier registered for the home device."""
    return device_identifier(home_device_key(unique_id, entry_id))


def zone_device_identifier(entry_id: str, zone_id: object) -> tuple[str, str]:
    """Identifier registered for a zone device."""
    return device_identifier(f"{entry_id}_zone_{zone_id}")


def identifier_root(namespace: str) -> str:
    """Return the integration domain from an identifier namespace."""
    return namespace.split(":", 1)[0]


def normalize_serial(serial_no: str) -> str:
    """Return a comparable serial, or empty if none."""
    return serial_no.strip().upper() if serial_no else ""


_SERIAL_TOKEN = re.compile(r"(?i)^[a-z]{2,3}(?=[a-z0-9]*\d)[a-z0-9]{8,12}$")


def zone_id_from_device_key(value: str, entry_id: str) -> int | None:
    """Zone id from ``{entry_id}_zone_{id}``, or None."""
    prefix = f"{entry_id}_zone_"
    if not value.startswith(prefix):
        return None
    zone_id = value.removeprefix(prefix)
    return int(zone_id) if zone_id.isdigit() else None


def zone_id_from_unique_id(unique_id: str) -> int | None:
    """Zone id encoded in a Hijack unique id. Home entities have none."""
    parts = unique_id.split("_")
    for index, part in enumerate(parts[:-1]):
        if part == "zone" and parts[index + 1].isdigit():
            return int(parts[index + 1])
    tail = parts[-1]
    return int(tail) if tail.isdigit() else None


def serial_from_unique_id(unique_id: str) -> str | None:
    """Serial token encoded in a Hijack unique id."""
    return next(
        (
            normalize_serial(part)
            for part in unique_id.split("_")
            if _SERIAL_TOKEN.fullmatch(part)
        ),
        None,
    )


def parse_identifier(item: object) -> tuple[str, str] | None:
    """Parse a registry identifier into (namespace, value).

    Known shapes:
    - 2 fields: HA ``(namespace, value)``
    - 3 fields: HomeKit Controller legacy ``(domain, kind, value)``
      → ``(domain:kind, value)``, same as migrated HomeKit
    """
    if not isinstance(item, (list, tuple)):
        return None
    length = len(item)
    if length == IDENTIFIER_NS_VALUE:
        namespace, ident = item
    elif length == IDENTIFIER_DOMAIN_KIND_VALUE:
        domain, kind, ident = item
        if not isinstance(domain, str) or not isinstance(kind, str):
            return None
        namespace = f"{domain}:{kind}"
    else:
        _LOGGER.debug("Unsupported device identifier length %s", length)
        return None
    if not isinstance(namespace, str) or ident is None:
        return None
    return namespace, ident if isinstance(ident, str) else str(ident)


def identifier_pairs(identifiers: Iterable[object]) -> Iterator[tuple[str, str]]:
    """Yield parsed (namespace, value) pairs."""
    for item in identifiers:
        parsed = parse_identifier(item)
        if parsed is not None:
            yield parsed


def has_local_domain(device: DeviceEntry, domains: Iterable[str]) -> bool:
    """Return True if the device has an identifier in the given domains."""
    allowed = frozenset(domains)
    return any(
        identifier_root(namespace) in allowed
        for namespace, _ident in identifier_pairs(device.identifiers)
    )


def serial_equals(value: str | None, needle: str) -> bool:
    """Return True if value is the cloud serial."""
    return isinstance(value, str) and normalize_serial(value) == needle


def serial_in_identifiers(
    device: DeviceEntry, needle: str, domains: Iterable[str]
) -> bool:
    """Return True if a matching identifier value is the cloud serial."""
    allowed = frozenset(domains)
    return any(
        identifier_root(namespace) in allowed and serial_equals(ident, needle)
        for namespace, ident in identifier_pairs(device.identifiers)
    )
