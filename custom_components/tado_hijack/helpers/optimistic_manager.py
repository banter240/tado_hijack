"""Manages optimistic UI state updates for immediate feedback."""

from __future__ import annotations

import time
from typing import Any, cast

from ..const import OPTIMISTIC_GRACE_PERIOD_S
from .logging_utils import get_redacted_logger

_LOGGER = get_redacted_logger(__name__)


class OptimisticManager:
    """Manages temporary optimistic states for immediate UI feedback."""

    def __init__(self) -> None:
        """Initialize the manager."""
        # Generic store: {scope: {id: {key: (value, time, grace)}}}
        self._store: dict[str, dict[str, dict[str, tuple[Any, float, float]]]] = {
            "home": {},
            "zone": {},
            "device": {},
        }

    def set_optimistic(
        self,
        scope: str,
        entity_id: str | int,
        key: str,
        value: Any,
        grace_period: float | None = None,
    ) -> None:
        """Set an optimistic value for a given scope, ID and key."""
        eid = str(entity_id)
        if scope not in self._store:
            self._store[scope] = {}
        if eid not in self._store[scope]:
            self._store[scope][eid] = {}

        # Store value, timestamp and custom grace period if provided
        self._store[scope][eid][key] = (
            value,
            time.monotonic(),
            grace_period or OPTIMISTIC_GRACE_PERIOD_S,
        )

    def get_optimistic(self, scope: str, entity_id: str | int, key: str) -> Any | None:
        """Return optimistic value if not expired."""
        eid = str(entity_id)
        if (
            scope not in self._store
            or eid not in self._store[scope]
            or key not in self._store[scope][eid]
        ):
            return None

        val, set_time, grace = self._store[scope][eid][key]
        if (time.monotonic() - set_time) < grace:
            return val

        # Clean up expired entry
        del self._store[scope][eid][key]
        return None

    def clear_optimistic(self, scope: str, entity_id: str | int, key: str) -> None:
        """Clear a specific optimistic value (e.g. for rollback)."""
        eid = str(entity_id)
        if (
            scope in self._store
            and eid in self._store[scope]
            and key in self._store[scope][eid]
        ):
            _LOGGER.debug("Optimistic CLEAR: [%s] %s -> %s", scope, eid, key)
            del self._store[scope][eid][key]

    def clear_entity(self, scope: str, entity_id: str | int) -> None:
        """Clear all optimistic state for a specific entity ID."""
        eid = str(entity_id)
        if scope in self._store and eid in self._store[scope]:
            _LOGGER.debug("Optimistic CLEAR ENTITY: [%s] %s", scope, eid)
            del self._store[scope][eid]

    # Presence (Home scope)

    def set_presence(self, presence: str, grace_period: float | None = None) -> None:
        """Set optimistic presence state."""
        self.set_optimistic("home", "global", "presence", presence, grace_period)

    def get_presence(self) -> str | None:
        """Return optimistic presence if not expired."""
        return cast(str, self.get_optimistic("home", "global", "presence"))

    def clear_presence(self) -> None:
        """Clear optimistic presence state."""
        self.clear_optimistic("home", "global", "presence")

    # Devices (Device scope)

    def set_child_lock(
        self, serial_no: str, enabled: bool, grace_period: float | None = None
    ) -> None:
        """Set optimistic child lock state."""
        self.set_optimistic("device", serial_no, "child_lock", enabled, grace_period)

    def get_child_lock(self, serial_no: str) -> bool | None:
        """Return optimistic child lock state."""
        return cast(
            "bool | None", self.get_optimistic("device", serial_no, "child_lock")
        )

    def clear_child_lock(self, serial_no: str) -> None:
        """Clear optimistic child lock state."""
        self.clear_optimistic("device", serial_no, "child_lock")

    def set_offset(
        self, serial_no: str, offset: float, grace_period: float | None = None
    ) -> None:
        """Set optimistic temperature offset state."""
        self.set_optimistic("device", serial_no, "offset", offset, grace_period)

    def get_offset(self, serial_no: str) -> float | None:
        """Return optimistic temperature offset."""
        return cast("float | None", self.get_optimistic("device", serial_no, "offset"))

    def clear_offset(self, serial_no: str) -> None:
        """Clear optimistic offset state."""
        self.clear_optimistic("device", serial_no, "offset")

    # Zones (Zone scope)

    def set_zone(
        self,
        zone_id: int,
        overlay: bool | None,
        power: str | None = None,
        operation_mode: str | None = None,
        temperature: float | None = None,
        grace_period: float | None = None,
    ) -> None:
        """Set optimistic zone overlay state (Legacy/Simple)."""
        self.set_optimistic("zone", zone_id, "overlay", overlay, grace_period)
        if power is not None:
            self.set_optimistic("zone", zone_id, "power", power, grace_period)
        if operation_mode is not None:
            self.set_optimistic(
                "zone", zone_id, "operation_mode", operation_mode, grace_period
            )
        if temperature is not None:
            self.set_optimistic(
                "zone", zone_id, "temperature", temperature, grace_period
            )

    def apply_zone_state(
        self,
        zone_id: int,
        overlay: bool,
        power: str | None = None,
        temperature: float | None = None,
        operation_mode: str | None = None,
        ac_mode: str | None = None,
        vertical_swing: str | None = None,
        horizontal_swing: str | None = None,
        grace_period: float | None = None,
    ) -> None:
        """Apply a comprehensive optimistic state to a zone (DRY Orchestrator)."""
        if not overlay:
            self.clear_zone(zone_id)

        self.set_optimistic("zone", zone_id, "overlay", overlay, grace_period)

        if overlay:
            final_power = power
            final_op_mode = operation_mode

            if final_power is None and final_op_mode:
                final_power = "OFF" if final_op_mode == "off" else "ON"
            elif final_op_mode is None and final_power:
                final_op_mode = "off" if final_power == "OFF" else "heat"
            elif final_power is None and final_op_mode is None:
                final_power = "ON"
                final_op_mode = "heat"

            if final_power is not None:
                self.set_optimistic("zone", zone_id, "power", final_power, grace_period)
            if final_op_mode is not None:
                self.set_optimistic(
                    "zone", zone_id, "operation_mode", final_op_mode, grace_period
                )

        if ac_mode is not None:
            self.set_optimistic("zone", zone_id, "ac_mode", ac_mode, grace_period)
        if temperature is not None:
            self.set_optimistic(
                "zone", zone_id, "temperature", temperature, grace_period
            )
        if vertical_swing is not None:
            self.set_optimistic(
                "zone", zone_id, "vertical_swing", vertical_swing, grace_period
            )
        if horizontal_swing is not None:
            self.set_optimistic(
                "zone", zone_id, "horizontal_swing", horizontal_swing, grace_period
            )

    def set_away_temp(
        self, zone_id: int, temp: float, grace_period: float | None = None
    ) -> None:
        """Set optimistic away temperature."""
        self.set_optimistic("zone", zone_id, "away_temp", temp, grace_period)

    def get_away_temp(self, zone_id: int) -> float | None:
        """Return optimistic away temperature."""
        return cast("float | None", self.get_optimistic("zone", zone_id, "away_temp"))

    def clear_away_temp(self, zone_id: int) -> None:
        """Clear optimistic away temperature state."""
        self.clear_optimistic("zone", zone_id, "away_temp")

    def set_dazzle(
        self, zone_id: int, enabled: bool, grace_period: float | None = None
    ) -> None:
        """Set optimistic dazzle mode state."""
        self.set_optimistic("zone", zone_id, "dazzle", enabled, grace_period)

    def get_dazzle(self, zone_id: int) -> bool | None:
        """Return optimistic dazzle mode."""
        return cast("bool | None", self.get_optimistic("zone", zone_id, "dazzle"))

    def clear_dazzle(self, zone_id: int) -> None:
        """Clear optimistic dazzle mode."""
        self.clear_optimistic("zone", zone_id, "dazzle")

    def set_early_start(
        self, zone_id: int, enabled: bool, grace_period: float | None = None
    ) -> None:
        """Set optimistic early start state."""
        self.set_optimistic("zone", zone_id, "early_start", enabled, grace_period)

    def get_early_start(self, zone_id: int) -> bool | None:
        """Return optimistic early start."""
        return cast("bool | None", self.get_optimistic("zone", zone_id, "early_start"))

    def clear_early_start(self, zone_id: int) -> None:
        """Clear optimistic early start."""
        self.clear_optimistic("zone", zone_id, "early_start")

    def set_open_window(
        self, zone_id: int, timeout: int, grace_period: float | None = None
    ) -> None:
        """Set optimistic open window detection state (timeout in seconds)."""
        self.set_optimistic("zone", zone_id, "open_window", timeout, grace_period)

    def get_open_window(self, zone_id: int) -> int | None:
        """Return optimistic open window detection timeout."""
        return cast("int | None", self.get_optimistic("zone", zone_id, "open_window"))

    def clear_open_window(self, zone_id: int) -> None:
        """Clear optimistic open window."""
        self.clear_optimistic("zone", zone_id, "open_window")

    def set_vertical_swing(self, zone_id: int, value: str) -> None:
        """Set optimistic vertical swing state."""
        self.set_optimistic("zone", zone_id, "vertical_swing", value)

    def get_vertical_swing(self, zone_id: int) -> str | None:
        """Return optimistic vertical swing state."""
        return cast(
            "str | None", self.get_optimistic("zone", zone_id, "vertical_swing")
        )

    def set_horizontal_swing(self, zone_id: int, value: str) -> None:
        """Set optimistic horizontal swing state."""
        self.set_optimistic("zone", zone_id, "horizontal_swing", value)

    def get_horizontal_swing(self, zone_id: int) -> str | None:
        """Return optimistic horizontal swing state."""
        return cast(
            "str | None", self.get_optimistic("zone", zone_id, "horizontal_swing")
        )

    def get_zone(self, zone_id: int) -> dict[str, Any]:
        """Get all cached zone state as dict for redundancy checks."""
        overlay = self.get_zone_overlay(zone_id)
        return {
            "overlay_active": overlay if overlay is not None else True,
            "power": self.get_zone_power(zone_id),
            "temperature": self.get_zone_temperature(zone_id),
            "operation_mode": self.get_zone_operation_mode(zone_id),
            "ac_mode": self.get_zone_ac_mode(zone_id),
        }

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

    def get_zone_ac_mode(self, zone_id: int) -> str | None:
        """Return optimistic zone AC mode if not expired."""
        return cast("str | None", self.get_optimistic("zone", zone_id, "ac_mode"))

    def get_zone_temperature(self, zone_id: int) -> float | None:
        """Return optimistic zone temperature if not expired."""
        return cast("float | None", self.get_optimistic("zone", zone_id, "temperature"))

    def clear_zone(self, zone_id: int) -> None:
        """Clear all optimistic zone state."""
        self.clear_entity("zone", zone_id)

    def cleanup(self) -> None:
        """Clear expired optimistic states."""
        now = time.monotonic()
        for scope in self._store:
            for entity_id in list(self._store[scope].keys()):
                for key in list(self._store[scope][entity_id].keys()):
                    _, set_time, grace = self._store[scope][entity_id][key]
                    if (now - set_time) > grace:
                        _LOGGER.debug(
                            "Optimistic SWEEP: [%s] %s -> %s", scope, entity_id, key
                        )
                        del self._store[scope][entity_id][key]
                # Cleanup empty ID dicts
                if not self._store[scope][entity_id]:
                    del self._store[scope][entity_id]
