"""Manages optimistic UI state updates for immediate feedback."""

from __future__ import annotations

import time
from typing import Any, cast

from ..const import OPTIMISTIC_GRACE_PERIOD_S


class OptimisticManager:
    """Manages temporary optimistic states for immediate UI feedback."""

    def __init__(self) -> None:
        """Initialize the manager."""
        # Generic store: {scope: {id: {key: (value, time)}}}
        self._store: dict[str, dict[str | int, dict[str, tuple[Any, float]]]] = {
            "home": {},
            "zone": {},
            "device": {},
        }

    def set_optimistic(
        self, scope: str, entity_id: str | int, key: str, value: Any
    ) -> None:
        """Set an optimistic value for a given scope, ID and key."""
        if scope not in self._store:
            self._store[scope] = {}
        if entity_id not in self._store[scope]:
            self._store[scope][entity_id] = {}

        self._store[scope][entity_id][key] = (value, time.monotonic())

    def get_optimistic(self, scope: str, entity_id: str | int, key: str) -> Any | None:
        """Return optimistic value if not expired."""
        if (
            scope not in self._store
            or entity_id not in self._store[scope]
            or key not in self._store[scope][entity_id]
        ):
            return None

        val, set_time = self._store[scope][entity_id][key]
        if (time.monotonic() - set_time) < OPTIMISTIC_GRACE_PERIOD_S:
            return val

        # Clean up expired entry
        del self._store[scope][entity_id][key]
        return None

    def clear_optimistic(self, scope: str, entity_id: str | int, key: str) -> None:
        """Clear a specific optimistic value (e.g. for rollback)."""
        if (
            scope in self._store
            and entity_id in self._store[scope]
            and key in self._store[scope][entity_id]
        ):
            del self._store[scope][entity_id][key]

    def set_presence(self, presence: str) -> None:
        """Set optimistic presence state."""
        self.set_optimistic("home", "global", "presence", presence)

    def set_zone(
        self,
        zone_id: int,
        overlay: bool | None,
        power: str | None = None,
        operation_mode: str | None = None,
        temperature: float | None = None,
    ) -> None:
        """Set optimistic zone overlay state (Legacy/Simple)."""
        self.set_optimistic("zone", zone_id, "overlay", overlay)
        if power is not None:
            self.set_optimistic("zone", zone_id, "power", power)
        if operation_mode is not None:
            self.set_optimistic("zone", zone_id, "operation_mode", operation_mode)
        if temperature is not None:
            self.set_optimistic("zone", zone_id, "temperature", temperature)

    def apply_zone_state(
        self,
        zone_id: int,
        overlay: bool,
        power: str | None = None,
        temperature: float | None = None,
        operation_mode: str | None = None,
    ) -> None:
        """Apply a comprehensive optimistic state to a zone (DRY Orchestrator).

        This helper ensures all entity types (Climate, WaterHeater) stay in sync.
        """
        # 1. Clear previous state to avoid 'sticking' values (e.g. old temperatures)
        self.clear_zone(zone_id)

        # 2. Set the mandatory overlay marker
        self.set_optimistic("zone", zone_id, "overlay", overlay)

        # 3. Resolve and sync power vs operation_mode
        # If one is missing, we derive it from the other to support all entity types
        final_power = power
        final_op_mode = operation_mode

        if overlay:
            if final_power is None and final_op_mode:
                final_power = "OFF" if final_op_mode == "off" else "ON"
            elif final_op_mode is None and final_power:
                final_op_mode = "off" if final_power == "OFF" else "heat"
            elif final_power is None and final_op_mode is None:
                # Default to ON/HEAT if we just know an overlay is requested
                # This prevents entities from falling back to lagging API data (OFF/AUTO)
                final_power = "ON"
                final_op_mode = "heat"

        # 4. Set the resolved optimistic keys
        if final_power is not None:
            self.set_optimistic("zone", zone_id, "power", final_power)
        if final_op_mode is not None:
            self.set_optimistic("zone", zone_id, "operation_mode", final_op_mode)
        if temperature is not None:
            self.set_optimistic("zone", zone_id, "temperature", temperature)

    def set_child_lock(self, serial_no: str, enabled: bool) -> None:
        """Set optimistic child lock state."""
        self.set_optimistic("device", serial_no, "child_lock", enabled)

    def set_offset(self, serial_no: str, offset: float) -> None:
        """Set optimistic temperature offset state."""
        self.set_optimistic("device", serial_no, "offset", offset)

    def set_away_temp(self, zone_id: int, temp: float) -> None:
        """Set optimistic away temperature state."""
        self.set_optimistic("zone", zone_id, "away_temp", temp)

    def set_dazzle(self, zone_id: int, enabled: bool) -> None:
        """Set optimistic dazzle mode state."""
        self.set_optimistic("zone", zone_id, "dazzle", enabled)

    def set_early_start(self, zone_id: int, enabled: bool) -> None:
        """Set optimistic early start state."""
        self.set_optimistic("zone", zone_id, "early_start", enabled)

    def set_open_window(self, zone_id: int, enabled: bool) -> None:
        """Set optimistic open window detection state."""
        self.set_optimistic("zone", zone_id, "open_window", enabled)

    def get_presence(self) -> str | None:
        """Return optimistic presence if not expired."""
        return cast(str, self.get_optimistic("home", "global", "presence"))

    def get_zone_overlay(self, zone_id: int) -> bool | None:
        """Return optimistic zone overlay if not expired."""
        return cast("bool | None", self.get_optimistic("zone", zone_id, "overlay"))

    def get_zone_power(self, zone_id: int) -> str | None:
        """Return optimistic zone power state if not expired."""
        return cast("str | None", self.get_optimistic("zone", zone_id, "power"))

    def get_zone_operation_mode(self, zone_id: int) -> str | None:
        """Return optimistic zone operation mode if not expired."""
        return cast(
            "str | None", self.get_optimistic("zone", zone_id, "operation_mode")
        )

    def get_zone_temperature(self, zone_id: int) -> float | None:
        """Return optimistic zone temperature if not expired."""
        return cast("float | None", self.get_optimistic("zone", zone_id, "temperature"))

    def get_child_lock(self, serial_no: str) -> bool | None:
        """Return optimistic child lock state if not expired."""
        return cast("bool", self.get_optimistic("device", serial_no, "child_lock"))

    def get_offset(self, serial_no: str) -> float | None:
        """Return optimistic temperature offset if not expired."""
        return cast("float", self.get_optimistic("device", serial_no, "offset"))

    def get_away_temp(self, zone_id: int) -> float | None:
        """Return optimistic away temperature if not expired."""
        return cast("float", self.get_optimistic("zone", zone_id, "away_temp"))

    def get_dazzle(self, zone_id: int) -> bool | None:
        """Return optimistic dazzle mode if not expired."""
        return cast("bool", self.get_optimistic("zone", zone_id, "dazzle"))

    def get_early_start(self, zone_id: int) -> bool | None:
        """Return optimistic early start if not expired."""
        return cast("bool", self.get_optimistic("zone", zone_id, "early_start"))

    def get_open_window(self, zone_id: int) -> bool | None:
        """Return optimistic open window detection if not expired."""
        return cast("bool", self.get_optimistic("zone", zone_id, "open_window"))

    def clear_presence(self) -> None:
        """Clear optimistic presence state (for rollback)."""
        self.clear_optimistic("home", "global", "presence")

    def clear_zone(self, zone_id: int) -> None:
        """Clear optimistic zone state (for rollback)."""
        if "zone" in self._store and zone_id in self._store["zone"]:
            del self._store["zone"][zone_id]

    def clear_child_lock(self, serial_no: str) -> None:
        """Clear optimistic child lock state (for rollback)."""
        self.clear_optimistic("device", serial_no, "child_lock")

    def clear_offset(self, serial_no: str) -> None:
        """Clear optimistic offset state (for rollback)."""
        self.clear_optimistic("device", serial_no, "offset")

    def clear_away_temp(self, zone_id: int) -> None:
        """Clear optimistic away temperature state (for rollback)."""
        self.clear_optimistic("zone", zone_id, "away_temp")

    def clear_dazzle(self, zone_id: int) -> None:
        """Clear optimistic dazzle mode (for rollback)."""
        self.clear_optimistic("zone", zone_id, "dazzle")

    def clear_early_start(self, zone_id: int) -> None:
        """Clear optimistic early start (for rollback)."""
        self.clear_optimistic("zone", zone_id, "early_start")

    def clear_open_window(self, zone_id: int) -> None:
        """Clear optimistic open window (for rollback)."""
        self.clear_optimistic("zone", zone_id, "open_window")

    def cleanup(self) -> None:
        """Clear expired optimistic states."""
        now = time.monotonic()
        for scope in self._store:
            for entity_id in list(self._store[scope].keys()):
                for key in list(self._store[scope][entity_id].keys()):
                    _, set_time = self._store[scope][entity_id][key]
                    if (now - set_time) > OPTIMISTIC_GRACE_PERIOD_S:
                        del self._store[scope][entity_id][key]
                # Cleanup empty ID dicts
                if not self._store[scope][entity_id]:
                    del self._store[scope][entity_id]
