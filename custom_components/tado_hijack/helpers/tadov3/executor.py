"""Executor for Tado Classic (v3) batch commands using tadoasync."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..executor_base import TadoExecutorBase, map_magic_temp_to_power
from ..logging_utils import get_redacted_logger

if TYPE_CHECKING:
    from ...coordinator import TadoDataUpdateCoordinator
    from ..client import TadoHijackClient

_LOGGER = get_redacted_logger(__name__)


class TadoV3Executor(TadoExecutorBase):
    """Handles execution of merged commands targeting the v2 API."""

    def __init__(
        self, coordinator: TadoDataUpdateCoordinator, client: TadoHijackClient
    ) -> None:
        """Initialize the Tado v3 executor."""
        jitter_percent = 10.0
        if coordinator.config_entry and coordinator.config_entry.data:
            jitter_percent = float(
                coordinator.config_entry.data.get("jitter_percent", 10.0)
            )
        super().__init__(coordinator, jitter_percent)
        self.client = client

    async def execute_batch(self, merged: dict[str, Any]) -> None:
        """Process the entire merged batch using Classic v3 logic."""

        # 1. Presence
        if presence := merged["presence"]:
            await self._safe_execute(
                "presence",
                self.client.set_presence(presence),
                rollback_fn=self._create_presence_rollback(merged.get("old_presence")),
                success_fn=lambda: self.coordinator.optimistic.set_presence(
                    presence, grace_period=2.0
                ),
                context={"presence": presence},
            )

        # 2. Device Properties (Child Lock, Offset)
        rollback_child_locks = merged.get("rollback_child_locks", {})
        for serial, enabled in merged["child_lock"].items():
            await self._safe_execute(
                f"child_lock_{serial}",
                self.client.set_child_lock(serial, child_lock=enabled),
                rollback_fn=self._create_child_lock_rollback(
                    serial, rollback_child_locks.get(serial)
                ),
                success_fn=lambda s=serial, e=enabled: (
                    self.coordinator.optimistic.set_child_lock(s, e, grace_period=2.0)
                ),
                context={"serial": serial, "enabled": enabled},
            )

        rollback_offsets = merged.get("rollback_offsets", {})
        for serial, offset in merged["offsets"].items():
            await self._safe_execute(
                f"offset_{serial}",
                self.client.set_temperature_offset(serial, offset),
                rollback_fn=self._create_offset_rollback(
                    serial, rollback_offsets.get(serial)
                ),
                success_fn=lambda s=serial, o=offset: (
                    self.coordinator.optimistic.set_offset(s, o, grace_period=2.0)
                ),
                context={"serial": serial, "offset": offset},
            )

        # 3. Zone Properties
        await self._execute_zone_properties(merged)

        # 4. Identify Actions
        for serial in merged["identifies"]:
            await self._safe_execute(
                f"identify_{serial}",
                self.client.identify_device(serial),
                context={"serial": serial},
            )

        # 5. Zone Actions (Overlays & Resumes)
        await self._execute_zone_actions(merged)

    async def _execute_zone_properties(self, merged: dict[str, Any]) -> None:
        """Execute v3-specific zone property updates."""
        rollback_away_temps = merged.get("rollback_away_temps", {})
        for zid, temp in merged["away_temps"].items():
            if self._should_skip_zone(zid):  # [DUMMY_HOOK]
                continue

            await self._safe_execute(
                f"away_temp_{zid}",
                self.client.set_away_configuration(zid, temp),
                rollback_fn=self._create_away_temp_rollback(
                    zid, rollback_away_temps.get(zid)
                ),
                success_fn=lambda zid=zid, t=temp: (
                    self.coordinator.optimistic.set_away_temp(zid, t, grace_period=2.0)
                ),
                context={"zone_id": zid, "temp": temp},
            )

        rollback_dazzle_modes = merged.get("rollback_dazzle_modes", {})
        for zid, enabled in merged["dazzle_modes"].items():
            if self._should_skip_zone(zid):  # [DUMMY_HOOK]
                continue

            await self._safe_execute(
                f"dazzle_{zid}",
                self.client.set_dazzle_mode(zid, enabled),
                rollback_fn=self._create_dazzle_rollback(
                    zid, rollback_dazzle_modes.get(zid)
                ),
                success_fn=lambda zid=zid, e=enabled: (
                    self.coordinator.optimistic.set_dazzle(zid, e, grace_period=2.0)
                ),
                context={"zone_id": zid, "enabled": enabled},
            )

        rollback_early_starts = merged.get("rollback_early_starts", {})
        for zid, enabled in merged["early_starts"].items():
            if self._should_skip_zone(zid):  # [DUMMY_HOOK]
                continue

            await self._safe_execute(
                f"early_start_{zid}",
                self.client.set_early_start(zid, enabled),
                rollback_fn=self._create_early_start_rollback(
                    zid, rollback_early_starts.get(zid)
                ),
                success_fn=lambda zid=zid, e=enabled: (
                    self.coordinator.optimistic.set_early_start(
                        zid, e, grace_period=2.0
                    )
                ),
                context={"zone_id": zid, "enabled": enabled},
            )

        rollback_open_windows = merged.get("rollback_open_windows", {})
        for zid, data in merged["open_windows"].items():
            if self._should_skip_zone(zid):  # [DUMMY_HOOK]
                continue

            # Capture timeout for the lambda closure
            timeout = data.get("timeout_seconds") or 0
            enabled = data["enabled"]

            await self._safe_execute(
                f"open_window_{zid}",
                self.client.set_open_window_detection(zid, enabled, timeout),
                rollback_fn=self._create_open_window_rollback(
                    zid, rollback_open_windows.get(zid)
                ),
                success_fn=lambda zid=zid, t=timeout, e=enabled: (
                    self.coordinator.optimistic.set_open_window(
                        zid, t if e else 0, grace_period=2.0
                    )
                ),
                context={
                    "zone_id": zid,
                    "enabled": enabled,
                    "timeout_seconds": timeout,
                },
            )

    async def _execute_zone_actions(self, merged: dict[str, Any]) -> None:
        """Execute overlays and resumes using v3 bulk endpoints."""
        zones = merged["zones"]
        if not zones:
            return

        rollback_zones = merged.get("rollback_zones", {})

        # Separate actions by zone type and operation
        heating_resumes, heating_overlays, hw_actions = self._group_zone_actions(zones)

        if heating_resumes:
            if real_resumes := self._filter_real_zones(heating_resumes):

                def _on_success_bulk(zid_list: list[int] = real_resumes) -> None:
                    for zid in zid_list:
                        self.coordinator.optimistic.clear_zone(zid)

                await self._safe_execute(
                    "bulk_resume",
                    self.client.reset_all_zones_overlay(real_resumes),
                    rollback_fn=self._create_zones_rollback(
                        real_resumes, rollback_zones
                    ),
                    success_fn=_on_success_bulk,
                    context={"zones": real_resumes},
                )

        if heating_overlays:
            if real_overlays := self._filter_real_overlays(heating_overlays):
                overlay_zone_ids = [ov["room"] for ov in real_overlays]
                await self._safe_execute(
                    "bulk_overlay",
                    self.client.set_all_zones_overlay(real_overlays),
                    rollback_fn=self._create_zones_rollback(
                        overlay_zone_ids, rollback_zones
                    ),
                    # Bulk overlays don't easily map back to optimistic per-field states here,
                    # but CommandMerger already handled optimistic SET during queueing.
                    context={"overlays": real_overlays},
                )

        if hw_actions:
            await self._execute_hw_actions(hw_actions, rollback_zones)

    def _group_zone_actions(
        self, zones: dict[int, dict[str, Any] | None]
    ) -> tuple[list[int], list[dict[str, Any]], dict[int, dict[str, Any] | None]]:
        """Separate actions by zone type and operation."""
        resumes, overlays, hw = [], [], {}
        for zid, data in zones.items():
            z = self.coordinator.zones_meta.get(zid)
            if z and z.type == "HOT_WATER":
                hw[zid] = data
            elif data is None:
                resumes.append(zid)
            else:
                # Rebuild overlay from merged data (magic number mapping)
                setting = data.get("setting", {})
                temp_dict = setting.get("temperature", {})
                temp = temp_dict.get("celsius")

                # Magic number mapping: temp=-1 → power=OFF (last call wins)
                _final_temp, power = map_magic_temp_to_power(temp)

                overlay_data = data
                if power == "OFF":
                    # Rebuild setting for OFF mode
                    setting = {**setting, "power": "OFF"}
                    if "temperature" in setting:
                        del setting["temperature"]
                    overlay_data = {**data, "setting": setting}

                overlays.append({"room": zid, "overlay": overlay_data})
        return resumes, overlays, hw

    async def _execute_hw_actions(
        self, actions: dict[int, dict[str, Any] | None], rollback_zones: dict[int, Any]
    ) -> None:
        """Execute hot water actions individually (not bulk)."""
        for zid, data in actions.items():
            # [DUMMY_HOOK] Intercept dummy hot water commands
            if self._intercept_zone_command(zid, data):
                continue

            def _on_success(zone_id: int = zid, payload: Any = data) -> None:
                if payload is None:
                    self.coordinator.optimistic.clear_zone(zone_id)
                else:
                    setting = payload.get("setting", {})
                    self.coordinator.optimistic.apply_zone_state(
                        zone_id,
                        overlay=True,
                        power=setting.get("power"),
                        temperature=setting.get("temperature", {}).get("celsius"),
                        grace_period=2.0,
                    )

            await self._safe_execute(
                f"hot_water_{zid}",
                self.client.reset_hot_water_zone_overlay(zid)
                if data is None
                else self.client.set_hot_water_zone_overlay(zid, data),
                rollback_fn=self._create_zones_rollback([zid], rollback_zones),
                success_fn=_on_success,
                context={"zone_id": zid, "payload": data},
            )
