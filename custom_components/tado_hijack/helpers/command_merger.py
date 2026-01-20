"""Helper to merge Tado commands."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..models import CommandType, TadoCommand

if TYPE_CHECKING:
    from tadoasync.models import Zone


class CommandMerger:
    """Merges a list of commands into a consolidated state."""

    def __init__(self, zones_meta: dict[int, Zone]) -> None:
        """Initialize the merger."""
        self.zones_meta = zones_meta
        self.zones: dict[int, dict[str, Any] | None] = {}
        self.child_locks: dict[str, bool] = {}
        self.offsets: dict[str, float] = {}
        self.presence: str | None = None
        self.manual_poll = False

    def add(self, cmd: TadoCommand) -> None:
        """Add a command to the merger."""
        if cmd.cmd_type == CommandType.MANUAL_POLL:
            self.manual_poll = True
        elif cmd.cmd_type == CommandType.SET_CHILD_LOCK:
            self._merge_child_lock(cmd)
        elif cmd.cmd_type == CommandType.SET_OFFSET:
            self._merge_offset(cmd)
        elif cmd.cmd_type == CommandType.SET_PRESENCE:
            self._merge_presence(cmd)
        elif cmd.cmd_type == CommandType.RESUME_SCHEDULE:
            self._merge_resume(cmd)
        elif cmd.cmd_type == CommandType.SET_OVERLAY:
            self._merge_overlay(cmd)

    def _merge_child_lock(self, cmd: TadoCommand) -> None:
        if cmd.data and "serial" in cmd.data and "enabled" in cmd.data:
            self.child_locks[cmd.data["serial"]] = bool(cmd.data["enabled"])

    def _merge_offset(self, cmd: TadoCommand) -> None:
        if cmd.data and "serial" in cmd.data and "offset" in cmd.data:
            self.offsets[cmd.data["serial"]] = float(cmd.data["offset"])

    def _merge_presence(self, cmd: TadoCommand) -> None:
        if cmd.data and "presence" in cmd.data:
            self.presence = str(cmd.data["presence"])

    def _merge_resume(self, cmd: TadoCommand) -> None:
        if cmd.zone_id is not None:
            self.zones[cmd.zone_id] = None
        else:
            for zid in self.zones_meta:
                self.zones[zid] = None

    def _merge_overlay(self, cmd: TadoCommand) -> None:
        if cmd.zone_id is not None:
            self.zones[cmd.zone_id] = cmd.data
        else:
            for zid, zone in self.zones_meta.items():
                if getattr(zone, "type", "HEATING") == "HEATING":
                    self.zones[zid] = cmd.data

    @property
    def result(self) -> dict[str, Any]:
        """Return the merged result."""
        return {
            "zones": self.zones,
            "child_lock": self.child_locks,
            "offsets": self.offsets,
            "presence": self.presence,
            "manual_poll": self.manual_poll,
        }
