"""Redundancy checker for optimizing API calls by skipping no-op operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..const import POWER_OFF, POWER_ON, TEMP_STRICT_TOLERANCE, TEMP_TOLERANCE
from ..models import CommandType, TadoCommand
from .logging_utils import get_redacted_logger

if TYPE_CHECKING:
    from .action_provider_base import TadoActionProvider
    from .optimistic import OptimisticState

_LOGGER = get_redacted_logger(__name__)


def preserve_rollback_state(existing: TadoCommand, replacement: TadoCommand) -> None:
    """Carry forward the original rollback state when a pending command is replaced.

    Ensures the redundancy filter always compares against the confirmed API state,
    not the optimistic intermediate state from a previous replacement in the debounce chain.
    """
    if existing.cmd_type == CommandType.SET_PRESENCE:
        if replacement.data is not None and existing.data is not None:
            if (original := existing.data.get("old_presence")) is not None:
                replacement.data["old_presence"] = original
    elif existing.rollback_context is not None:
        replacement.rollback_context = existing.rollback_context


def _check_presence_redundancy(
    command: TadoCommand, optimistic: OptimisticState
) -> bool:
    """Check if SET_PRESENCE is redundant."""
    if not command.data:
        return False

    target_presence = command.data.get("presence")
    old_presence = command.data.get("old_presence")

    if old_presence is None:
        return False

    if old_presence == target_presence:
        _LOGGER.debug(
            "Skipping redundant SET_PRESENCE: already %s",
            target_presence,
        )
        return True

    return False


def _check_overlay_redundancy(
    command: TadoCommand, optimistic: OptimisticState
) -> bool:
    """Check if SET_OVERLAY is redundant."""
    zone_id = command.zone_id
    if not zone_id or not command.data:
        return False

    setting = command.data.get("setting", {})
    target_power = setting.get("power")
    target_temp = (setting.get("temperature") or {}).get("celsius")

    cache_state = optimistic.get_zone(zone_id)
    if not cache_state:
        return False

    cache_power = cache_state.get("power")
    if cache_power is None or target_power != cache_power:
        return False

    # Both OFF → redundant
    if target_power == POWER_OFF:
        _LOGGER.debug("Skipping redundant SET_OVERLAY zone_%s: both OFF", zone_id)
        return True

    # Both ON → check temperature
    if target_temp is not None:
        cache_temp = cache_state.get("temperature")
        if cache_temp is None:
            return False

        if abs(cache_temp - target_temp) < TEMP_TOLERANCE:
            _LOGGER.debug(
                "Skipping redundant SET_OVERLAY zone_%s: power=%s, temp=%s",
                zone_id,
                target_power,
                target_temp,
            )
            return True

    return False


def _check_resume_redundancy(command: TadoCommand, optimistic: OptimisticState) -> bool:
    """Check if RESUME_SCHEDULE is redundant."""
    zone_id = command.zone_id
    if not zone_id:
        return False

    cache_state = optimistic.get_zone(zone_id)
    if not cache_state:
        return False

    overlay_active = cache_state.get("overlay_active", True)
    if not overlay_active:
        _LOGGER.debug(
            "Skipping redundant RESUME_SCHEDULE zone_%s: already in schedule",
            zone_id,
        )
        return True

    return False


def _check_child_lock_redundancy(
    command: TadoCommand, optimistic: OptimisticState
) -> bool:
    """Check if SET_CHILD_LOCK is redundant."""
    if not command.data:
        return False

    serial_no = command.data.get("serial")
    target_enabled = command.data.get("enabled")

    if serial_no is None or target_enabled is None:
        return False

    cache_enabled = optimistic.get_child_lock(serial_no)
    if cache_enabled is None:
        return False

    if cache_enabled == target_enabled:
        _LOGGER.debug(
            "Skipping redundant SET_CHILD_LOCK %s: already %s",
            serial_no,
            target_enabled,
        )
        return True

    return False


def _check_offset_redundancy(command: TadoCommand, optimistic: OptimisticState) -> bool:
    """Check if SET_OFFSET is redundant."""
    if not command.data:
        return False

    serial_no = command.data.get("serial")
    target_offset = command.data.get("offset")

    if serial_no is None or target_offset is None:
        return False

    cache_offset = optimistic.get_offset(serial_no)
    if cache_offset is None:
        return False

    if abs(cache_offset - target_offset) < TEMP_STRICT_TOLERANCE:
        _LOGGER.debug(
            "Skipping redundant SET_OFFSET %s: already %s",
            serial_no,
            target_offset,
        )
        return True

    return False


def _check_away_temp_redundancy(
    command: TadoCommand, optimistic: OptimisticState
) -> bool:
    """Check if SET_AWAY_TEMP is redundant."""
    if not command.data:
        return False

    zone_id = command.data.get("zone_id")
    target_temp = command.data.get("temp")

    if zone_id is None or target_temp is None:
        return False

    cache_temp = optimistic.get_away_temp(zone_id)
    if cache_temp is None:
        return False

    if abs(cache_temp - target_temp) < TEMP_STRICT_TOLERANCE:
        _LOGGER.debug(
            "Skipping redundant SET_AWAY_TEMP zone_%s: already %s",
            zone_id,
            target_temp,
        )
        return True

    return False


def _check_dazzle_redundancy(command: TadoCommand, optimistic: OptimisticState) -> bool:
    """Check if SET_DAZZLE is redundant."""
    if not command.data:
        return False

    zone_id = command.data.get("zone_id")
    target_enabled = command.data.get("enabled")

    if zone_id is None or target_enabled is None:
        return False

    cache_enabled = optimistic.get_dazzle(zone_id)
    if cache_enabled is None:
        return False

    if cache_enabled == target_enabled:
        _LOGGER.debug(
            "Skipping redundant SET_DAZZLE zone_%s: already %s",
            zone_id,
            target_enabled,
        )
        return True

    return False


def _check_early_start_redundancy(
    command: TadoCommand, optimistic: OptimisticState
) -> bool:
    """Check if SET_EARLY_START is redundant."""
    if not command.data:
        return False

    zone_id = command.data.get("zone_id")
    target_enabled = command.data.get("enabled")

    if zone_id is None or target_enabled is None:
        return False

    cache_enabled = optimistic.get_early_start(zone_id)
    if cache_enabled is None:
        return False

    if cache_enabled == target_enabled:
        _LOGGER.debug(
            "Skipping redundant SET_EARLY_START zone_%s: already %s",
            zone_id,
            target_enabled,
        )
        return True

    return False


def _check_open_window_redundancy(
    command: TadoCommand, optimistic: OptimisticState
) -> bool:
    """Check if SET_OPEN_WINDOW is redundant."""
    if not command.data:
        return False

    zone_id = command.data.get("zone_id")
    target_enabled = command.data.get("enabled")
    target_timeout = command.data.get("timeout_seconds", 0)

    if zone_id is None or target_enabled is None:
        return False

    # Convert enabled to timeout (0 = disabled)
    target_timeout_val = target_timeout if target_enabled else 0

    cache_timeout = optimistic.get_open_window(zone_id)
    if cache_timeout is None:
        return False

    if cache_timeout == target_timeout_val:
        _LOGGER.debug(
            "Skipping redundant SET_OPEN_WINDOW zone_%s: already %s",
            zone_id,
            target_timeout_val,
        )
        return True

    return False


# Mapping of CommandType to redundancy checker function
_REDUNDANCY_CHECKERS = {
    CommandType.SET_PRESENCE: _check_presence_redundancy,
    CommandType.SET_OVERLAY: _check_overlay_redundancy,
    CommandType.RESUME_SCHEDULE: _check_resume_redundancy,
    CommandType.SET_CHILD_LOCK: _check_child_lock_redundancy,
    CommandType.SET_OFFSET: _check_offset_redundancy,
    CommandType.SET_AWAY_TEMP: _check_away_temp_redundancy,
    CommandType.SET_DAZZLE: _check_dazzle_redundancy,
    CommandType.SET_EARLY_START: _check_early_start_redundancy,
    CommandType.SET_OPEN_WINDOW: _check_open_window_redundancy,
}

# Commands that should always send (explicit user actions)
_ALWAYS_SEND_COMMANDS = {CommandType.MANUAL_POLL, CommandType.IDENTIFY}


def should_skip_state_change(
    command: TadoCommand,
    optimistic: OptimisticState,
    suppress_enabled: bool,
) -> bool:
    """Check if state change command should be skipped (cache matches target).

    Args:
        command: The command to check
        optimistic: Optimistic state cache
        suppress_enabled: Whether redundant call suppression is enabled

    Returns:
        True if command should be skipped, False otherwise

    """
    if not suppress_enabled or command.cmd_type in _ALWAYS_SEND_COMMANDS:
        return False

    try:
        if checker := _REDUNDANCY_CHECKERS.get(command.cmd_type):
            return checker(command, optimistic)

    except Exception as e:
        _LOGGER.warning("Error checking redundancy for %s: %s", command.cmd_type, e)
        return False  # On error, send to be safe

    return False


def should_skip_all_action(
    action_type: str,
    zone_ids: list[int],
    optimistic: OptimisticState,
    suppress_calls_enabled: bool,
    suppress_buttons_enabled: bool,
) -> bool:
    """Check if ALL-button action should be skipped (all zones match target).

    Args:
        action_type: Type of ALL action ("resume_all", "boost_all", "turn_off_all")
        zone_ids: List of zone IDs to check
        optimistic: Optimistic state cache
        suppress_calls_enabled: Whether redundant calls suppression is enabled
        suppress_buttons_enabled: Whether redundant buttons suppression is enabled

    Returns:
        True if ALL zones match target (skip), False otherwise

    """
    # Toggle 2 requires Toggle 1
    if not suppress_calls_enabled or not suppress_buttons_enabled:
        return False

    if not zone_ids:
        return False

    try:
        if action_type == "resume_all":
            # Check if ALL zones already in schedule
            for zone_id in zone_ids:
                cache_state = optimistic.get_zone(zone_id)
                if not cache_state:
                    return False  # No cache → send

                if overlay_active := cache_state.get("overlay_active", True):
                    return False  # At least one needs resume → send

            # All zones in schedule
            _LOGGER.info(
                "Skipping resume_all_schedules: all %d zones already in schedule",
                len(zone_ids),
            )
            return True

        elif action_type == "boost_all":
            # Check if ALL zones already at 25°C manual
            BOOST_TEMP = 25.0
            for zone_id in zone_ids:
                cache_state = optimistic.get_zone(zone_id)
                if not cache_state:
                    return False

                cache_power = cache_state.get("power")
                cache_temp = cache_state.get("temperature")
                overlay_active = cache_state.get("overlay_active", False)

                # Needs: power=ON, temp=25°C, overlay active (manual)
                if (
                    cache_power != POWER_ON
                    or cache_temp is None
                    or abs(cache_temp - BOOST_TEMP) > TEMP_TOLERANCE
                    or not overlay_active
                ):
                    return False  # At least one needs boost → send

            # All zones boosted
            _LOGGER.info(
                "Skipping boost_all_zones: all %d zones already at 25°C manual",
                len(zone_ids),
            )
            return True

        elif action_type == "turn_off_all":
            # Check if ALL zones already OFF
            for zone_id in zone_ids:
                cache_state = optimistic.get_zone(zone_id)
                if not cache_state:
                    return False

                cache_power = cache_state.get("power")
                if cache_power != POWER_OFF:
                    return False  # At least one is ON → send

            # All zones OFF
            _LOGGER.info(
                "Skipping turn_off_all_zones: all %d zones already OFF",
                len(zone_ids),
            )
            return True

    except Exception as e:
        _LOGGER.warning("Error checking redundancy for %s: %s", action_type, e)
        return False  # On error, send to be safe

    return False


def should_skip_all_action_provider(
    action_type: str,
    action_provider: TadoActionProvider,
    suppress_calls: bool,
    suppress_buttons: bool,
) -> bool:
    """Check if ALL-button action should be skipped using ActionProvider.

    Args:
        action_type: Type of ALL action ("resume_all", "boost_all", "turn_off_all")
        action_provider: Generation-specific action provider
        suppress_calls: Whether redundant calls suppression is enabled
        suppress_buttons: Whether redundant buttons suppression is enabled

    Returns:
        True if ALL zones match target (skip), False otherwise

    """
    # Toggle 2 requires Toggle 1
    if not suppress_calls or not suppress_buttons:
        return False

    zone_ids = action_provider.get_active_zone_ids(include_heating=True)
    if not zone_ids:
        return False

    try:
        if action_type == "boost_all":
            # Check if ALL zones already at 25°C manual
            BOOST_TEMP = 25.0
            for zone_id in zone_ids:
                power = action_provider.get_zone_power(zone_id)
                temp = action_provider.get_zone_temperature(zone_id)
                in_schedule = action_provider.is_zone_in_schedule(zone_id)

                # Needs: power=ON, temp=25°C, NOT in schedule (manual)
                if (
                    power != POWER_ON
                    or temp is None
                    or abs(temp - BOOST_TEMP) > TEMP_TOLERANCE
                    or in_schedule  # in_schedule=True means no overlay
                ):
                    return False  # At least one needs boost → send

            _LOGGER.info(
                "Skipping boost_all_zones: all %d zones already at 25°C manual",
                len(zone_ids),
            )
            return True

        elif action_type == "resume_all":
            # Check if ALL zones already in schedule
            for zone_id in zone_ids:
                if not action_provider.is_zone_in_schedule(zone_id):
                    return False  # At least one needs resume → send

            _LOGGER.info(
                "Skipping resume_all_schedules: all %d zones already in schedule",
                len(zone_ids),
            )
            return True

        elif action_type == "turn_off_all":
            # Check if ALL zones already OFF
            for zone_id in zone_ids:
                if action_provider.get_zone_power(zone_id) != POWER_OFF:
                    return False  # At least one is ON → send

            _LOGGER.info(
                "Skipping turn_off_all_zones: all %d zones already OFF",
                len(zone_ids),
            )
            return True

    except Exception as e:
        _LOGGER.warning("Error checking redundancy for %s: %s", action_type, e)
        return False  # On error, send to be safe

    return False


def _is_resume_redundant(
    zone_id: int, zone_states: dict[str, Any], suppress_buttons: bool
) -> bool:
    """Return True if a RESUME_SCHEDULE command is redundant."""
    if not suppress_buttons:
        return False
    state = zone_states.get(str(zone_id))
    return state is not None and not getattr(state, "overlay_active", True)


def _is_overlay_redundant(
    zone_id: int, zone_data: dict[str, Any], zone_states: dict[str, Any]
) -> bool:
    """Return True if a SET_OVERLAY command matches current device state."""
    state = zone_states.get(str(zone_id))
    if state is None or not getattr(state, "overlay_active", False):
        return False

    setting = zone_data.get("setting", {})
    target_power = setting.get("power")

    api_setting = getattr(state, "setting", None)
    cache_power = getattr(api_setting, "power", None) if api_setting else None

    if cache_power is None or target_power != cache_power:
        return False

    if target_power == POWER_OFF:
        return True

    target_temp = (setting.get("temperature") or {}).get("celsius")
    if target_temp is None:
        return False

    cache_temp_obj = getattr(api_setting, "temperature", None)
    cache_temp = (
        getattr(cache_temp_obj, "celsius", None) if cache_temp_obj is not None else None
    )
    return cache_temp is not None and abs(cache_temp - target_temp) < TEMP_TOLERANCE


def _filter_zone_updates(
    merged: dict[str, Any],
    zone_states: dict[str, Any],
    suppress_buttons: bool = False,
) -> dict[str, Any]:
    """Filter redundant zone updates from merged data.

    Compares against pre-patch states (cmd.rollback_context) captured before
    optimistic patching. coordinator.data.zone_states is mutated in-place by
    state_patcher before queuing, so it already reflects the target by batch time.
    """
    if not (zones := merged.get("zones", {})):
        return merged

    filtered_zones: dict[str, Any] = {}
    for zone_id_str, zone_data in zones.items():
        zone_id = int(zone_id_str)

        if zone_data is None and _is_resume_redundant(
            zone_id, zone_states, suppress_buttons
        ):
            _LOGGER.debug(
                "Skipping redundant RESUME_SCHEDULE zone_%s: already in schedule",
                zone_id,
            )
        elif (
            zone_data is None
            and not _is_resume_redundant(zone_id, zone_states, suppress_buttons)
        ) or (
            zone_data is not None
            and not _is_overlay_redundant(zone_id, zone_data, zone_states)
        ):
            filtered_zones[zone_id_str] = zone_data
        else:
            setting = zone_data.get("setting", {})
            _LOGGER.debug(
                "Skipping redundant zone_%s overlay: power=%s, temp=%s",
                zone_id,
                setting.get("power"),
                (setting.get("temperature") or {}).get("celsius"),
            )
    merged["zones"] = filtered_zones
    return merged


def _filter_simple_attributes(
    merged: dict[str, Any],
    attribute_name: str,
    rollback_key: str,
    log_name: str,
) -> dict[str, Any]:
    """Filter redundant simple attributes using pre-patch rollback values."""
    rollback = merged.get(rollback_key, {})
    if attributes := merged.get(attribute_name, {}):
        filtered = {}
        for key, value in attributes.items():
            old_value = rollback.get(key)
            if old_value is None or old_value != value:
                filtered[key] = value
            else:
                _LOGGER.debug(
                    "Skipping redundant %s %s: already %s", log_name, key, value
                )
        merged[attribute_name] = filtered
    return merged


def _filter_presence(merged: dict[str, Any]) -> dict[str, Any]:
    """Filter redundant presence updates."""
    if presence := merged.get("presence"):
        old_presence = merged.get("old_presence")
        if old_presence is not None and old_presence == presence:
            _LOGGER.debug("Skipping redundant presence: already %s", presence)
            merged.pop("presence", None)
    return merged


def filter_redundant_merged_data(
    merged: dict[str, Any],
    zone_states: dict[str, Any],
    suppress_enabled: bool,
    suppress_buttons: bool = False,
) -> dict[str, Any]:
    """Filter redundant operations from merged batch data.

    Checks each part of the merged payload against cached state and removes
    redundant operations to save API quota.

    Args:
        merged: Merged command data from CommandMerger
        zone_states: Pre-patch states from cmd.rollback_context (state before optimistic patch)
        suppress_enabled: Whether redundant call suppression is enabled

    Returns:
        Filtered merged data with redundant operations removed

    """
    if not suppress_enabled:
        return merged  # No filtering

    _SIMPLE_FILTERS = [
        ("child_lock", "rollback_child_locks", "child_lock"),
        ("offsets", "rollback_offsets", "offset"),
        ("away_temps", "rollback_away_temps", "away_temp zone"),
        ("dazzle_modes", "rollback_dazzle_modes", "dazzle zone"),
        ("early_starts", "rollback_early_starts", "early_start zone"),
        ("open_windows", "rollback_open_windows", "open_window zone"),
    ]

    try:
        merged = _filter_zone_updates(merged, zone_states, suppress_buttons)

        for attr, rollback_key, log_name in _SIMPLE_FILTERS:
            merged = _filter_simple_attributes(merged, attr, rollback_key, log_name)

        merged = _filter_presence(merged)

    except Exception as e:
        _LOGGER.warning("Error filtering redundant merged data: %s", e)
        # On error, return original to be safe

    return merged
