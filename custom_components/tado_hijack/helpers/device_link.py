"""Shared identifier helpers for HomeKit / Matter serial matching."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from homeassistant.helpers.device_registry import DeviceEntry

from ..const import IDENTIFIER_DOMAIN_KIND_VALUE, IDENTIFIER_NS_VALUE
from .logging_utils import get_redacted_logger

_LOGGER = get_redacted_logger(__name__)


def identifier_root(namespace: str) -> str:
    """Return the integration domain from an identifier namespace."""
    return namespace.split(":", 1)[0]


def normalize_serial(serial_no: str) -> str:
    """Return a comparable serial, or empty if none."""
    return serial_no.strip().upper() if serial_no else ""


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
