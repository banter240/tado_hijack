"""Models for Tado Hijack."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


@dataclass(slots=True)
class RateLimit:
    """Model for API Rate Limit statistics."""

    limit: int
    remaining: int


class CommandType(StrEnum):
    """Types of API commands."""

    SET_OVERLAY = "set_overlay"
    RESUME_SCHEDULE = "resume_schedule"
    SET_PRESENCE = "set_presence"
    MANUAL_POLL = "manual_poll"
    SET_CHILD_LOCK = "set_child_lock"
    SET_OFFSET = "set_offset"


@dataclass
class TadoCommand:
    """Represents a queued API command."""

    cmd_type: CommandType
    zone_id: int | None = None
    data: dict[str, Any] | None = None
