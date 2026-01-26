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

    def set_zone(
        self,
        zone_id: int,
        overlay: bool | None,
        power: str | None = None,
        operation_mode: str | None = None,
    ) -> None:
        """Set optimistic zone overlay state."""
        data: dict[str, Any] = {"overlay": overlay, "time": time.monotonic()}
        if power is not None:
            data["power"] = power
        if operation_mode is not None:
            data["operation_mode"] = operation_mode
        self.zones[zone_id] = data

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

    def set_away_temp(self, zone_id: int, temp: float) -> None:
        """Set optimistic away temperature state."""
        self.zones[zone_id] = self.zones.get(zone_id, {})
        self.zones[zone_id].update({"away_temp": temp, "time": time.monotonic()})

    def set_dazzle(self, zone_id: int, enabled: bool) -> None:
        """Set optimistic dazzle mode state."""
        self.zones[zone_id] = self.zones.get(zone_id, {})
        self.zones[zone_id].update({"dazzle": enabled, "time": time.monotonic()})

    def set_early_start(self, zone_id: int, enabled: bool) -> None:
        """Set optimistic early start state."""
        self.zones[zone_id] = self.zones.get(zone_id, {})
        self.zones[zone_id].update({"early_start": enabled, "time": time.monotonic()})

    def set_open_window(self, zone_id: int, enabled: bool) -> None:
        """Set optimistic open window detection state."""
        self.zones[zone_id] = self.zones.get(zone_id, {})
        self.zones[zone_id].update({"open_window": enabled, "time": time.monotonic()})

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
        if (time.monotonic() - opt.get("time", 0)) < OPTIMISTIC_GRACE_PERIOD_S:
            val = opt.get("overlay")
            return cast("bool | None", val) if val is not None else None

        return None

    def get_zone_power(self, zone_id: int) -> str | None:
        """Return optimistic zone power state if not expired."""
        if zone_id not in self.zones:
            return None

        opt = self.zones[zone_id]
        if (time.monotonic() - opt.get("time", 0)) < OPTIMISTIC_GRACE_PERIOD_S:
            return cast("str | None", opt.get("power"))

        return None

    def get_zone_operation_mode(self, zone_id: int) -> str | None:
        """Return optimistic zone operation mode if not expired."""
        if zone_id not in self.zones:
            return None

        opt = self.zones[zone_id]
        if (time.monotonic() - opt.get("time", 0)) < OPTIMISTIC_GRACE_PERIOD_S:
            return cast("str | None", opt.get("operation_mode"))

        return None

    def get_child_lock(self, serial_no: str) -> bool | None:
        """Return optimistic child lock state if not expired."""
        if serial_no not in self.devices:
            return None

        opt = self.devices[serial_no]
        if (time.monotonic() - opt.get("time", 0)) < OPTIMISTIC_GRACE_PERIOD_S:
            val = opt.get("child_lock")
            return cast("bool", val) if val is not None else None

        return None

    def get_offset(self, serial_no: str) -> float | None:
        """Return optimistic temperature offset if not expired."""
        if serial_no not in self.devices:
            return None

        opt = self.devices[serial_no]
        if (time.monotonic() - opt.get("time", 0)) < OPTIMISTIC_GRACE_PERIOD_S:
            val = opt.get("offset")
            return cast("float", val) if val is not None else None

        return None

    def get_away_temp(self, zone_id: int) -> float | None:
        """Return optimistic away temperature if not expired."""
        if zone_id not in self.zones:
            return None

        opt = self.zones[zone_id]
        if (time.monotonic() - opt.get("time", 0)) < OPTIMISTIC_GRACE_PERIOD_S:
            val = opt.get("away_temp")
            return cast("float", val) if val is not None else None

        return None

    def get_dazzle(self, zone_id: int) -> bool | None:
        """Return optimistic dazzle mode if not expired."""
        if zone_id not in self.zones:
            return None

        opt = self.zones[zone_id]
        if (time.monotonic() - opt.get("time", 0)) < OPTIMISTIC_GRACE_PERIOD_S:
            val = opt.get("dazzle")
            return cast("bool", val) if val is not None else None

        return None

    def get_early_start(self, zone_id: int) -> bool | None:
        """Return optimistic early start if not expired."""
        if zone_id not in self.zones:
            return None

        opt = self.zones[zone_id]
        if (time.monotonic() - opt.get("time", 0)) < OPTIMISTIC_GRACE_PERIOD_S:
            val = opt.get("early_start")
            return cast("bool", val) if val is not None else None

        return None

    def get_open_window(self, zone_id: int) -> bool | None:
        """Return optimistic open window detection if not expired."""
        if zone_id not in self.zones:
            return None

        opt = self.zones[zone_id]
        if (time.monotonic() - opt.get("time", 0)) < OPTIMISTIC_GRACE_PERIOD_S:
            return cast("bool", opt.get("open_window"))

        return None

    def clear_presence(self) -> None:
        """Clear optimistic presence state (for rollback)."""
        self.presence = None
        self.presence_time = 0

    def clear_zone(self, zone_id: int) -> None:
        """Clear optimistic zone state (for rollback)."""
        self.zones.pop(zone_id, None)

    def clear_child_lock(self, serial_no: str) -> None:
        """Clear optimistic child lock state (for rollback)."""
        if serial_no in self.devices and "child_lock" in self.devices[serial_no]:
            del self.devices[serial_no]["child_lock"]
            if not self.devices[serial_no]:
                del self.devices[serial_no]

    def clear_offset(self, serial_no: str) -> None:
        """Clear optimistic offset state (for rollback)."""
        if serial_no in self.devices and "offset" in self.devices[serial_no]:
            del self.devices[serial_no]["offset"]
            if not self.devices[serial_no]:
                del self.devices[serial_no]

    def clear_away_temp(self, zone_id: int) -> None:
        """Clear optimistic away temperature state (for rollback)."""
        if zone_id in self.zones and "away_temp" in self.zones[zone_id]:
            del self.zones[zone_id]["away_temp"]

    def clear_dazzle(self, zone_id: int) -> None:
        """Clear optimistic dazzle mode (for rollback)."""
        if zone_id in self.zones and "dazzle" in self.zones[zone_id]:
            del self.zones[zone_id]["dazzle"]

    def clear_early_start(self, zone_id: int) -> None:
        """Clear optimistic early start (for rollback)."""
        if zone_id in self.zones and "early_start" in self.zones[zone_id]:
            del self.zones[zone_id]["early_start"]

    def clear_open_window(self, zone_id: int) -> None:
        """Clear optimistic open window (for rollback)."""
        if zone_id in self.zones and "open_window" in self.zones[zone_id]:
            del self.zones[zone_id]["open_window"]

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
