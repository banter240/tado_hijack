"""TadoX API client (hops.tado.com) - tadoasync compatible.

This module wraps the Tado X (Hops) API using tadoasync's session and authentication.
It accesses some private attributes from tadoasync that ideally should be public:
  - _ensure_session(): Get aiohttp session for requests
  - _refresh_auth(): Refresh OAuth token before requests
  - _access_token: Bearer token for Authorization header
  - _home_id: Home identifier for API endpoints
  - _headers: User-Agent and other headers

These private attribute usages are documented for potential upstream contribution.
See dev/workspace/context/tadoasync_coupling.md for details.
"""

from __future__ import annotations

import http
from typing import TYPE_CHECKING, Any, cast

from aiohttp import ClientTimeout

from ..helpers.logging_utils import get_redacted_logger
from ..helpers.tadox.const import HOPS_BASE_URL
from .tadox_models import HopsRoomsAndDevicesResponse, TadoXZoneState

if TYPE_CHECKING:
    from tadoasync import Tado

_LOGGER = get_redacted_logger(__name__)


class TadoXApi:
    """Helper class to communicate with Hops API using tadoasync session."""

    def __init__(self, tado_client: Tado) -> None:
        """Initialize with an existing (and authenticated) tadoasync instance.

        Args:
            tado_client: Authenticated tadoasync.Tado instance

        Note:
            Accesses private attributes from tadoasync for compatibility:
            - _ensure_session(): aiohttp session
            - _home_id: home identifier
            These should ideally be public in tadoasync.

        """
        self._tado = tado_client
        # Private attribute access - could be public in future tadoasync
        self._session = tado_client._ensure_session()
        self._home_id = tado_client._home_id
        _LOGGER.debug(
            "TadoXApi initialized: home_id=%s, session=%s",
            self._home_id,
            type(self._session).__name__,
        )

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Perform an authenticated request to Hops API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path (without base URL or home_id)
            json_data: Optional JSON payload
            params: Optional query parameters

        Returns:
            Parsed JSON response or success dict

        Note:
            Uses tadoasync private methods:
            - _refresh_auth(): Refresh OAuth token
            - _access_token: Get current bearer token
            - _headers: Get User-Agent

        """
        # Private method access - should be public for multi-API support
        await self._tado._refresh_auth()

        url = f"{HOPS_BASE_URL}/homes/{self._home_id}/{endpoint}"
        _LOGGER.debug(
            "TadoX API Request: %s %s (home_id=%s)", method, url, self._home_id
        )
        # Private attribute access - should be public
        headers = {
            "Authorization": f"Bearer {self._tado._access_token}",
            "Content-Type": "application/json",
            "User-Agent": self._tado._headers.get("user-agent", "TadoHijack/1.0"),
        }

        # Tado X / Hops often requires bypassing the Service Worker cache
        hops_params = {"ngsw-bypass": "true"}
        if params:
            hops_params |= params

        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                json=json_data,
                params=hops_params,
                timeout=ClientTimeout(total=10),
            ) as response:
                if response.status == http.HTTPStatus.NO_CONTENT:
                    return {"success": True}
                if response.status == http.HTTPStatus.NOT_FOUND:
                    _LOGGER.info(
                        "Hops API returned 404 for %s (no Tado X hardware associated with this account)",
                        endpoint,
                    )
                    # Return minimal valid structure for Pydantic models
                    if "roomsAndDevices" in endpoint:
                        return {"rooms": [], "devices": []}
                    return [] if "rooms" in endpoint else {}
                response.raise_for_status()

                # Parse JSON without Content-Type validation (Hops API omits it).
                # quickActions POST endpoints return 200 with empty body → raises → success.
                try:
                    return await response.json(content_type=None)
                except Exception:
                    return {"success": True}
        except Exception as err:
            _LOGGER.error("Hops API Error on %s: %s", endpoint, err)
            raise

    async def async_get_rooms_and_devices(self) -> HopsRoomsAndDevicesResponse:
        """Fetch all rooms and devices snapshot."""
        data = await self._request("GET", "roomsAndDevices")
        return cast(
            HopsRoomsAndDevicesResponse,
            HopsRoomsAndDevicesResponse.model_validate(data),
        )

    async def async_get_room_states(self) -> list[TadoXZoneState]:
        """Fetch all room states."""
        data = await self._request("GET", "rooms")
        return [TadoXZoneState.model_validate(room) for room in data]

    async def async_set_manual_control(
        self,
        room_id: int,
        temperature: float | None,
        power: str = "ON",
        termination_type: str = "MANUAL",
        duration_seconds: int | None = None,
    ) -> Any:
        """Set manual temperature control."""
        payload: dict[str, Any] = {
            "setting": {
                "power": power,
                "isBoost": False,
            },
            "termination": {"type": termination_type},
        }
        # Only add temperature if provided (OFF mode doesn't need temperature)
        if temperature is not None:
            payload["setting"]["temperature"] = {"value": temperature}
        if termination_type == "TIMER" and duration_seconds:
            payload["termination"]["durationInSeconds"] = duration_seconds
        return await self._request(
            "POST", f"rooms/{room_id}/manualControl", json_data=payload
        )

    async def async_resume_schedule(self, room_id: int) -> Any:
        """Delete manual control and resume schedule."""
        return await self._request("DELETE", f"rooms/{room_id}/manualControl")

    async def async_set_presence(self, presence: str) -> None:
        """Set home presence via v2 API (shared endpoint)."""
        await self._request_external(
            f"https://my.tado.com/api/v2/homes/{self._home_id}/presenceLock",
            "PUT" if presence.upper() != "AUTO" else "DELETE",
            json_data={"homePresence": presence}
            if presence.upper() != "AUTO"
            else None,
        )

    async def async_set_temperature_offset(self, device_id: str, offset: float) -> Any:
        """Set temperature offset for a device."""
        payload = {"temperatureOffset": offset}
        return await self._request(
            "PATCH", f"roomsAndDevices/devices/{device_id}", json_data=payload
        )

    async def async_boost_all(self) -> Any:
        """Activate boost mode for all rooms."""
        return await self._request("POST", "quickActions/boost")

    async def async_resume_all_schedules(self) -> Any:
        """Resume schedule for all rooms."""
        return await self._request("POST", "quickActions/resumeSchedule")

    async def async_turn_off_all_zones(self) -> Any:
        """Turn off all rooms (frost protection mode)."""
        return await self._request("POST", "quickActions/allOff")

    async def async_set_open_window_detection(self, room_id: int, enabled: bool) -> Any:
        """Enable or disable open window detection."""
        if enabled:
            return await self._request("POST", f"rooms/{room_id}/openWindow")
        return await self._request("DELETE", f"rooms/{room_id}/openWindow")

    async def _request_external(
        self, url: str, method: str, json_data: dict[str, Any] | None = None
    ) -> Any:
        """Handle requests to subdomains outside hops.tado.com.

        Note:
            Uses tadoasync private methods/attributes:
            - _refresh_auth(): Refresh OAuth token
            - _access_token: Get current bearer token

        """
        await self._tado._refresh_auth()
        headers = {
            "Authorization": f"Bearer {self._tado._access_token}",
            "Content-Type": "application/json",
        }
        async with self._session.request(
            method, url, headers=headers, json=json_data
        ) as response:
            response.raise_for_status()
            # 204 No Content or 200 with empty body
            if (
                response.status == http.HTTPStatus.NO_CONTENT
                or response.content_length == 0
            ):
                return None
            return await response.json(content_type=None)
