"""Base executor for Tado API commands.

Provides common execution logic for v3 and X executors.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

from tadoasync.models import TemperatureOffset

from ..const import CONF_API_PROXY_URL, CONF_CALL_JITTER_ENABLED, OFF_MAGIC_TEMP
from .logging_utils import get_redacted_logger
from .utils import apply_jitter

if TYPE_CHECKING:
    from ..coordinator import TadoDataUpdateCoordinator

_LOGGER = get_redacted_logger(__name__)


def map_magic_temp_to_power(temp: float | None) -> tuple[float | None, str]:
    """Map magic temperature value to final temperature and power state.

    Magic number convention: temp=OFF_MAGIC_TEMP means OFF mode (last-call-wins merge logic).

    Args:
        temp: Temperature from merged overlay (may be magic number OFF_MAGIC_TEMP)

    Returns:
        (final_temperature, power_state) tuple:
        - (None, "OFF") if temp is magic number OFF_MAGIC_TEMP
        - (temp, "ON") for normal temperatures

    """
    return (None, "OFF") if temp == OFF_MAGIC_TEMP else (temp, "ON")


class TadoExecutorBase(ABC):
    """Base class for Tado command executors.

    Provides common execution patterns (safe execute, jitter, error handling).
    Subclasses implement generation-specific API calls.
    """

    def __init__(self, coordinator: TadoDataUpdateCoordinator, jitter_percent: float):
        """Initialize base executor."""
        self.coordinator = coordinator
        self._jitter_percent = jitter_percent

    async def _safe_execute(
        self,
        label: str,
        coro: Any,
        rollback_fn: Any = None,
        success_fn: Any = None,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """Execute command with error handling and optional rollback/success handlers.

        Args:
            label: Human-readable label for logging
            coro: Coroutine to execute
            rollback_fn: Optional async or sync function to call on failure
            success_fn: Optional async or sync function to call on success
            context: Optional dict with context data for logging

        Returns:
            True if successful, False otherwise

        """
        await self._apply_jitter()

        # Log payload before execution
        if context:
            _LOGGER.debug("Executor sending [%s]: %s", label, context)

        try:
            await coro
            _LOGGER.debug("Executor succeeded [%s]", label)

            # Handle Success Callback (Adaptive Shield Reset etc.)
            if success_fn:
                if asyncio.iscoroutine(res := success_fn()):
                    await res

            return True
        except Exception as e:
            if context:
                _LOGGER.error(
                    "Executor failed [%s]: %s (type: %s). Context: %s",
                    label,
                    e,
                    type(e).__name__,
                    context,
                )
            else:
                _LOGGER.error(
                    "Executor failed [%s]: %s (type: %s)",
                    label,
                    e,
                    type(e).__name__,
                )

            # Handle Rollback Callback
            if rollback_fn:
                if asyncio.iscoroutine(res := rollback_fn()):
                    await res
                _LOGGER.info("Rolled back [%s]", label)

            return False

    async def _apply_jitter(self) -> None:
        """Apply jitter delay to prevent API hammering."""
        # Check if jitter is enabled via config (only for proxy)
        if not self.coordinator.config_entry.data.get(CONF_API_PROXY_URL):
            return  # No proxy, no jitter

        if not self.coordinator.config_entry.data.get(CONF_CALL_JITTER_ENABLED):
            return  # Jitter disabled by user

        delay = apply_jitter(0.5, self._jitter_percent)
        if delay > 0:
            _LOGGER.debug("Applying jitter delay: %.3fs", delay)
        await asyncio.sleep(delay)

    # Centralized Dummy Handler Helpers (DRY for v3 and X executors)

    def _should_skip_zone(self, zone_id: int) -> bool:
        """Check if a zone should be skipped (is dummy)."""
        handler = self.coordinator.dummy_handler
        return bool(handler and handler.is_dummy_zone(zone_id))

    def _filter_real_zones(self, zone_ids: list[int]) -> list[int]:
        """Filter out dummy zones and intercept them, return real zones."""
        if handler := self.coordinator.dummy_handler:
            return handler.filter_and_intercept_resume(zone_ids)
        else:
            return zone_ids

    def _filter_real_overlays(
        self, overlays: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Filter out dummy overlays and intercept them, return real overlays."""
        if handler := self.coordinator.dummy_handler:
            return handler.filter_and_intercept_overlays(overlays)
        else:
            return overlays

    def _intercept_zone_command(self, zone_id: int, data: Any) -> bool:
        """Intercept a zone command if it's for a dummy zone. Returns True if intercepted."""
        handler = self.coordinator.dummy_handler
        if handler and handler.is_dummy_zone(zone_id):
            handler.intercept_command(zone_id, data)
            return True
        return False

    # Centralized Rollback Helpers (DRY)

    def _rollback_optimistic(
        self,
        scope: str,
        entity_id: str | int,
        key: str,
        restore_fn: Callable[[], Any] | None = None,
    ) -> Callable[[], Coroutine[Any, Any, None]]:
        """Create a standard rollback that clears optimistic state and restores data."""

        async def rollback() -> None:
            self.coordinator.optimistic.clear_optimistic(scope, entity_id, key)
            if restore_fn:
                if asyncio.iscoroutine(res := restore_fn()):
                    await res
                else:
                    restore_fn()
            self.coordinator.async_update_listeners()

        return rollback

    def _create_presence_rollback(
        self, old_presence: str | None
    ) -> Callable[[], Coroutine[Any, Any, None]]:
        """Create rollback function for presence."""

        async def restore() -> None:
            if old_presence and self.coordinator.data.home_state:
                _LOGGER.info("Rolling back local presence state to %s", old_presence)
                self.coordinator.data.home_state.presence = old_presence
            else:
                _LOGGER.info("Triggering manual poll to recover presence state")
                await self.coordinator.async_manual_poll("presence")

        return self._rollback_optimistic("home", "global", "presence", restore)

    def _create_child_lock_rollback(
        self, serial: str, old_val: bool | None
    ) -> Callable[[], Coroutine[Any, Any, None]]:
        """Create rollback function for child lock."""

        def restore() -> None:
            if old_val is not None and (
                dev := self.coordinator.devices_meta.get(serial)
            ):
                dev.child_lock_enabled = old_val
                _LOGGER.info("Rolled back child_lock for %s", serial)

        return self._rollback_optimistic("device", serial, "child_lock", restore)

    def _create_offset_rollback(
        self, serial: str, old_val: float | None
    ) -> Callable[[], Coroutine[Any, Any, None]]:
        """Create rollback function for temperature offset."""

        def restore() -> None:
            if old_val is not None:
                self.coordinator.data_manager.offsets_cache[serial] = TemperatureOffset(
                    celsius=old_val, fahrenheit=old_val * 1.8 + 32
                )
                _LOGGER.info("Rolled back offset for %s", serial)

        return self._rollback_optimistic("device", serial, "offset", restore)

    def _create_away_temp_rollback(
        self, zone_id: int, old_val: float | None
    ) -> Callable[[], Coroutine[Any, Any, None]]:
        """Create rollback function for away temperature."""

        def restore() -> None:
            if old_val is not None:
                self.coordinator.data_manager.away_cache[zone_id] = old_val
            else:
                # Was OFF before: restore by removing the key
                self.coordinator.data_manager.away_cache.pop(zone_id, None)
            _LOGGER.info("Rolled back away temp for zone %d", zone_id)

        return self._rollback_optimistic("zone", zone_id, "away_temp", restore)

    def _create_dazzle_rollback(
        self, zone_id: int, old_val: bool | None
    ) -> Callable[[], Coroutine[Any, Any, None]]:
        """Create rollback function for dazzle mode."""

        def restore() -> None:
            if old_val is not None and (
                zone := self.coordinator.zones_meta.get(zone_id)
            ):
                zone.dazzle_enabled = old_val
                _LOGGER.info("Rolled back dazzle for zone %d", zone_id)

        return self._rollback_optimistic("zone", zone_id, "dazzle", restore)

    def _create_early_start_rollback(
        self, zone_id: int, old_val: bool | None
    ) -> Callable[[], Coroutine[Any, Any, None]]:
        """Create rollback function for early start."""

        def restore() -> None:
            if old_val is not None and (
                zone := self.coordinator.zones_meta.get(zone_id)
            ):
                if hasattr(zone, "early_start_enabled"):
                    zone.early_start_enabled = old_val
                _LOGGER.info("Rolled back early start for zone %d", zone_id)

        return self._rollback_optimistic("zone", zone_id, "early_start", restore)

    def _create_open_window_rollback(
        self, zone_id: int, old_val: Any
    ) -> Callable[[], Coroutine[Any, Any, None]]:
        """Create rollback function for open window detection."""

        def restore() -> None:
            if old_val is not None and (
                zone := self.coordinator.zones_meta.get(zone_id)
            ):
                if zone.open_window_detection:
                    if isinstance(old_val, tuple):
                        zone.open_window_detection.enabled = old_val[0]
                        zone.open_window_detection.timeout_in_seconds = old_val[1]
                    else:
                        zone.open_window_detection.enabled = old_val
                    _LOGGER.info("Rolled back open window for zone %d", zone_id)

        return self._rollback_optimistic("zone", zone_id, "open_window", restore)

    def _create_zones_rollback(
        self, zone_ids: list[int], rollback_data: dict[int, Any]
    ) -> Callable[[], Coroutine[Any, Any, None]]:
        """Create rollback function for zone states with logging and data restoration."""

        async def rollback() -> None:
            restored = False
            for zid in zone_ids:
                self.coordinator.optimistic.clear_zone(zid)
                if old_state := rollback_data.get(zid):
                    if self.coordinator.data.zone_states:
                        str_id = str(zid)
                        self.coordinator.data.zone_states[str_id] = old_state
                        restored = True
            if restored:
                _LOGGER.info("Rolled back local state for zones: %s", zone_ids)
                self.coordinator.async_update_listeners()

        return rollback

    @abstractmethod
    async def execute_batch(self, merged: dict[str, Any]) -> None:
        """Execute a batch of merged commands.

        Args:
            merged: Merged command dictionary from CommandMerger

        """
        ...
