"""Executor for Tado X (Hops) batch commands."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from collections.abc import Callable, Coroutine

from ...lib.tadox_api import TadoXApi
from ..executor_base import TadoExecutorBase, map_magic_temp_to_power
from ..logging_utils import get_redacted_logger

if TYPE_CHECKING:
    from ...coordinator import TadoDataUpdateCoordinator

_LOGGER = get_redacted_logger(__name__)


class TadoXExecutor(TadoExecutorBase):
    """Handles execution of merged commands targeting the Hops API."""

    def __init__(
        self, coordinator: TadoDataUpdateCoordinator, bridge: TadoXApi
    ) -> None:
        """Initialize the Tado X executor."""
        jitter_percent = 10.0
        if coordinator.config_entry and coordinator.config_entry.data:
            jitter_percent = float(
                coordinator.config_entry.data.get("jitter_percent", 10.0)
            )
        super().__init__(coordinator, jitter_percent)
        self.bridge = bridge

    async def execute_batch(self, merged: dict[str, Any]) -> None:
        """Process the entire merged batch using Tado X logic."""

        # 1. Presence
        if merged["presence"]:
            await self._safe_execute(
                "presence",
                self.bridge.async_set_presence(merged["presence"]),
                rollback_fn=self._create_presence_rollback(merged.get("old_presence")),
            )

        # 2. Device Properties (Child Lock, Offset) -> Unified into PATCH
        await self._execute_device_fusion(merged)

        # 3. Zone Actions & Quick Actions
        await self._execute_zone_actions(merged)

        # 4. Open Window Detection
        rollback_open_windows = merged.get("rollback_open_windows", {})
        for zone_id, data in merged["open_windows"].items():
            if self._should_skip_zone(zone_id):  # [DUMMY_HOOK]
                continue

            await self._safe_execute(
                f"open_window_{zone_id}",
                self.bridge.async_set_open_window_detection(zone_id, data["enabled"]),
                rollback_fn=self._create_open_window_rollback(
                    zone_id, rollback_open_windows.get(zone_id)
                ),
                context={"zone_id": zone_id, "enabled": data["enabled"]},
            )

        # 5. Identify Actions
        for serial in merged["identifies"]:
            await self._safe_execute(
                f"identify_{serial}",
                self.bridge._request(
                    "POST", f"roomsAndDevices/devices/{serial}/identify"
                ),
            )

    async def _execute_device_fusion(self, merged: dict[str, Any]) -> None:
        """Fuse multiple property changes for the same device into a single PATCH call."""
        device_changes: dict[str, dict[str, Any]] = {}

        # Collect Child Lock changes
        for serial, enabled in merged["child_lock"].items():
            device_changes.setdefault(serial, {})["childLockEnabled"] = enabled

        # Collect Offset changes
        for serial, offset in merged["offsets"].items():
            device_changes.setdefault(serial, {})["temperatureOffset"] = offset

        rollback_child_locks = merged.get("rollback_child_locks", {})
        rollback_offsets = merged.get("rollback_offsets", {})

        for serial, payload in device_changes.items():
            # Create combined rollback function for both properties
            rb_child = self._create_child_lock_rollback(
                serial, rollback_child_locks.get(serial)
            )
            rb_offset = self._create_offset_rollback(
                serial, rollback_offsets.get(serial)
            )

            async def _rollback_combined(
                rb_c: Callable[[], Coroutine[Any, Any, None]] = rb_child,
                rb_o: Callable[[], Coroutine[Any, Any, None]] = rb_offset,
            ) -> None:
                await rb_c()
                await rb_o()

            await self._safe_execute(
                f"device_update_{serial}",
                self.bridge._request(
                    "PATCH", f"roomsAndDevices/devices/{serial}", json_data=payload
                ),
                rollback_fn=_rollback_combined,
                context={"serial": serial, "payload": payload},
            )

    async def _execute_zone_actions(self, merged: dict[str, Any]) -> None:
        """Execute zone commands, prioritizing house-wide Quick Actions."""
        zones = merged["zones"]
        if not zones:
            return

        real_zones = {
            zid: data
            for zid, data in zones.items()
            if not self._intercept_zone_command(zid, data)
        }
        if not real_zones:
            return

        rollback_zones = merged.get("rollback_zones", {})

        # Check for Quick Action potential (Heuristic)
        all_heating = self.coordinator.get_active_zones(include_heating=True)
        pending_resumes = [
            zid
            for zid, data in real_zones.items()
            if data is None and zid in all_heating
        ]

        if pending_resumes and len(pending_resumes) == len(all_heating):
            _LOGGER.info("Tado X: Fusing multiple resumes into house-wide Quick Action")
            await self._safe_execute(
                "resume_all",
                self.bridge.async_resume_all_schedules(),
                rollback_fn=self._create_zones_rollback(
                    pending_resumes, rollback_zones
                ),
                context={"zones": pending_resumes},
            )
            return

        # Fallback: Execute remaining zone actions sequentially with jitter
        for zone_id, data in real_zones.items():
            if data is None:
                await self._safe_execute(
                    f"resume_{zone_id}",
                    self.bridge.async_resume_schedule(zone_id),
                    rollback_fn=self._create_zones_rollback([zone_id], rollback_zones),
                    context={"zone_id": zone_id},
                )
            else:
                # Manual Control - rebuild overlay from merged data
                setting = data.get("setting", {})

                # Support both v3 format (celsius) and Tado X format (value)
                temp_dict = setting.get("temperature", {})
                temp = temp_dict.get("value") or temp_dict.get("celsius")

                # Magic number mapping: temp=-1 → power=OFF (last call wins)
                temp, power = map_magic_temp_to_power(temp)

                await self._safe_execute(
                    f"overlay_{zone_id}",
                    self.bridge.async_set_manual_control(zone_id, temp, power=power),
                    rollback_fn=self._create_zones_rollback([zone_id], rollback_zones),
                    context={"zone_id": zone_id, "temp": temp, "power": power},
                )
