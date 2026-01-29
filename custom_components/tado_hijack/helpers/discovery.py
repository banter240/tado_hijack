"""Discovery helpers for Tado Hijack."""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tadoasync.models import Device, Zone
    from ..coordinator import TadoDataUpdateCoordinator


def yield_zones(
    coordinator: TadoDataUpdateCoordinator,
    include_types: set[str] | None = None,
) -> Generator[Zone, None, None]:
    """Yield zones matching specified types."""
    for zone in coordinator.zones_meta.values():
        if include_types is None or zone.type in include_types:
            yield zone


def yield_devices(
    coordinator: TadoDataUpdateCoordinator,
    include_zone_types: set[str] | None = None,
    capability: str | None = None,
) -> Generator[tuple[Device, int], None, None]:
    """Yield devices matching zone types and capabilities.

    Returns a tuple of (Device, zone_id).
    """
    seen_devices: set[str] = set()
    for zone in coordinator.zones_meta.values():
        if include_zone_types is not None and zone.type not in include_zone_types:
            continue

        for device in zone.devices:
            if device.serial_no in seen_devices:
                continue

            if capability:
                caps = getattr(device.characteristics, "capabilities", []) or []
                if capability not in caps:
                    continue

            seen_devices.add(device.serial_no)
            yield device, zone.id
