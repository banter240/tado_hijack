"""Calendar platform: per-zone weekly heating plan as read-only events."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .entity import TadoZoneEntity
from .helpers.discovery import yield_zones
from .helpers.schedule import (
    iter_heat_windows,
    plan_service_attrs,
    service_blocks_for_weekday,
    zone_supports_schedule,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import TadoConfigEntry
    from .coordinator import TadoDataUpdateCoordinator

_LOOKAHEAD = timedelta(days=8)


def _weekly_plan_title(zone_name: str, language: str | None) -> str:
    """Full calendar name: Tado <room> Weekly Plan (localized suffix)."""
    lang = (language or "en").lower()
    if lang.startswith("de"):
        suffix = "Wochenplan"
    elif lang.startswith("cs"):
        suffix = "týdenní plán"
    else:
        suffix = "Weekly Plan"
    return f"Tado {zone_name} {suffix}"


def _as_local(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=dt_util.get_default_time_zone())
    return cast(datetime, dt_util.as_local(value))


def _heat_event(
    start_at: datetime,
    end_at: datetime,
    temp: float,
    description: str | None = None,
) -> CalendarEvent:
    return CalendarEvent(
        start=start_at,
        end=end_at,
        summary=f"{temp:g} °C",
        description=description,
    )


def _events_from_plan(
    days: dict[str, Any],
    timetable_type: str | None,
    range_start: datetime,
    range_end: datetime,
) -> list[CalendarEvent]:
    json_by_weekday: dict[int, str] = {}
    events: list[CalendarEvent] = []
    for window_start, window_end, temp in iter_heat_windows(
        days, range_start, range_end
    ):
        weekday = window_start.weekday()
        if weekday not in json_by_weekday:
            blocks = service_blocks_for_weekday(days, timetable_type, weekday)
            json_by_weekday[weekday] = (
                json.dumps(blocks, ensure_ascii=False, separators=(",", ":"))
                if blocks
                else ""
            )
        events.append(
            _heat_event(
                window_start,
                window_end,
                temp,
                json_by_weekday[weekday] or None,
            )
        )
    return events


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TadoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one plan calendar per schedule-capable zone."""
    coordinator: TadoDataUpdateCoordinator = entry.runtime_data
    dummy = coordinator.dummy_handler
    if entities := [
        TadoZonePlanCalendar(coordinator, zone.id, zone.name)
        for zone in yield_zones(coordinator)
        if zone_supports_schedule(coordinator, zone.id)
        and not (dummy and dummy.is_dummy_zone(zone.id))
    ]:
        async_add_entities(entities)


class TadoZonePlanCalendar(TadoZoneEntity, CalendarEntity):
    """Read-only ON windows for a zone's cloud heating plan."""

    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: TadoDataUpdateCoordinator,
        zone_id: int,
        zone_name: str,
    ) -> None:
        """Initialize the zone plan calendar."""
        super().__init__(coordinator, "zone_plan", zone_id, zone_name)
        entry_id = (
            coordinator.config_entry.entry_id if coordinator.config_entry else "tado"
        )
        self._attr_unique_id = f"{entry_id}_zone_{zone_id}_zone_plan"
        language = coordinator.hass.config.language if coordinator.hass else None
        self._attr_name = _weekly_plan_title(zone_name, language)
        self._set_entity_id("calendar", "zone_plan")

    async def async_added_to_hass(self) -> None:
        """Keep the full Tado <room> name; HA would otherwise prefix the zone device."""
        await super().async_added_to_hass()
        registry = er.async_get(self.hass)
        entry = registry.async_get(self.entity_id)
        wanted = self._attr_name
        if entry is None or wanted is None or entry.name is not None:
            return
        registry.async_update_entity(self.entity_id, name=wanted)

    def _plan_entry(self) -> dict[str, Any]:
        plan = self.coordinator.data_manager.schedule_blocks_cache.get(self._zone_id)
        return plan if isinstance(plan, dict) else {}

    def _plan_days(self) -> dict[str, Any]:
        days = self._plan_entry().get("days")
        return days if isinstance(days, dict) else {}

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """set_schedule-ready payload for today (and the full cached plan)."""
        return plan_service_attrs(self._plan_entry(), dt_util.now().weekday())

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next heat window from cache (no extra API call)."""
        days = self._plan_days()
        if not days:
            return None
        now = dt_util.now()
        events = _events_from_plan(
            days, self._plan_entry().get("timetable_type"), now, now + _LOOKAHEAD
        )
        return events[0] if events else None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return cached heat windows. Fetch is a button or manual poll, not open."""
        if days := self._plan_days():
            return _events_from_plan(
                days,
                self._plan_entry().get("timetable_type"),
                _as_local(start_date),
                _as_local(end_date),
            )
        return []
