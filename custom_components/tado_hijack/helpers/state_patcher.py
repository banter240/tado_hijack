"""Helpers for patching local state models for optimistic updates."""

from __future__ import annotations

import copy
from typing import Any

from tadoasync.models import Overlay, Temperature, Termination

from .logging_utils import get_redacted_logger
from ..lib.tadox_models import HopsTemperature, ManualControlTermination

_LOGGER = get_redacted_logger(__name__)


def patch_zone_overlay(
    current_state: Any | None, overlay_data: dict[str, Any]
) -> Any | None:
    """Patch local zone state with overlay data and return old state for rollback."""
    if current_state is None:
        return None

    try:
        old_state = copy.deepcopy(current_state)
    except Exception as e:
        _LOGGER.warning("Failed to copy state for zone: %s", e)
        return None

    try:
        if hasattr(current_state, "manual_control_termination"):
            _patch_zone_overlay_tadox(current_state, overlay_data)
        else:
            _patch_zone_overlay_v3(current_state, overlay_data)
    except Exception as e:
        _LOGGER.warning("Error patching local state for zone: %s", e)
        return None

    return old_state


def _patch_zone_overlay_tadox(current_state: Any, overlay_data: dict[str, Any]) -> None:
    """Apply overlay patch for Tado X (Pydantic Models)."""
    sett_d = overlay_data.get("setting", {})
    term_d = overlay_data.get("termination", {})

    # 1. Update Setting
    if current_state.setting:
        if "power" in sett_d:
            current_state.setting.power = sett_d["power"]
        if "temperature" in sett_d and "celsius" in sett_d["temperature"]:
            val = float(sett_d["temperature"]["celsius"])
            if current_state.setting.temperature:
                current_state.setting.temperature.value = val
            else:
                current_state.setting.temperature = HopsTemperature(value=val)

    # 2. Create Termination
    type_str = term_d.get("typeSkillBasedApp", "MANUAL")
    # Map Tado API "TIMER" -> Tado X "TIMER" (same string)
    remaining = None
    if type_str == "TIMER" and "durationInSeconds" in term_d:
        remaining = int(term_d["durationInSeconds"])

    term_obj = ManualControlTermination(
        type=type_str,
        remainingTimeInSeconds=remaining,
        projectedExpiry=None,
    )

    # 3. Apply
    current_state.manual_control_termination = term_obj


def _patch_zone_overlay_v3(current_state: Any, overlay_data: dict[str, Any]) -> None:
    """Apply overlay patch for v3 Classic (PyTado Objects)."""
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


def patch_zone_resume(current_state: Any | None) -> Any | None:
    """Patch local zone state to resume schedule and return old state for rollback."""
    if current_state is None:
        return None

    try:
        old_state = copy.deepcopy(current_state)
    except Exception as e:
        _LOGGER.warning("Failed to copy state for zone: %s", e)
        return None

    try:
        if hasattr(current_state, "manual_control_termination"):
            _patch_zone_resume_tadox(current_state)
        else:
            _patch_zone_resume_v3(current_state)
    except Exception as e:
        _LOGGER.warning("Error patching resume state for zone: %s", e)
        return None

    return old_state


def _patch_zone_resume_tadox(current_state: Any) -> None:
    """Apply resume patch for Tado X."""
    current_state.manual_control_termination = None
    # Property 'overlay_active' on TadoXZoneState uses this field


def _patch_zone_resume_v3(current_state: Any) -> None:
    """Apply resume patch for v3 Classic."""
    current_state.overlay = None
    current_state.overlay_active = False
