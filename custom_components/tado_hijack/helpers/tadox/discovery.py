"""Discovery helpers for Tado X devices."""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...coordinator import TadoDataUpdateCoordinator


def yield_tadox_devices(
    coordinator: TadoDataUpdateCoordinator,
    include_zone_types: set[str] | list[str] | None = None,
    capability: str | None = None,
) -> Generator[tuple[Any, int]]:
    """Yield Tado X devices matching capabilities.

    Tado X specific implementation - uses room_id instead of zone.id.

    Returns:
        Generator of (TadoXDevice, room_id) tuples

    """
    from ...const import DEVICE_PREFIX_BRIDGE, DEVICE_TYPE_GW01
    from ...lib.tadox_models import HopsRoomSnapshot

    seen_devices: set[str] = set()

    # Tado X: zones_meta contains HopsRoomSnapshot objects
    for room in coordinator.zones_meta.values():
        # Type narrowing for Tado X
        if not isinstance(room, HopsRoomSnapshot):
            continue
        # Note: include_zone_types is ignored for Tado X (no zone.type concept)

        for device in room.devices:
            if device.serial_no in seen_devices:
                continue

            # Exclude bridges from general device scope
            dtype = getattr(device, "device_type", "")
            if dtype.startswith(DEVICE_PREFIX_BRIDGE) or dtype == DEVICE_TYPE_GW01:
                continue

            # Provider compatibility check
            if coordinator.provider and not coordinator.provider.is_device_compatible(
                dtype
            ):
                continue

            # Capability filtering
            if capability:
                caps = getattr(device.characteristics, "capabilities", []) or []
                if capability not in caps:
                    continue

            seen_devices.add(device.serial_no)
            yield device, room.room_id  # Tado X uses room_id
