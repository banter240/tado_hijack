"""Helpers for writing Tado timetable blocks (the daily schedule plan)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..const import (
    GEN_X,
    POWER_OFF,
    POWER_ON,
    TADOX_VIRTUAL_HOT_WATER_ZONE_ID,
    TIMETABLE_ONE_DAY,
    TIMETABLE_SEVEN_DAY,
    TIMETABLE_THREE_DAY,
    ZONE_TYPE_AIR_CONDITIONING,
    ZONE_TYPE_HEATING,
    ZONE_TYPE_HOT_WATER,
)
from ..models import CommandType, TadoCommand
from .timetable import entry_for_type, normalize_timetable_type
from .zone_utils import get_zone_type

if TYPE_CHECKING:
    from homeassistant.core import State

    from ..coordinator import TadoDataUpdateCoordinator

MIN_BLOCK_MINUTES = 15
MINUTES_PER_DAY = 1440
CLOCK_HOURS = 24
CLOCK_MINUTES = 60

DAY_MONDAY_TO_SUNDAY = "MONDAY_TO_SUNDAY"
DAY_MONDAY_TO_FRIDAY = "MONDAY_TO_FRIDAY"
DAY_MONDAY = "MONDAY"
DAY_TUESDAY = "TUESDAY"
DAY_WEDNESDAY = "WEDNESDAY"
DAY_THURSDAY = "THURSDAY"
DAY_FRIDAY = "FRIDAY"
DAY_SATURDAY = "SATURDAY"
DAY_SUNDAY = "SUNDAY"

TIMETABLE_DAY_TYPES: dict[str, tuple[str, ...]] = {
    TIMETABLE_ONE_DAY: (DAY_MONDAY_TO_SUNDAY,),
    TIMETABLE_THREE_DAY: (DAY_MONDAY_TO_FRIDAY, DAY_SATURDAY, DAY_SUNDAY),
    TIMETABLE_SEVEN_DAY: (
        DAY_MONDAY,
        DAY_TUESDAY,
        DAY_WEDNESDAY,
        DAY_THURSDAY,
        DAY_FRIDAY,
        DAY_SATURDAY,
        DAY_SUNDAY,
    ),
}

HA_WEEKDAYS: tuple[str, ...] = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

_DAY_ALIASES: dict[str, str] = {
    "monday_to_sunday": DAY_MONDAY_TO_SUNDAY,
    "everyday": DAY_MONDAY_TO_SUNDAY,
    "every_day": DAY_MONDAY_TO_SUNDAY,
    "monday_to_friday": DAY_MONDAY_TO_FRIDAY,
    "weekdays": DAY_MONDAY_TO_FRIDAY,
    "weekday": DAY_MONDAY_TO_FRIDAY,
    "monday": DAY_MONDAY,
    "mon": DAY_MONDAY,
    "tuesday": DAY_TUESDAY,
    "tue": DAY_TUESDAY,
    "wednesday": DAY_WEDNESDAY,
    "wed": DAY_WEDNESDAY,
    "thursday": DAY_THURSDAY,
    "thu": DAY_THURSDAY,
    "friday": DAY_FRIDAY,
    "fri": DAY_FRIDAY,
    "saturday": DAY_SATURDAY,
    "sat": DAY_SATURDAY,
    "sunday": DAY_SUNDAY,
    "sun": DAY_SUNDAY,
}

_CLASSIC_SCHEDULE_TYPES = {
    ZONE_TYPE_HEATING,
    ZONE_TYPE_HOT_WATER,
    ZONE_TYPE_AIR_CONDITIONING,
}


def normalize_day_type(value: str) -> str | None:
    """Accept tuesday / TUESDAY / monday-to-friday and return the API dayType."""
    key = value.strip().replace("-", "_").lower()
    if key in _DAY_ALIASES:
        return _DAY_ALIASES[key]
    upper = value.strip().replace("-", "_").upper()
    allowed = {day for days in TIMETABLE_DAY_TYPES.values() for day in days}
    return upper if upper in allowed else None


def resolve_day_types(
    timetable_type: str, all_days: bool, days: list[str] | None
) -> list[str]:
    """Return the Tado dayTypes to write for this timetable.

    one_day: no day picker (always monday_to_sunday). Passing tuesday etc. errors.
    three_day: monday_to_friday, saturday, sunday only.
    seven_day: monday..sunday, any subset (tuesday+wednesday).
    """
    allowed = list(TIMETABLE_DAY_TYPES[timetable_type])
    if timetable_type == TIMETABLE_ONE_DAY:
        if days:
            for raw in days:
                canon = normalize_day_type(str(raw))
                if canon != DAY_MONDAY_TO_SUNDAY:
                    raise ValueError(
                        "ONE_DAY has no day selection. "
                        "Do not pass days such as tuesday; the plan is every day."
                    )
        return allowed
    if all_days:
        return allowed
    if not days:
        raise ValueError(
            f"Set all_days to true or provide days for {timetable_type} "
            f"({', '.join(allowed)})."
        )

    resolved: list[str] = []
    for raw in days:
        canon = normalize_day_type(str(raw))
        if canon is None:
            raise ValueError(f"Unknown day '{raw}'.")
        if canon not in allowed:
            raise ValueError(
                f"{canon} is not a {timetable_type} slot. Use {', '.join(allowed)}."
            )
        if canon not in resolved:
            resolved.append(canon)
    return resolved


def parse_hhmm(value: str) -> int:
    """Parse HH:MM or HH:MM:SS to minutes from midnight. 24:00 is 1440."""
    text = value.strip()
    if text.startswith("24:00"):
        return MINUTES_PER_DAY
    try:
        hour_s, minute_s, *_extra = text.split(":")
        hour = int(hour_s)
        minute = int(minute_s)
    except ValueError as err:
        raise ValueError(f"Invalid time '{value}'. Use HH:MM.") from err
    if hour == CLOCK_HOURS and minute == 0:
        return MINUTES_PER_DAY
    last_hour = CLOCK_HOURS - 1
    last_minute = CLOCK_MINUTES - 1
    if not (0 <= hour <= last_hour and 0 <= minute <= last_minute):
        raise ValueError(f"Invalid time '{value}'. Use HH:MM.")
    return hour * CLOCK_MINUTES + minute


def format_hhmm(minutes: int, *, end_of_day_midnight: bool) -> str:
    """Format minutes as HH:MM. End-of-day is 00:00 (classic) or 24:00 (X)."""
    if minutes >= MINUTES_PER_DAY:
        return "00:00" if end_of_day_midnight else "24:00"
    hour, minute = divmod(minutes, CLOCK_MINUTES)
    return f"{hour:02d}:{minute:02d}"


def _canonical_block(
    start_min: int,
    end_min: int,
    power: str,
    temperature: float | None,
    geolocation_override: bool,
) -> dict[str, Any]:
    return {
        "start_min": start_min,
        "end_min": end_min,
        "power": power,
        "temperature": temperature,
        "geolocation_override": geolocation_override,
    }


def parse_blocks(
    raw_blocks: list[Any],
    default_geolocation_override: bool = False,
) -> list[dict[str, Any]]:
    """Normalize a service block list to canonical minutes/power/temp."""
    if not raw_blocks:
        raise ValueError("blocks must contain at least one entry.")

    parsed: list[dict[str, Any]] = []
    for raw in raw_blocks:
        if not isinstance(raw, dict):
            raise ValueError("Each block must be a mapping with start and end.")
        if "start" not in raw or "end" not in raw:
            raise ValueError("Each block needs start and end (HH:MM).")
        start_min = parse_hhmm(str(raw["start"]))
        end_min = parse_hhmm(str(raw["end"]))
        if end_min == 0 and start_min > 0:
            end_min = MINUTES_PER_DAY
        power_raw = raw.get("power")
        temperature = raw.get("temperature")
        if power_raw is None:
            power = POWER_ON if temperature is not None else POWER_OFF
        else:
            power = str(power_raw).strip().upper()
            if power not in {POWER_ON, POWER_OFF}:
                raise ValueError("Block power must be ON or OFF.")
        if power == POWER_ON:
            if temperature is None:
                raise ValueError("ON blocks need a temperature.")
            temperature = float(temperature)
        else:
            temperature = None
        geo = raw.get("geolocation_override", default_geolocation_override)
        parsed.append(
            _canonical_block(start_min, end_min, power, temperature, bool(geo))
        )
    return parsed


def ensure_full_day(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Require 00:00-24:00 coverage, no overlaps, min 15 minutes per block."""
    ordered = sorted(blocks, key=lambda item: int(item["start_min"]))
    filled: list[dict[str, Any]] = []
    cursor = 0
    geo = bool(ordered[0]["geolocation_override"]) if ordered else False

    def _off(start: int, end: int) -> dict[str, Any]:
        return _canonical_block(start, end, POWER_OFF, None, geo)

    for block in ordered:
        start_min = int(block["start_min"])
        end_min = int(block["end_min"])
        if end_min <= start_min:
            raise ValueError("Each block must end after it starts.")
        if start_min < cursor:
            raise ValueError("Schedule blocks overlap.")
        if start_min > cursor:
            filled.append(_off(cursor, start_min))
        filled.append(block)
        cursor = end_min
    if cursor < MINUTES_PER_DAY:
        filled.append(_off(cursor, MINUTES_PER_DAY))
    if not filled:
        filled.append(_off(0, MINUTES_PER_DAY))
    if int(filled[0]["start_min"]) != 0:
        raise ValueError("The first block must start at 00:00.")
    if int(filled[-1]["end_min"]) != MINUTES_PER_DAY:
        raise ValueError("The last block must end at 00:00 / 24:00.")
    for block in filled:
        length = int(block["end_min"]) - int(block["start_min"])
        if length < MIN_BLOCK_MINUTES:
            raise ValueError(
                f"Each block must be at least {MIN_BLOCK_MINUTES} minutes."
            )
    return filled


def blocks_from_schedule_state(
    state: State,
    ha_days: list[str],
    default_geolocation_override: bool = False,
) -> list[dict[str, Any]]:
    """Build canonical blocks from a Home Assistant schedule entity.

    Helper gaps are filled with power OFF. Extra data uses temperature / power.
    """
    raw_segments: list[dict[str, Any]] = []
    for ha_day in ha_days:
        entries = state.attributes.get(ha_day) or []
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            extra = entry.get("data")
            data: dict[str, Any] = extra if isinstance(extra, dict) else {}
            raw_segments.append(
                {
                    "start": entry.get("from", entry.get("start")),
                    "end": entry.get("to", entry.get("end")),
                    "temperature": data.get("temperature"),
                    "power": data.get("power"),
                    "geolocation_override": data.get(
                        "geolocation_override", default_geolocation_override
                    ),
                }
            )
    if not raw_segments:
        return ensure_full_day([])
    return ensure_full_day(parse_blocks(raw_segments, default_geolocation_override))


def ha_days_for_tado_day(day_type: str) -> list[str]:
    """HA schedule weekdays that map onto a Tado dayType."""
    if day_type == DAY_MONDAY_TO_SUNDAY:
        return list(HA_WEEKDAYS)
    if day_type == DAY_MONDAY_TO_FRIDAY:
        return list(HA_WEEKDAYS[:5])
    return [day_type.lower()]


def setting_type_for_zone(coordinator: TadoDataUpdateCoordinator, zone_id: int) -> str:
    """ZoneSetting.type for this zone."""
    ztype = get_zone_type(coordinator.zones_meta.get(zone_id))
    return ztype or ZONE_TYPE_HEATING


def zone_supports_schedule(
    coordinator: TadoDataUpdateCoordinator, zone_id: int
) -> bool:
    """True if this zone can receive timetable block writes."""
    if zone_id == TADOX_VIRTUAL_HOT_WATER_ZONE_ID:
        return False
    ztype = get_zone_type(coordinator.zones_meta.get(zone_id))
    if coordinator.generation == GEN_X:
        return ztype == ZONE_TYPE_HEATING
    return ztype in _CLASSIC_SCHEDULE_TYPES


def build_classic_blocks(
    day_type: str, setting_type: str, blocks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Classic v2 TimetableBlock array for one dayType."""
    payload: list[dict[str, Any]] = []
    for block in blocks:
        setting: dict[str, Any] = {
            "type": setting_type,
            "power": block["power"],
        }
        if block["power"] == POWER_ON and block["temperature"] is not None:
            setting["temperature"] = {"celsius": block["temperature"]}
        payload.append(
            {
                "dayType": day_type,
                "start": format_hhmm(int(block["start_min"]), end_of_day_midnight=True),
                "end": format_hhmm(int(block["end_min"]), end_of_day_midnight=True),
                "geolocationOverride": bool(block["geolocation_override"]),
                "setting": setting,
            }
        )
    return payload


def build_x_payload(day_type: str, blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """Hops POST body for one room-day schedule."""
    day_schedule: list[dict[str, Any]] = []
    for block in blocks:
        setting: dict[str, Any] = {"power": block["power"]}
        if block["power"] == POWER_ON and block["temperature"] is not None:
            setting["temperature"] = {"value": block["temperature"]}
        day_schedule.append(
            {
                "start": format_hhmm(
                    int(block["start_min"]), end_of_day_midnight=False
                ),
                "end": format_hhmm(int(block["end_min"]), end_of_day_midnight=False),
                "dayType": day_type,
                "setting": setting,
            }
        )
    return {"dayType": day_type, "daySchedule": day_schedule}


def schedule_queue_key(zone_id: int, timetable_id: int, day_type: str) -> str:
    """Debounce key for one zone + timetable + dayType write."""
    return f"{CommandType.SET_SCHEDULE.value}_{zone_id}_{timetable_id}_{day_type}"


def schedule_slot_key(zone_id: int, timetable_id: int, day_type: str) -> str:
    """Merger key for last-write-wins schedule slots."""
    return f"{zone_id}:{timetable_id}:{day_type}"


def schedule_queue_key_for_command(cmd: TadoCommand) -> str | None:
    """Debounce key for SET_SCHEDULE, or None."""
    if cmd.cmd_type != CommandType.SET_SCHEDULE or not cmd.data:
        return None
    return schedule_queue_key(
        int(cmd.data["zone_id"]),
        int(cmd.data["timetable_id"]),
        str(cmd.data["day_type"]),
    )


def build_set_schedule_command(
    zone_id: int,
    timetable_id: int,
    day_type: str,
    payload: Any,
) -> TadoCommand:
    """Queue payload for one dayType write."""
    return TadoCommand(
        CommandType.SET_SCHEDULE,
        zone_id=zone_id,
        data={
            "zone_id": zone_id,
            "timetable_id": timetable_id,
            "day_type": day_type,
            "payload": payload,
        },
    )


def resolve_timetable_type(requested: str | None, cached_type: str | None) -> str:
    """Canonical timetable type from the service arg or the zone cache."""
    if requested:
        canonical = normalize_timetable_type(requested)
        if canonical is None or entry_for_type(canonical) is None:
            raise ValueError(f"Unknown timetable '{requested}'.")
        return canonical
    if cached_type:
        if canonical := normalize_timetable_type(cached_type):
            return canonical
    raise ValueError(
        "No timetable type known for this zone. "
        "Pass timetable or refresh the timetable first."
    )


def as_day_list(days: Any) -> list[str] | None:
    """Accept a single day string or a list."""
    if days is None:
        return None
    return [days] if isinstance(days, str) else [str(item) for item in days]
