"""Discovery helpers for Tado Hijack."""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..coordinator import TadoDataUpdateCoordinator


def _yield_zones_v3(
    coordinator: TadoDataUpdateCoordinator,
    include_types: set[str] | None = None,
) -> Generator[Any, None, None]:
    """Yield v3 Classic zones matching specified types.

    v3 zones have a .type attribute (HEATING, AIR_CONDITIONING, HOT_WATER).
    """
    for zone in coordinator.zones_meta.values():
        if include_types is None or getattr(zone, "type", None) in include_types:
            yield zone


def _yield_zones_tadox(
    coordinator: TadoDataUpdateCoordinator,
) -> Generator[Any, None, None]:
    """Yield all Tado X rooms without type filtering.

    Tado X HopsRoomSnapshot has no .type attribute - all rooms are yielded.
    """
    yield from coordinator.zones_meta.values()


def yield_zones(
    coordinator: TadoDataUpdateCoordinator,
    include_types: set[str] | None = None,
    include_heating: bool = False,
    include_hot_water: bool = False,
    include_ac: bool = False,
) -> Generator[Any, None, None]:
    """Yield zones - generation-aware dispatcher.

    For Tado X: yields all rooms (no type filtering).
    For v3 Classic: yields zones matching include_types or boolean flags.

    Args:
        coordinator: Coordinator instance
        include_types: Explicit set of zone types (overrides boolean flags)
        include_heating: Include HEATING zones
        include_hot_water: Include HOT_WATER zones
        include_ac: Include AIR_CONDITIONING zones

    """
    from ..const import (
        GEN_X,
        ZONE_TYPE_AIR_CONDITIONING,
        ZONE_TYPE_HEATING,
        ZONE_TYPE_HOT_WATER,
    )

    # Build include_types from boolean flags if not explicitly provided
    if include_types is None and (include_heating or include_hot_water or include_ac):
        include_types = set()
        if include_heating:
            include_types.add(ZONE_TYPE_HEATING)
        if include_hot_water:
            include_types.add(ZONE_TYPE_HOT_WATER)
        if include_ac:
            include_types.add(ZONE_TYPE_AIR_CONDITIONING)

    if coordinator.generation == GEN_X:
        yield from _yield_zones_tadox(coordinator)
    else:
        yield from _yield_zones_v3(coordinator, include_types)


def get_bridges(
    devices: dict[str, Any] | list[Any],
    generation: str,
) -> list[Any]:
    """Get generation-specific bridges from device collection.

    Args:
        devices: Device dict (serial_no -> Device) or list of devices
        generation: GEN_CLASSIC or GEN_X

    Returns:
        List of bridge devices for the given generation.

    """
    from ..const import (
        DEVICE_TYPE_GW01,
        DEVICE_TYPE_IB01,
        DEVICE_TYPE_IB02,
        GEN_CLASSIC,
    )

    device_list = devices.values() if isinstance(devices, dict) else devices

    if generation == GEN_CLASSIC:
        return [
            d
            for d in device_list
            if getattr(d, "device_type", "") in [DEVICE_TYPE_IB01, DEVICE_TYPE_GW01]
        ]
    else:  # GEN_X
        return [
            d for d in device_list if getattr(d, "device_type", "") == DEVICE_TYPE_IB02
        ]


def _yield_devices_v3(
    coordinator: TadoDataUpdateCoordinator,
    include_zone_types: set[str] | None = None,
    capability: str | None = None,
) -> Generator[tuple[Any, int], None, None]:
    """Yield v3 Classic devices matching zone types and capabilities.

    v3 specific implementation - uses zone.id and zone.type.

    Returns:
        Generator of (Device, zone_id) tuples

    """
    from ..const import DEVICE_PREFIX_BRIDGE, DEVICE_TYPE_GW01

    seen_devices: set[str] = set()

    # v3: zones_meta contains Zone objects with .id and .type
    for zone in coordinator.zones_meta.values():
        # Zone type filtering (v3 specific)
        if include_zone_types is not None and zone.type not in include_zone_types:
            continue

        for device in zone.devices:
            if device.serial_no in seen_devices:
                continue

            # Exclude bridges from general device scope
            dtype = getattr(device, "device_type", "")
            if dtype.startswith(DEVICE_PREFIX_BRIDGE) or dtype == DEVICE_TYPE_GW01:
                continue

            # Capability filtering
            if capability:
                caps = getattr(device.characteristics, "capabilities", []) or []
                if capability not in caps:
                    continue

            seen_devices.add(device.serial_no)
            yield device, zone.id  # v3 uses zone.id


def yield_devices(
    coordinator: TadoDataUpdateCoordinator,
    include_zone_types: set[str] | None = None,
    capability: str | None = None,
) -> Generator[tuple[Any, int], None, None]:
    """Yield devices matching zone types and capabilities.

    Generation-aware dispatcher - delegates to v3 or Tado X implementation.

    Returns:
        Generator of (Device, zone_id) tuples

    """
    from ..const import GEN_X

    if coordinator.generation == GEN_X:
        # Tado X: delegate to Tado X specific implementation
        from .tadox.discovery import yield_tadox_devices

        yield from yield_tadox_devices(coordinator, include_zone_types, capability)
    else:
        # v3 Classic: use v3 specific implementation
        yield from _yield_devices_v3(coordinator, include_zone_types, capability)
