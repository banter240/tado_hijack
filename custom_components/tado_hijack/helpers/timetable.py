"""Classic v2 timetable helpers.

Maps Tado activeTimetable type strings to API ids. Executors receive the
integer id only; format mapping stays here. Tado X uses the same URI
with room ids (experimental).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from ..const import (
    GEN_X,
    TADOX_VIRTUAL_HOT_WATER_ZONE_ID,
    TIMETABLE_ID_TO_TYPE,
    TIMETABLE_TYPE_TO_ID,
    TIMETABLE_ZONE_TYPES,
    ZONE_TYPE_HEATING,
)
from ..models import CommandType, TadoCommand
from .zone_utils import get_zone_type

if TYPE_CHECKING:
    from ..coordinator import TadoDataUpdateCoordinator

TimetableEntry = dict[str, Any]

_REFRESH_ALL_KEY = "all"


def normalize_timetable_type(value: str) -> str | None:
    """Accept ONE_DAY / one_day and return the canonical API type."""
    key = value.strip().replace("-", "_").upper()
    return key if key in TIMETABLE_TYPE_TO_ID else None


def entry_for_type(timetable_type: str) -> TimetableEntry | None:
    """Build a cache entry {id, type} from a canonical type string."""
    timetable_id = TIMETABLE_TYPE_TO_ID.get(timetable_type)
    if timetable_id is None:
        return None
    return {"id": timetable_id, "type": timetable_type}


def entry_for_id(timetable_id: int | None) -> TimetableEntry | None:
    """Build a cache entry from the API integer id."""
    if timetable_id is None:
        return None
    timetable_type = TIMETABLE_ID_TO_TYPE.get(timetable_id)
    return entry_for_type(timetable_type) if timetable_type else None


def normalize_api_entry(raw: dict[str, Any]) -> TimetableEntry:
    """Normalize a Tado activeTimetable payload to {id, type}."""
    raw_id = raw.get("id")
    timetable_id = int(raw_id) if raw_id is not None else None
    timetable_type = (
        normalize_timetable_type(str(raw["type"])) if raw.get("type") else None
    )
    if timetable_type and (entry := entry_for_type(timetable_type)):
        return entry
    if entry := entry_for_id(timetable_id):
        return entry
    return {"id": timetable_id, "type": timetable_type}


def select_option(entry: TimetableEntry | None) -> str | None:
    """HA select option (lowercase) for a cache entry."""
    timetable_type = (entry or {}).get("type")
    return str(timetable_type).lower() if timetable_type else None


def zone_select_value(cache: dict[int, TimetableEntry], zone_id: int) -> str | None:
    """Select value for one zone, or None until fetched."""
    return select_option(cache.get(zone_id))


def home_select_value(cache: dict[int, TimetableEntry]) -> str | None:
    """Home select value when every cached zone agrees; None if mixed/empty."""
    types = {entry.get("type") for entry in cache.values() if entry.get("type")}
    return None if len(types) != 1 else select_option({"type": next(iter(types))})


def compatible_zone_ids(coordinator: TadoDataUpdateCoordinator) -> list[int]:
    """Zone ids that expose classic activeTimetable.

    Classic: heating and hot water. Tado X: heating rooms only (skip synthetic
    DHW 9001). Same v2 URI; X is experimental.
    """
    allowed = (
        {ZONE_TYPE_HEATING} if coordinator.generation == GEN_X else TIMETABLE_ZONE_TYPES
    )
    return [
        zone_id
        for zone_id, zone in coordinator.zones_meta.items()
        if get_zone_type(zone) in allowed and zone_id != TADOX_VIRTUAL_HOT_WATER_ZONE_ID
    ]


def unique_zone_ids(zone_ids: Iterable[Any], skip: Iterable[Any] = ()) -> list[int]:
    """Stable unique int zone ids, dropping anything in skip."""
    skip_set = {int(zid) for zid in skip}
    result: list[int] = []
    seen: set[int] = set()
    for raw in zone_ids:
        zid = int(raw)
        if zid in seen or zid in skip_set:
            continue
        seen.add(zid)
        result.append(zid)
    return result


def set_queue_key(zone_id: int) -> str:
    """Debounce key for SET_TIMETABLE on one zone."""
    return f"{CommandType.SET_TIMETABLE.value}_{zone_id}"


def refresh_queue_key(zone_id: int | None = None) -> str:
    """Debounce key for one zone refresh, or the home-wide refresh_all command."""
    suffix = _REFRESH_ALL_KEY if zone_id is None else zone_id
    return f"{CommandType.REFRESH_TIMETABLE.value}_{suffix}"


def queue_key_for_command(cmd: TadoCommand) -> str | None:
    """Debounce key for a timetable command, or None if cmd is another type."""
    if cmd.cmd_type == CommandType.SET_TIMETABLE and cmd.zone_id is not None:
        return set_queue_key(cmd.zone_id)
    if cmd.cmd_type == CommandType.REFRESH_TIMETABLE:
        return refresh_queue_key(cmd.zone_id)
    return None


def refresh_zone_ids_from_command(cmd: TadoCommand) -> list[int]:
    """Zone ids carried by a REFRESH_TIMETABLE command (one zone or a list)."""
    if cmd.data and cmd.data.get("zone_ids"):
        return unique_zone_ids(cmd.data["zone_ids"])
    zid = cmd.zone_id
    if zid is None and cmd.data and "zone_id" in cmd.data:
        zid = cmd.data["zone_id"]
    return unique_zone_ids((zid,) if zid is not None else ())


def build_set_command(
    zone_id: int, timetable_id: int, rollback_id: int | None
) -> TadoCommand:
    """Queue payload for PUT activeTimetable on one zone."""
    return TadoCommand(
        CommandType.SET_TIMETABLE,
        zone_id=zone_id,
        data={"zone_id": zone_id, "timetable_id": timetable_id},
        rollback_context=rollback_id,
    )


def build_refresh_command(zone_id: int) -> TadoCommand:
    """Queue payload for GET activeTimetable on one zone."""
    return TadoCommand(
        CommandType.REFRESH_TIMETABLE,
        zone_id=zone_id,
        data={"zone_id": zone_id},
    )


def build_refresh_all_command(zone_ids: list[int]) -> TadoCommand:
    """Queue payload for GET activeTimetable on every compatible zone."""
    return TadoCommand(
        CommandType.REFRESH_TIMETABLE,
        data={"zone_ids": zone_ids},
    )
