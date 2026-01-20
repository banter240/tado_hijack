"""Manages optimistic UI state updates for immediate feedback."""

from __future__ import annotations

import time
from typing import Any, cast

from ..const import OPTIMISTIC_GRACE_PERIOD_S


class OptimisticManager:
    """Manages temporary optimistic states for immediate UI feedback."""

    def __init__(self) -> None:
        """Initialize the manager."""
        self.presence: str | None = None
        self.presence_time: float = 0
        self.zones: dict[int, dict[str, Any]] = {}
        self.devices: dict[str, dict[str, Any]] = {}

    def set_presence(self, presence: str) -> None:
        """Set optimistic presence state."""
        self.presence = presence
        self.presence_time = time.monotonic()

    def set_zone(self, zone_id: int, overlay: bool | None) -> None:
        """Set optimistic zone overlay state."""
        self.zones[zone_id] = {"overlay": overlay, "time": time.monotonic()}

    def set_child_lock(self, serial_no: str, enabled: bool) -> None:
        """Set optimistic child lock state."""
        self.devices[serial_no] = self.devices.get(serial_no, {})
        self.devices[serial_no].update(
            {"child_lock": enabled, "time": time.monotonic()}
        )

    def set_offset(self, serial_no: str, offset: float) -> None:
        """Set optimistic temperature offset state."""
        self.devices[serial_no] = self.devices.get(serial_no, {})
        self.devices[serial_no].update({"offset": offset, "time": time.monotonic()})

    def get_presence(self) -> str | None:
        """Return optimistic presence if not expired."""
        if (
            self.presence
            and (time.monotonic() - self.presence_time) < OPTIMISTIC_GRACE_PERIOD_S
        ):
            return self.presence
        return None

    def get_zone_overlay(self, zone_id: int) -> bool | None:
        """Return optimistic zone overlay if not expired."""
        if zone_id not in self.zones:
            return None

        opt = self.zones[zone_id]
        if (time.monotonic() - opt["time"]) < OPTIMISTIC_GRACE_PERIOD_S:
            return cast("bool | None", opt["overlay"])

        return None

    def get_child_lock(self, serial_no: str) -> bool | None:
        """Return optimistic child lock state if not expired."""
        if serial_no not in self.devices:
            return None

        opt = self.devices[serial_no]
        if (
            "child_lock" in opt
            and (time.monotonic() - opt["time"]) < OPTIMISTIC_GRACE_PERIOD_S
        ):
            return cast("bool", opt["child_lock"])

        return None

    def get_offset(self, serial_no: str) -> float | None:
        """Return optimistic temperature offset if not expired."""
        if serial_no not in self.devices:
            return None

        opt = self.devices[serial_no]
        if (
            "offset" in opt
            and (time.monotonic() - opt["time"]) < OPTIMISTIC_GRACE_PERIOD_S
        ):
            return cast("float", opt["offset"])

        return None

    def cleanup(self) -> None:
        """Clear expired optimistic states."""
        now = time.monotonic()
        if (now - self.presence_time) > OPTIMISTIC_GRACE_PERIOD_S:
            self.presence = None

        to_delete_zones = [
            z_id
            for z_id, d in self.zones.items()
            if (now - d["time"]) > OPTIMISTIC_GRACE_PERIOD_S
        ]
        for z_id in to_delete_zones:
            del self.zones[z_id]

        to_delete_devices = [
            s_no
            for s_no, d in self.devices.items()
            if (now - d["time"]) > OPTIMISTIC_GRACE_PERIOD_S
        ]
        for s_no in to_delete_devices:
            del self.devices[s_no]
