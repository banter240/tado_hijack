"""Redundancy checker for optimizing API calls by skipping no-op operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from collections.abc import Callable

from ..const import POWER_OFF, POWER_ON
from ..models import CommandType, TadoCommand
from .logging_utils import get_redacted_logger

if TYPE_CHECKING:
    from .action_provider_base import TadoActionProvider
    from .optimistic import OptimisticState

_LOGGER = get_redacted_logger(__name__)


def _check_presence_redundancy(
    command: TadoCommand, optimistic: OptimisticState
) -> bool:
    """Check if SET_PRESENCE is redundant."""
    if not command.data:
        return False

    target_presence = command.data.get("presence")
    cache_presence = optimistic.get_presence()

    if cache_presence is None:
        return False

    if cache_presence == target_presence:
        _LOGGER.debug(
            "Skipping redundant SET_PRESENCE: cache=%s, target=%s",
            cache_presence,
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
    target_temp = setting.get("temperature", {}).get("celsius")

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

        if abs(cache_temp - target_temp) < 0.1:
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

    if abs(cache_offset - target_offset) < 0.01:  # Float comparison
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

    if abs(cache_temp - target_temp) < 0.01:  # Float comparison
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
                    or abs(cache_temp - BOOST_TEMP) > 0.1
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
                    or abs(temp - BOOST_TEMP) > 0.1
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


def _filter_zone_updates(
    merged: dict[str, Any],
    action_provider: TadoActionProvider,
) -> dict[str, Any]:
    """Filter redundant zone updates from merged data."""
    if zones := merged.get("zones", {}):
        filtered_zones = {}
        for zone_id_str, zone_data in zones.items():
            zone_id = int(zone_id_str)

            setting = zone_data.get("setting", {})
            target_power = setting.get("power")
            target_temp = setting.get("temperature", {}).get("celsius")

            cache_power = action_provider.get_zone_power(zone_id)
            cache_temp = action_provider.get_zone_temperature(zone_id)

            # No cache data → send
            if cache_power is None:
                filtered_zones[zone_id_str] = zone_data
                continue

            # Check if redundant
            is_redundant = False

            # If power differs → not redundant
            if target_power != cache_power:
                pass  # Send
            # If both OFF and match → redundant
            elif target_power == POWER_OFF and cache_power == POWER_OFF:
                is_redundant = True
                _LOGGER.debug("Skipping redundant zone_%s overlay: both OFF", zone_id)
            # If ON, check temperature
            elif target_power == POWER_ON and target_temp is not None:
                if cache_temp is not None and abs(cache_temp - target_temp) < 0.1:
                    is_redundant = True
                    _LOGGER.debug(
                        "Skipping redundant zone_%s overlay: power=%s, temp=%s",
                        zone_id,
                        target_power,
                        target_temp,
                    )

            if not is_redundant:
                filtered_zones[zone_id_str] = zone_data

        merged["zones"] = filtered_zones
    return merged


def _filter_simple_attributes(
    merged: dict[str, Any],
    optimistic: OptimisticState,
    attribute_name: str,
    cache_getter: Callable[[Any], Any],
    log_name: str,
) -> dict[str, Any]:
    """Filter redundant simple attributes (child_lock, offsets, etc.)."""
    if attributes := merged.get(attribute_name, {}):
        filtered = {}
        for key, value in attributes.items():
            cache_value = cache_getter(key)
            if cache_value is None or cache_value != value:
                filtered[key] = value
            else:
                _LOGGER.debug(
                    "Skipping redundant %s %s: already %s", log_name, key, value
                )
        merged[attribute_name] = filtered
    return merged


def _filter_presence(
    merged: dict[str, Any],
    optimistic: OptimisticState,
) -> dict[str, Any]:
    """Filter redundant presence updates."""
    if presence := merged.get("presence"):
        cache_presence = optimistic.get_presence()
        if cache_presence is not None and cache_presence == presence:
            _LOGGER.debug("Skipping redundant presence: already %s", presence)
            merged.pop("presence", None)
    return merged


def filter_redundant_merged_data(
    merged: dict[str, Any],
    action_provider: TadoActionProvider,
    optimistic: OptimisticState,
    suppress_enabled: bool,
) -> dict[str, Any]:
    """Filter redundant operations from merged batch data.

    Checks each part of the merged payload against cached state and removes
    redundant operations to save API quota.

    Args:
        merged: Merged command data from CommandMerger
        action_provider: Generation-specific action provider for state checks
        optimistic: Optimistic state manager for cache lookups
        suppress_enabled: Whether redundant call suppression is enabled

    Returns:
        Filtered merged data with redundant operations removed

    """
    if not suppress_enabled:
        return merged  # No filtering

    try:
        # Filter zone updates
        merged = _filter_zone_updates(merged, action_provider)

        # Filter simple attributes
        merged = _filter_simple_attributes(
            merged, optimistic, "child_lock", optimistic.get_child_lock, "child_lock"
        )
        merged = _filter_simple_attributes(
            merged, optimistic, "offsets", optimistic.get_offset, "offset"
        )
        merged = _filter_simple_attributes(
            merged,
            optimistic,
            "away_temps",
            lambda zid: optimistic.get_away_temp(int(zid)),
            "away_temp zone",
        )
        merged = _filter_simple_attributes(
            merged,
            optimistic,
            "dazzle_modes",
            lambda zid: optimistic.get_dazzle(int(zid)),
            "dazzle zone",
        )
        merged = _filter_simple_attributes(
            merged,
            optimistic,
            "early_starts",
            lambda zid: optimistic.get_early_start(int(zid)),
            "early_start zone",
        )
        merged = _filter_simple_attributes(
            merged,
            optimistic,
            "open_windows",
            lambda zid: optimistic.get_open_window(int(zid)),
            "open_window zone",
        )

        # Filter presence
        merged = _filter_presence(merged, optimistic)

    except Exception as e:
        _LOGGER.warning("Error filtering redundant merged data: %s", e)
        # On error, return original to be safe

    return merged
