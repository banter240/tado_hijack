"""Classic v2 timetable helpers.

Maps Tado activeTimetable type strings to API ids. Executors receive the
integer id only; format mapping stays here. Tado X uses the same URI
with room ids (experimental).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..const import (
    GEN_X,
    TADOX_VIRTUAL_HOT_WATER_ZONE_ID,
    TIMETABLE_ID_TO_TYPE,
    TIMETABLE_TYPE_TO_ID,
    TIMETABLE_ZONE_TYPES,
    ZONE_TYPE_HEATING,
)
from .zone_utils import get_zone_type

if TYPE_CHECKING:
    from ..coordinator import TadoDataUpdateCoordinator

TimetableEntry = dict[str, Any]


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
