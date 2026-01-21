"""Handles robust Tado API requests with browser-like behavior."""

from __future__ import annotations

import asyncio
from typing import Any, cast

from aiohttp import ClientResponseError
from tadoasync import Tado, TadoConnectionError
from tadoasync.const import HttpMethod
from tadoasync.tadoasync import (
    API_URL,
    EIQ_API_PATH,
    EIQ_HOST_URL,
    TADO_API_PATH,
    TADO_HOST_URL,
)
from yarl import URL

from ..const import TADO_USER_AGENT
from .logging_utils import get_redacted_logger
from .parsers import parse_ratelimit_headers

_LOGGER = get_redacted_logger(__name__)


class TadoRequestHandler:
    """Handles Tado API requests with browser-like behavior and rate limit tracking."""

    def __init__(self) -> None:
        """Initialize the handler."""
        # Shared storage for hijacked headers
        self.rate_limit_data: dict[str, int] = {"limit": 0, "remaining": 0}

    async def robust_request(
        self,
        instance: Tado,
        uri: str | None = None,
        endpoint: str = API_URL,
        data: dict[str, object] | None = None,
        method: HttpMethod = HttpMethod.GET,
        proxy_url: str | None = None,
    ) -> str:
        """Execute a robust request mimicking browser behavior."""
        # Only refresh auth if NOT using a proxy (proxy handles auth)
        if not proxy_url:
            await instance._refresh_auth()  # noqa: SLF001

        url = self._build_url(uri, endpoint, proxy_url)
        headers = self._build_headers(instance._access_token, method)  # noqa: SLF001

        _LOGGER.debug("Tado Request: %s %s (Proxy: %s)", method.value, url, proxy_url)

        try:
            async with asyncio.timeout(instance._request_timeout):  # noqa: SLF001
                session = instance._ensure_session()  # noqa: SLF001

                request_kwargs: dict[str, Any] = {
                    "method": method.value,
                    "url": str(url),
                    "headers": headers,
                }
                if method != HttpMethod.GET and data is not None:
                    request_kwargs["json"] = data

                async with session.request(**cast(Any, request_kwargs)) as response:
                    if rl := parse_ratelimit_headers(dict(response.headers)):
                        self.rate_limit_data["limit"] = rl.limit
                        self.rate_limit_data["remaining"] = rl.remaining

                    response.raise_for_status()
                    return cast(str, await response.text())

        except TimeoutError as err:
            raise TadoConnectionError("Timeout connecting to Tado") from err
        except ClientResponseError as err:
            # Only check request status if NOT using proxy, or if proxy passes through Tado errors 1:1
            # But we can't refresh auth via proxy, so we just raise.
            if not proxy_url:
                await instance.check_request_status(err)
            raise

    def _build_url(
        self, uri: str | None, endpoint: str, proxy_url: str | None = None
    ) -> URL:
        """Construct URL handling query parameters manually to avoid encoding issues."""
        if proxy_url:
            # Proxy handles base URL. We assume proxy_url points to root (e.g. http://localhost:8080)
            # Tado API paths start with /api/v2
            # EIQ paths start with /api
            # We need to map endpoint to correct path on proxy if proxy mirrors structure.
            # Proxy doc says: "Replace https://my.tado.com with http://localhost:8080 in your API calls."
            # and "http://localhost:8080/api/v2/me".
            # So we just swap the host part.

            # Parse proxy URL to get scheme/host/port
            parsed_proxy = URL(proxy_url)

            if endpoint == EIQ_HOST_URL:
                # Proxy might not support EIQ? Docs only mention /api/v2.
                # Assuming it proxies everything or we fallback/fail for EIQ.
                # Let's try to map it to /api if EIQ.
                url = parsed_proxy.with_path(EIQ_API_PATH)
            else:
                url = parsed_proxy.with_path(TADO_API_PATH)

        elif endpoint == EIQ_HOST_URL:
            url = URL.build(scheme="https", host=EIQ_HOST_URL, path=EIQ_API_PATH)
        else:
            url = URL.build(scheme="https", host=TADO_HOST_URL, path=TADO_API_PATH)

        if uri:
            # yarl.joinpath encodes '?' which breaks Tado's query parsing.
            # We construct the path manually to preserve query strings.
            base_str = str(url).rstrip("/")
            uri_str = uri.lstrip("/")
            return URL(f"{base_str}/{uri_str}")

        return url

    def _build_headers(
        self, access_token: str | None, method: HttpMethod
    ) -> dict[str, str]:
        """Build headers matching browser behavior."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": TADO_USER_AGENT,
        }

        # Browser omits Content-Type for DELETE, but sends it for PUT/POST
        if method == HttpMethod.PUT:
            headers["Content-Type"] = "application/json;charset=UTF-8"
            headers["Mime-Type"] = "application/json;charset=UTF-8"

        return headers
