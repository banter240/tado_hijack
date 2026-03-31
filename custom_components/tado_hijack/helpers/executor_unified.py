"""Unified executor for dispatching commands to generation-specific executors."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .tadov3.executor import TadoV3Executor
from .tadox.executor import TadoXExecutor

if TYPE_CHECKING:
    from ..coordinator import TadoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


class TadoUnifiedExecutor:
    """Dispatches command batches to generation-specific executor."""

    def __init__(self, coordinator: TadoDataUpdateCoordinator) -> None:
        """Initialize unified executor."""
        self.coordinator = coordinator
        self._classic_executor = TadoV3Executor(coordinator, coordinator.client)
        self._x_executor: TadoXExecutor | None = None
        if bridge := getattr(coordinator, "tadox_bridge", None):
            self._x_executor = TadoXExecutor(coordinator, bridge)

    async def execute_batch(self, merged_data: dict[str, Any]) -> None:
        """Execute command batch using appropriate executor."""
        if self.coordinator.generation == "x":
            if self._x_executor:
                await self._x_executor.execute_batch(merged_data)
            else:
                _LOGGER.error("Tado X executor not available")
            return

        await self._classic_executor.execute_batch(merged_data)
