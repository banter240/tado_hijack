"""Handles robust Tado API requests with browser-like behavior."""

from __future__ import annotations

import asyncio
import contextlib
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
        """Execute a robust request mimicking browser behavior.

        NOTE: This method accesses private tadoasync APIs (_refresh_auth, _access_token,
        _request_timeout, _ensure_session) as they're not exposed publicly but necessary
        for custom request handling. If tadoasync changes these internals, errors will
        be logged and handled gracefully.
        """
        # Only refresh auth if NOT using a proxy (proxy handles auth)
        # AND only if we are not in the middle of a device authorization flow
        is_auth_request = uri and ("oauth/token" in uri or "oauth2/device" in uri)

        if not proxy_url and not is_auth_request:
            if hasattr(instance, "_refresh_auth"):
                await instance._refresh_auth()
            else:
                _LOGGER.warning(
                    "_refresh_auth not found in Tado instance (library may have changed)"
                )

        url = self._build_url(uri, endpoint, proxy_url)

        # Get access token only if NOT using proxy (proxy handles auth internally)
        access_token: str | None = None
        if not proxy_url and not is_auth_request:
            access_token = getattr(instance, "_access_token", None)
            if access_token is None:
                _LOGGER.error(
                    "_access_token not found in Tado instance (library may have changed)"
                )
                raise TadoConnectionError("Cannot access Tado authentication token")

        headers = self._build_headers(access_token, method, bool(proxy_url))

        _LOGGER.debug("Tado Request: %s %s (Proxy: %s)", method.value, url, proxy_url)

        # Get timeout (private API with fallback)
        request_timeout = getattr(instance, "_request_timeout", 10)

        try:
            async with asyncio.timeout(request_timeout):
                # Get session (private API with fallback)
                if hasattr(instance, "_ensure_session"):
                    session = instance._ensure_session()
                elif hasattr(instance, "_session") and instance._session is not None:
                    session = instance._session
                else:
                    _LOGGER.error(
                        "Cannot access session from Tado instance (library may have changed)"
                    )
                    raise TadoConnectionError("Cannot access HTTP session")

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
                        _LOGGER.debug(
                            "Tado Response: %d %s. Quota: %d/%d remaining.",
                            response.status,
                            url.path,
                            rl.remaining,
                            rl.limit,
                        )

                    if response.status >= 400:
                        body = await response.text()
                        _LOGGER.error(
                            "Tado API Error %d: %s. Response: %s",
                            response.status,
                            url.path,
                            body,
                        )
                        response.raise_for_status()

                    return cast(str, await response.text())

        except TimeoutError as err:
            raise TadoConnectionError("Timeout connecting to Tado") from err
        except ClientResponseError as err:
            # Only check request status if NOT using proxy, or if proxy passes through Tado errors 1:1
            if not proxy_url:
                with contextlib.suppress(KeyError):
                    await instance.check_request_status(err)
            raise

    def _build_url(
        self, uri: str | None, endpoint: str, proxy_url: str | None = None
    ) -> URL:
        """Construct URL handling query parameters manually to avoid encoding issues."""
        if proxy_url:
            # Map endpoint to correct path on proxy
            parsed_proxy = URL(proxy_url)

            # If user already included the API path, use it as-is
            if parsed_proxy.path and parsed_proxy.path.startswith("/api"):
                url = parsed_proxy
            elif endpoint == EIQ_HOST_URL:
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
        self, access_token: str | None, method: HttpMethod, is_proxy: bool = False
    ) -> dict[str, str]:
        """Build headers matching browser behavior."""
        headers = {
            "User-Agent": TADO_USER_AGENT,
        }

        # Only add Authorization header when NOT using proxy (proxy handles auth)
        if not is_proxy and access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        # Browser omits Content-Type for DELETE, but sends it for PUT/POST
        if method == HttpMethod.PUT:
            headers["Content-Type"] = "application/json;charset=UTF-8"
            headers["Mime-Type"] = "application/json;charset=UTF-8"

        return headers
