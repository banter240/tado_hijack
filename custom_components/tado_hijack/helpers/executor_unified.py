"""Unified Executor Gateway for Tado Hijack.

This class acts as a dispatcher between Tado Classic (v3) and Tado X execution logic.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..const import GEN_CLASSIC, GEN_X
from .tadov3.executor import TadoV3Executor
from .tadox.executor import TadoXExecutor

if TYPE_CHECKING:
    from ..coordinator import TadoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


class TadoUnifiedExecutor:
    """Dispatches command batches to the generation-specific executor."""

    def __init__(self, coordinator: TadoDataUpdateCoordinator) -> None:
        """Initialize the unified dispatcher."""
        self.coordinator = coordinator
        self._v3_executor = TadoV3Executor(coordinator, coordinator.client)

        # Tado X bridge is only available if initialized in coordinator
        self._x_executor = None
        if hasattr(coordinator, "tadox_bridge") and coordinator.tadox_bridge:
            self._x_executor = TadoXExecutor(coordinator, coordinator.tadox_bridge)

    async def execute_batch(self, merged_data: dict[str, Any]) -> None:
        """Route the merged batch to the correct executor based on hardware generation."""
        generation = getattr(self.coordinator, "generation", GEN_CLASSIC)

        if generation == GEN_X:
            if not self._x_executor:
                if bridge := getattr(self.coordinator, "tadox_bridge", None):
                    self._x_executor = TadoXExecutor(self.coordinator, bridge)
                else:
                    _LOGGER.error("Tado X Executor requested but Bridge not available")
                    return

            _LOGGER.debug("Dispatching batch to Tado X Executor")
            await self._x_executor.execute_batch(merged_data)
        else:
            _LOGGER.debug("Dispatching batch to Tado Classic (v3) Executor")
            await self._v3_executor.execute_batch(merged_data)
