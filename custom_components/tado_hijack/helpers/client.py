"""Custom Tado client implementation for Tado Hijack."""

from __future__ import annotations

from typing import Any, cast

import orjson
from tadoasync import Tado
from tadoasync.const import HttpMethod
from tadoasync.tadoasync import API_URL

from .logging_utils import get_redacted_logger
from .patch import get_handler

_LOGGER = get_redacted_logger(__name__)


class TadoHijackClient(Tado):
    """Custom Tado client that uses TadoRequestHandler and adds bulk methods."""

    def __init__(
        self,
        *args: Any,
        proxy_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the client with optional proxy URL."""
        super().__init__(*args, **kwargs)
        self.proxy_url = proxy_url

    async def _request(
        self,
        uri: str | None = None,
        endpoint: str = API_URL,
        data: dict[str, object] | None = None,
        method: HttpMethod = HttpMethod.GET,
    ) -> str:
        """Override _request to use our robust TadoRequestHandler."""
        return await get_handler().robust_request(
            self, uri, endpoint, data, method, self.proxy_url
        )

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

    async def set_hot_water_zone_overlay(
        self, zone_id: int, data: dict[str, Any]
    ) -> None:
        """Set overlay for a hot water zone."""
        await self._request(
            f"homes/{self._home_id}/zones/{zone_id}/overlay",
            data=data,
            method=HttpMethod.PUT,
        )

    async def reset_hot_water_zone_overlay(self, zone_id: int) -> None:
        """Reset overlay for a hot water zone."""
        await self._request(
            f"homes/{self._home_id}/zones/{zone_id}/overlay",
            method=HttpMethod.DELETE,
        )

    async def set_temperature_offset(self, serial_no: str, offset: float) -> None:
        """Set the temperature offset for a device."""
        await self._request(
            f"devices/{serial_no}/temperatureOffset",
            data={"celsius": offset},
            method=HttpMethod.PUT,
        )

    async def get_away_configuration(self, zone_id: int) -> dict[str, Any]:
        """Get the away configuration for a zone."""
        response = await self._request(
            f"homes/{self._home_id}/zones/{zone_id}/awayConfiguration"
        )
        return cast(dict[str, Any], orjson.loads(response))

    async def set_away_configuration(
        self,
        zone_id: int,
        temp: float,
        preheating_level: str = "OFF",
        mode: str = "HEATING",
    ) -> None:
        """Set the away configuration for a zone."""
        await self._request(
            f"homes/{self._home_id}/zones/{zone_id}/awayConfiguration",
            data={
                "type": mode,
                "preheatingLevel": preheating_level,
                "minimumAwayTemperature": {"celsius": temp},
            },
            method=HttpMethod.PUT,
        )

    async def set_dazzle_mode(self, zone_id: int, enabled: bool) -> None:
        """Set dazzle mode for a zone."""
        await self._request(
            f"homes/{self._home_id}/zones/{zone_id}/dazzleMode",
            data={"enabled": enabled},
            method=HttpMethod.PUT,
        )

    async def set_early_start(self, zone_id: int, enabled: bool) -> None:
        """Set early start configuration for a zone."""
        await self._request(
            f"homes/{self._home_id}/zones/{zone_id}/earlyStart",
            data={"enabled": enabled},
            method=HttpMethod.PUT,
        )

    async def set_open_window_detection(self, zone_id: int, enabled: bool) -> None:
        """Set open window detection configuration for a zone."""
        await self._request(
            f"homes/{self._home_id}/zones/{zone_id}/openWindowDetection",
            data={"enabled": enabled},
            method=HttpMethod.PUT,
        )

    async def get_capabilities(self, zone_id: int) -> Any:
        """Get capabilities for a zone."""
        return await super().get_capabilities(zone_id)

    async def identify_device(self, serial_no: str) -> None:
        """Identify a device (make it flash)."""
        await self._request(
            f"devices/{serial_no}/identify",
            method=HttpMethod.POST,
        )
