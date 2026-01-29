"""Helpers for patching local state models for optimistic updates."""

from __future__ import annotations

import copy
import logging
from typing import Any

from tadoasync.models import Overlay, Temperature, Termination, ZoneState

_LOGGER = logging.getLogger(__name__)


def patch_zone_overlay(
    current_state: ZoneState | None, overlay_data: dict[str, Any]
) -> ZoneState | None:
    """Patch local zone state with overlay data and return old state for rollback."""
    if current_state is None:
        return None

    try:
        old_state = copy.deepcopy(current_state)
    except Exception as e:
        _LOGGER.warning("Failed to copy state for zone: %s", e)
        return None

    try:
        sett_d = overlay_data.get("setting", {})
        term_d = overlay_data.get("termination", {})

        if current_state.setting:
            if "power" in sett_d:
                current_state.setting.power = sett_d["power"]
            if "temperature" in sett_d and "celsius" in sett_d["temperature"]:
                val = float(sett_d["temperature"]["celsius"])
                if current_state.setting.temperature:
                    current_state.setting.temperature.celsius = val
                else:
                    current_state.setting.temperature = Temperature(
                        celsius=val, fahrenheit=0.0
                    )

        term_obj = Termination(
            type=term_d.get("typeSkillBasedApp", "MANUAL"),
            type_skill_based_app=term_d.get("typeSkillBasedApp"),
            projected_expiry=None,
        )

        current_state.overlay = Overlay(
            type="MANUAL",
            setting=current_state.setting,
            termination=term_obj,
        )
        current_state.overlay_active = True

    except Exception as e:
        _LOGGER.warning("Error patching local state for zone: %s", e)
        return None

    return old_state


def patch_zone_resume(current_state: ZoneState | None) -> ZoneState | None:
    """Patch local zone state to resume schedule and return old state for rollback."""
    if current_state is None:
        return None

    try:
        old_state = copy.deepcopy(current_state)
    except Exception as e:
        _LOGGER.warning("Failed to copy state for zone: %s", e)
        return None

    current_state.overlay = None
    current_state.overlay_active = False

    return old_state
