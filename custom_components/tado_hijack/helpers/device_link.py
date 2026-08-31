"""Shared identifier helpers for HomeKit / Matter serial matching."""

from __future__ import annotations

from collections.abc import Iterable

from homeassistant.helpers.device_registry import DeviceEntry


def identifier_root(domain: str) -> str:
    """Return the identifier domain without an HA suffix.

    HomeKit uses ``homekit_controller:accessory-id``; Matter uses ``matter``.
    """
    return domain.split(":", 1)[0]


def normalize_serial(serial_no: str) -> str:
    """Return a comparable serial, or empty if none."""
    return serial_no.strip().upper() if serial_no else ""


def has_local_domain(device: DeviceEntry, domains: Iterable[str]) -> bool:
    """Return True if the device has an identifier in the given domains."""
    allowed = frozenset(domains)
    return any(
        identifier_root(domain) in allowed for domain, _ident in device.identifiers
    )


def serial_equals(value: str | None, needle: str) -> bool:
    """Return True if value is the cloud serial."""
    return isinstance(value, str) and normalize_serial(value) == needle
