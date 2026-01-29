"""Manages property updates for Tado Hijack."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..models import CommandType, TadoCommand

if TYPE_CHECKING:
    from ..coordinator import TadoDataUpdateCoordinator


class PropertyManager:
    """Handles generic zone and device property updates with optimistic state."""

    def __init__(self, coordinator: TadoDataUpdateCoordinator) -> None:
        """Initialize the property manager."""
        self.coordinator = coordinator

    async def async_set_zone_property(
        self,
        zone_id: int,
        cmd_type: CommandType,
        data: dict[str, Any],
        optimistic_func: Any,
        optimistic_value: Any,
        rollback_context: Any = None,
    ) -> None:
        """Set a zone property with optimistic state and queuing."""
        optimistic_func(zone_id, optimistic_value)
        self.coordinator.async_update_listeners()

        self.coordinator.api_manager.queue_command(
            f"{cmd_type.value}_{zone_id}",
            TadoCommand(
                cmd_type,
                zone_id=zone_id,
                data=data,
                rollback_context=rollback_context,
            ),
        )

    async def async_set_device_property(
        self,
        serial_no: str,
        cmd_type: CommandType,
        data: dict[str, Any],
        optimistic_func: Any,
        optimistic_value: Any,
        rollback_context: Any = None,
    ) -> None:
        """Set a device property with optimistic state and queuing."""
        optimistic_func(serial_no, optimistic_value)
        self.coordinator.async_update_listeners()

        self.coordinator.api_manager.queue_command(
            f"{cmd_type.value}_{serial_no}",
            TadoCommand(
                cmd_type,
                data=data,
                rollback_context=rollback_context,
            ),
        )
