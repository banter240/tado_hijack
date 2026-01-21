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
        self.away_temps: dict[int, float] = {}
        self.dazzle_modes: dict[int, bool] = {}
        self.presence: str | None = None
        self.manual_poll: str | None = None

    def add(self, cmd: TadoCommand) -> None:
        """Add a command to the merger."""
        if cmd.cmd_type == CommandType.MANUAL_POLL:
            # Upgrade to 'all' if multiple manual polls are mixed
            new_type = cmd.data.get("type", "all") if cmd.data else "all"
            if self.manual_poll is None:
                self.manual_poll = new_type
            elif self.manual_poll != new_type:
                self.manual_poll = "all"
        elif cmd.cmd_type == CommandType.SET_CHILD_LOCK:
            self._merge_child_lock(cmd)
        elif cmd.cmd_type == CommandType.SET_OFFSET:
            self._merge_offset(cmd)
        elif cmd.cmd_type == CommandType.SET_AWAY_TEMP:
            self._merge_away_temp(cmd)
        elif cmd.cmd_type == CommandType.SET_DAZZLE:
            self._merge_dazzle(cmd)
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

    def _merge_away_temp(self, cmd: TadoCommand) -> None:
        if cmd.data and "zone_id" in cmd.data and "temp" in cmd.data:
            self.away_temps[int(cmd.data["zone_id"])] = float(cmd.data["temp"])

    def _merge_dazzle(self, cmd: TadoCommand) -> None:
        if cmd.data and "zone_id" in cmd.data and "enabled" in cmd.data:
            self.dazzle_modes[int(cmd.data["zone_id"])] = bool(cmd.data["enabled"])

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
        if not cmd.data:
            return

        if cmd.zone_id is not None:
            self._apply_overlay(cmd.zone_id, cmd.data)
        else:
            # Bulk operation for all heating zones
            for zid, zone in self.zones_meta.items():
                if getattr(zone, "type", "HEATING") == "HEATING":
                    self._apply_overlay(zid, cmd.data)

    def _apply_overlay(self, zone_id: int, data: dict[str, Any]) -> None:
        """Deep merge overlay settings for a zone."""
        current = self.zones.get(zone_id)
        if current is None:
            self.zones[zone_id] = data
            return

        # Merge 'setting' part of the overlay
        current_setting = current.get("setting", {})
        new_setting = data.get("setting", {})
        current["setting"] = {**current_setting, **new_setting}

    @property
    def result(self) -> dict[str, Any]:
        """Return the merged result."""
        return {
            "zones": self.zones,
            "child_lock": self.child_locks,
            "offsets": self.offsets,
            "away_temps": self.away_temps,
            "dazzle_modes": self.dazzle_modes,
            "presence": self.presence,
            "manual_poll": self.manual_poll,
        }
