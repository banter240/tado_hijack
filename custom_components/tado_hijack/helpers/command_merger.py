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
        self.early_starts: dict[int, bool] = {}
        self.open_windows: dict[int, bool] = {}
        self.identifies: set[str] = set()
        self.presence: str | None = None
        self.old_presence: str | None = None
        self.manual_poll: str | None = None
        self.rollback_zones: dict[int, Any] = {}
        self.rollback_child_locks: dict[str, bool] = {}
        self.rollback_offsets: dict[str, float] = {}
        self.rollback_away_temps: dict[int, float] = {}
        self.rollback_dazzle_modes: dict[int, bool] = {}
        self.rollback_early_starts: dict[int, bool] = {}
        self.rollback_open_windows: dict[int, bool] = {}

    def add(self, cmd: TadoCommand) -> None:
        """Add a command to the merger."""
        handlers = {
            CommandType.MANUAL_POLL: self._merge_manual_poll,
            CommandType.SET_OVERLAY: self._merge_overlay,
            CommandType.SET_CHILD_LOCK: self._merge_child_lock,
            CommandType.SET_OFFSET: self._merge_offset,
            CommandType.SET_AWAY_TEMP: self._merge_away_temp,
            CommandType.SET_DAZZLE: self._merge_dazzle,
            CommandType.SET_EARLY_START: self._merge_early_start,
            CommandType.SET_OPEN_WINDOW: self._merge_open_window,
            CommandType.IDENTIFY: self._merge_identify,
            CommandType.SET_PRESENCE: self._merge_presence,
            CommandType.RESUME_SCHEDULE: self._merge_resume,
        }
        if handler := handlers.get(cmd.cmd_type):
            handler(cmd)

    def _merge_manual_poll(self, cmd: TadoCommand) -> None:
        new_type = cmd.data.get("type", "all") if cmd.data else "all"
        if self.manual_poll is None:
            self.manual_poll = new_type
        elif self.manual_poll != new_type:
            self.manual_poll = "all"

    def _merge_child_lock(self, cmd: TadoCommand) -> None:
        if cmd.data and "serial" in cmd.data and "enabled" in cmd.data:
            serial = cmd.data["serial"]
            self.child_locks[serial] = bool(cmd.data["enabled"])
            if (
                cmd.rollback_context is not None
                and serial not in self.rollback_child_locks
            ):
                self.rollback_child_locks[serial] = cmd.rollback_context

    def _merge_offset(self, cmd: TadoCommand) -> None:
        if cmd.data and "serial" in cmd.data and "offset" in cmd.data:
            serial = cmd.data["serial"]
            self.offsets[serial] = float(cmd.data["offset"])
            if cmd.rollback_context is not None and serial not in self.rollback_offsets:
                self.rollback_offsets[serial] = cmd.rollback_context

    def _merge_away_temp(self, cmd: TadoCommand) -> None:
        if cmd.data and "zone_id" in cmd.data and "temp" in cmd.data:
            zid = int(cmd.data["zone_id"])
            self.away_temps[zid] = float(cmd.data["temp"])
            if cmd.rollback_context is not None and zid not in self.rollback_away_temps:
                self.rollback_away_temps[zid] = cmd.rollback_context

    def _merge_dazzle(self, cmd: TadoCommand) -> None:
        if cmd.data and "zone_id" in cmd.data and "enabled" in cmd.data:
            zid = int(cmd.data["zone_id"])
            self.dazzle_modes[zid] = bool(cmd.data["enabled"])
            if (
                cmd.rollback_context is not None
                and zid not in self.rollback_dazzle_modes
            ):
                self.rollback_dazzle_modes[zid] = cmd.rollback_context

    def _merge_early_start(self, cmd: TadoCommand) -> None:
        if cmd.data and "zone_id" in cmd.data and "enabled" in cmd.data:
            zid = int(cmd.data["zone_id"])
            self.early_starts[zid] = bool(cmd.data["enabled"])
            if (
                cmd.rollback_context is not None
                and zid not in self.rollback_early_starts
            ):
                self.rollback_early_starts[zid] = cmd.rollback_context

    def _merge_open_window(self, cmd: TadoCommand) -> None:
        if cmd.data and "zone_id" in cmd.data and "enabled" in cmd.data:
            zid = int(cmd.data["zone_id"])
            self.open_windows[zid] = bool(cmd.data["enabled"])
            if (
                cmd.rollback_context is not None
                and zid not in self.rollback_open_windows
            ):
                self.rollback_open_windows[zid] = cmd.rollback_context

    def _merge_identify(self, cmd: TadoCommand) -> None:
        if cmd.data and "serial" in cmd.data:
            self.identifies.add(str(cmd.data["serial"]))

    def _merge_presence(self, cmd: TadoCommand) -> None:
        if cmd.data and "presence" in cmd.data:
            self.presence = str(cmd.data["presence"])
            if self.old_presence is None and "old_presence" in cmd.data:
                self.old_presence = cmd.data["old_presence"]

    def _merge_resume(self, cmd: TadoCommand) -> None:
        if cmd.zone_id is not None:
            self.zones[cmd.zone_id] = None
            if cmd.rollback_context:
                self.rollback_zones[cmd.zone_id] = cmd.rollback_context
        else:
            for zid in self.zones_meta:
                self.zones[zid] = None
                # Bulk resume doesn't support individual rollback context in this command structure
                # Logic handled in coordinator loop

    def _merge_overlay(self, cmd: TadoCommand) -> None:
        if not cmd.data:
            return

        if cmd.zone_id is not None:
            self._apply_overlay(cmd.zone_id, cmd.data)
            if cmd.rollback_context:
                self.rollback_zones[cmd.zone_id] = cmd.rollback_context
        else:
            # Bulk operation for all heating zones
            for zid, zone in self.zones_meta.items():
                if getattr(zone, "type", "HEATING") == "HEATING":
                    self._apply_overlay(zid, cmd.data)
                    # Bulk overlay rollback handled in coordinator

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
            "early_starts": self.early_starts,
            "open_windows": self.open_windows,
            "identifies": self.identifies,
            "presence": self.presence,
            "old_presence": self.old_presence,
            "manual_poll": self.manual_poll,
            "rollback_zones": self.rollback_zones,
            "rollback_child_locks": self.rollback_child_locks,
            "rollback_offsets": self.rollback_offsets,
            "rollback_away_temps": self.rollback_away_temps,
            "rollback_dazzle_modes": self.rollback_dazzle_modes,
            "rollback_early_starts": self.rollback_early_starts,
            "rollback_open_windows": self.rollback_open_windows,
        }
