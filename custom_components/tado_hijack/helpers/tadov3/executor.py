"""Executor for Tado Classic (v3) batch commands using tadoasync."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..executor_base import TadoExecutorBase, map_magic_temp_to_power
from ..logging_utils import get_redacted_logger

if TYPE_CHECKING:
    from ..client import TadoHijackClient
    from ...coordinator import TadoDataUpdateCoordinator

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
        if merged["presence"]:
            await self._safe_execute(
                "presence",
                self.client.set_presence(merged["presence"]),
                rollback_fn=self._create_presence_rollback(merged.get("old_presence")),
                context={"presence": merged["presence"]},
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
                context={"zone_id": zid, "enabled": enabled},
            )

        rollback_open_windows = merged.get("rollback_open_windows", {})
        for zid, data in merged["open_windows"].items():
            if self._should_skip_zone(zid):  # [DUMMY_HOOK]
                continue

            await self._safe_execute(
                f"open_window_{zid}",
                self.client.set_open_window_detection(
                    zid, data["enabled"], data.get("timeout_seconds")
                ),
                rollback_fn=self._create_open_window_rollback(
                    zid, rollback_open_windows.get(zid)
                ),
                context={
                    "zone_id": zid,
                    "enabled": data["enabled"],
                    "timeout_seconds": data.get("timeout_seconds"),
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
                await self._safe_execute(
                    "bulk_resume",
                    self.client.reset_all_zones_overlay(real_resumes),
                    rollback_fn=self._create_zones_rollback(
                        real_resumes, rollback_zones
                    ),
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
                    context={"overlays": real_overlays},
                )

        if hw_actions:
            await self._execute_hw_actions(hw_actions, rollback_zones)

    def _group_zone_actions(
        self, zones: dict[int, dict[str, Any] | None]
    ) -> tuple[list[int], list[dict[str, Any]], dict[int, dict[str, Any] | None]]:
        """Separate actions by zone type and operation.

        Returns:
            (heating_resumes, heating_overlays, hot_water_actions)

        """
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
                final_temp, power = map_magic_temp_to_power(temp)

                if power == "OFF":
                    # Rebuild setting for OFF mode
                    setting = {**setting, "power": "OFF"}
                    if "temperature" in setting:
                        del setting["temperature"]
                    data = {**data, "setting": setting}

                overlays.append({"room": zid, "overlay": data})
        return resumes, overlays, hw

    async def _execute_hw_actions(
        self, actions: dict[int, dict[str, Any] | None], rollback_zones: dict[int, Any]
    ) -> None:
        """Execute hot water actions individually (not bulk)."""
        for zid, data in actions.items():
            # [DUMMY_HOOK] Intercept dummy hot water commands
            if self._intercept_zone_command(zid, data):
                continue

            await self._apply_jitter()
            try:
                if data is None:
                    await self.client.reset_hot_water_zone_overlay(zid)
                else:
                    await self.client.set_hot_water_zone_overlay(zid, data)
                _LOGGER.debug("Hot water command succeeded [zone_%d]", zid)
            except Exception as e:
                _LOGGER.error(
                    "Failed hot water overlay for zone %d: %s (type: %s). Payload: %s",
                    zid,
                    e,
                    type(e).__name__,
                    data,
                    exc_info=True,
                )
                # Rollback
                rollback_fn = self._create_zones_rollback([zid], rollback_zones)
                await rollback_fn()
                _LOGGER.info("Rolled back [hot_water_zone_%d]", zid)
