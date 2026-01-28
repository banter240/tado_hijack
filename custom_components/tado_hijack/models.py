"""Models for Tado Hijack."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tadoasync.models import (
        Capabilities,
        Device,
        HomeState,
        TemperatureOffset,
        Zone,
        ZoneState,
    )


@dataclass(slots=True)
class RateLimit:
    """Model for API Rate Limit statistics."""

    limit: int
    remaining: int


@dataclass
class TadoData:
    """Data structure to hold Tado data.

    Provides type safety and IDE autocomplete for data dictionary access.
    Updated by DataManager.fetch_full_update() and coordinator._async_update_data().
    """

    home_state: HomeState | None = None
    zone_states: dict[str, ZoneState] = field(default_factory=dict)
    rate_limit: RateLimit = field(default_factory=lambda: RateLimit(0, 0))
    api_status: str = "unknown"
    zones: dict[int, Zone] = field(default_factory=dict)
    devices: dict[str, Device] = field(default_factory=dict)
    capabilities: dict[int, Capabilities] = field(default_factory=dict)
    offsets: dict[str, TemperatureOffset] = field(default_factory=dict)
    away_config: dict[int, float] = field(default_factory=dict)


class CommandType(StrEnum):
    """Types of API commands."""

    SET_OVERLAY = "set_overlay"
    RESUME_SCHEDULE = "resume_schedule"
    SET_PRESENCE = "set_presence"
    MANUAL_POLL = "manual_poll"
    SET_CHILD_LOCK = "set_child_lock"
    SET_OFFSET = "set_offset"
    SET_AWAY_TEMP = "set_away_temp"
    SET_DAZZLE = "set_dazzle"
    SET_EARLY_START = "set_early_start"
    SET_OPEN_WINDOW = "set_open_window"
    IDENTIFY = "identify"


@dataclass
class TadoCommand:
    """Represents a queued API command."""

    cmd_type: CommandType
    zone_id: int | None = None
    data: dict[str, Any] | None = None
    rollback_context: Any = None
