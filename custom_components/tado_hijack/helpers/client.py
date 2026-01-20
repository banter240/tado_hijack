"""Custom Tado client implementation for Tado Hijack."""

from __future__ import annotations

from typing import Any

from tadoasync import Tado
from tadoasync.const import HttpMethod
from tadoasync.tadoasync import API_URL

from .logging_utils import get_redacted_logger
from .patch import get_handler

_LOGGER = get_redacted_logger(__name__)


class TadoHijackClient(Tado):
    """Custom Tado client that uses TadoRequestHandler and adds bulk methods."""

    async def _request(
        self,
        uri: str | None = None,
        endpoint: str = API_URL,
        data: dict[str, object] | None = None,
        method: HttpMethod = HttpMethod.GET,
    ) -> str:
        """Override _request to use our robust TadoRequestHandler."""
        return await get_handler().robust_request(self, uri, endpoint, data, method)

    async def reset_all_zones_overlay(self, zones: list[int]) -> None:
        """Reset overlay for multiple zones (Bulk API)."""
        if not zones:
            return
        rooms_param = ",".join(str(z) for z in zones)
        await self._request(
            f"homes/{self._home_id}/overlay?rooms={rooms_param}",
            method=HttpMethod.DELETE,
        )

    async def set_all_zones_overlay(self, overlays: list[dict[str, Any]]) -> None:
        """Set overlay for multiple zones (Bulk API)."""
        if not overlays:
            return
        await self._request(
            f"homes/{self._home_id}/overlay",
            data={"overlays": overlays},
            method=HttpMethod.POST,
        )

    async def set_temperature_offset(self, serial_no: str, offset: float) -> None:
        """Set the temperature offset for a device."""
        await self._request(
            f"devices/{serial_no}/temperatureOffset",
            data={"celsius": offset},
            method=HttpMethod.PUT,
        )
