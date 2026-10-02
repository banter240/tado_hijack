"""Handles robust Tado API requests with browser-like behavior."""

from __future__ import annotations

import asyncio
import contextlib
import http
import time
from typing import Any, cast

from aiohttp import ClientResponseError
from tadoasync import Tado, TadoConnectionError
from tadoasync.const import HttpMethod
from tadoasync.exceptions import (
    TadoAuthenticationError,
    TadoBadRequestError,
    TadoError,
    TadoForbiddenError,
)
from tadoasync.tadoasync import (
    API_URL,
    CLIENT_ID,
    EIQ_API_PATH,
    EIQ_HOST_URL,
    TADO_API_PATH,
    TADO_HOST_URL,
    TOKEN_URL,
)
from yarl import URL

from ..const import TADO_USER_AGENT
from .logging_utils import get_redacted_logger, log_secrets, redact
from .parsers import parse_ratelimit_headers

_LOGGER = get_redacted_logger(__name__)


class TadoRequestHandler:
    """Handles Tado API requests with browser-like behavior and rate limit tracking."""

    def __init__(self) -> None:
        """Initialize the handler."""
        # Shared storage for hijacked headers
        self.rate_limit_data: dict[str, Any] = {"limit": 0, "remaining": 0}
        self._auth_lock = asyncio.Lock()

    async def robust_request(
        self,
        instance: Tado,
        uri: str | None = None,
        endpoint: str = API_URL,
        data: dict[str, object] | None = None,
        method: HttpMethod = HttpMethod.GET,
        proxy_url: str | None = None,
        proxy_token: str | None = None,
    ) -> str:
        """Execute a robust request mimicking browser behavior.

        NOTE: This method accesses private tadoasync APIs (_refresh_auth, _access_token,
        _request_timeout, _ensure_session) as they're not exposed publicly but necessary
        for custom request handling. If tadoasync changes these internals, errors will
        be logged and handled gracefully.
        """
        is_auth_request = bool(uri and ("oauth/token" in uri or "oauth2/device" in uri))

        await self._refresh_auth_if_needed(instance, proxy_url, is_auth_request)

        url = self._build_url(uri, endpoint, proxy_url, proxy_token)
        access_token = self._get_access_token(instance, proxy_url, is_auth_request)
        headers = self._build_headers(access_token, method, bool(proxy_url))

        with log_secrets(proxy_token, access_token):
            _LOGGER.debug(
                "Tado Request: %s %s (Proxy: %s)", method.value, str(url), proxy_url
            )

            return await self._execute_request(
                instance, url, headers, method, data, proxy_url
            )

    async def _refresh_auth_if_needed(
        self, instance: Tado, proxy_url: str | None, is_auth_request: bool
    ) -> None:
        """Refresh authentication if needed."""
        if proxy_url or is_auth_request:
            return

        await instance._refresh_auth()

    async def refresh_auth(self, instance: Tado) -> str | None:
        """Return the new refresh token when this call rotated it."""
        if not hasattr(instance, "_token_expiry"):
            _LOGGER.warning("Tado token expiry is missing (library may have changed)")
            return None

        # A second caller with the same refresh token gets a 400 after rotation.
        async with self._auth_lock:
            previous = getattr(instance, "_refresh_token", None)
            await self._refresh_auth(instance)
            current = getattr(instance, "_refresh_token", None)
        return current if isinstance(current, str) and current != previous else None

    def _get_access_token(
        self, instance: Tado, proxy_url: str | None, is_auth_request: bool
    ) -> str | None:
        """Get access token from instance if not using proxy."""
        if proxy_url or is_auth_request:
            return None

        access_token = getattr(instance, "_access_token", None)
        if access_token is None:
            _LOGGER.error(
                "_access_token not found in Tado instance (library may have changed)"
            )
            raise TadoConnectionError("Cannot access Tado authentication token")
        return cast(str, access_token)

    def _get_session(self, instance: Tado) -> Any:
        """Get HTTP session from instance."""
        if hasattr(instance, "_ensure_session"):
            return cast(Any, instance._ensure_session())
        if hasattr(instance, "_session") and instance._session is not None:
            return cast(Any, instance._session)

        _LOGGER.error(
            "Cannot access session from Tado instance (library may have changed)"
        )
        raise TadoConnectionError("Cannot access HTTP session")

    async def _execute_request(
        self,
        instance: Tado,
        url: Any,
        headers: dict[str, str],
        method: HttpMethod,
        data: dict[str, object] | None,
        proxy_url: str | None,
    ) -> str:
        """Execute HTTP request with timeout and error handling."""
        request_timeout = getattr(instance, "_request_timeout", 10)

        try:
            async with asyncio.timeout(request_timeout):
                session = self._get_session(instance)
                request_kwargs = self._build_request_kwargs(url, headers, method, data)

                async with session.request(**cast(Any, request_kwargs)) as response:
                    self._log_response(response, url)

                    if response.status >= http.HTTPStatus.BAD_REQUEST:
                        await self._handle_error_response(response, url)

                    return (
                        ""
                        if response.status == http.HTTPStatus.NO_CONTENT
                        else cast(str, await response.text())
                    )
        except TimeoutError as err:
            raise TadoConnectionError("Timeout connecting to Tado") from err
        except ClientResponseError as err:
            if not proxy_url:
                with contextlib.suppress(KeyError):
                    await instance.check_request_status(err)
            raise

    def _build_request_kwargs(
        self,
        url: Any,
        headers: dict[str, str],
        method: HttpMethod,
        data: dict[str, object] | None,
    ) -> dict[str, Any]:
        """Build request kwargs dict."""
        request_kwargs: dict[str, Any] = {
            "method": method.value,
            "url": str(url),
            "headers": headers,
        }
        if method != HttpMethod.GET and data is not None:
            request_kwargs["json"] = data
        return request_kwargs

    def _log_response(self, response: Any, url: Any) -> None:
        """Log response with rate limit info if available."""
        if rl := parse_ratelimit_headers(dict(response.headers)):
            self.rate_limit_data["limit"] = rl.limit
            self.rate_limit_data["remaining"] = rl.remaining
            self.rate_limit_data["updated_at"] = time.monotonic()
            _LOGGER.debug(
                "Tado Response: %d %s. Quota: %d/%d remaining.",
                response.status,
                url.path,
                rl.remaining,
                rl.limit,
            )

    async def _refresh_auth(self, instance: Tado) -> None:
        """Refresh the access token and keep Tado's error body."""
        expiry = getattr(instance, "_token_expiry", None)
        if expiry is not None and time.time() < float(expiry) - 30:
            return

        refresh_token = getattr(instance, "_refresh_token", None)
        if not refresh_token:
            raise TadoConnectionError("Cannot refresh Tado token")

        timeout = getattr(instance, "_request_timeout", 10)
        session = self._get_session(instance)
        form = {
            "client_id": CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        with log_secrets(refresh_token):
            try:
                async with asyncio.timeout(timeout):
                    async with session.post(TOKEN_URL, data=form) as response:
                        if response.status >= http.HTTPStatus.BAD_REQUEST:
                            await self._raise_http_error(response, "oauth2/token")
                        payload = await response.json(content_type=None)
            except TimeoutError as err:
                raise TadoConnectionError("Timeout connecting to Tado") from err

        instance._access_token = payload["access_token"]
        instance._token_expiry = time.time() + float(payload["expires_in"])
        instance._refresh_token = payload["refresh_token"]

    async def _raise_http_error(self, response: Any, where: str) -> None:
        """Log and raise a Tado error that includes the redacted response body."""
        body = str(redact(await response.text()) or "<empty>")
        place = str(redact(where))
        _LOGGER.error(
            "Tado API Error %d: %s. Response: %s",
            response.status,
            place,
            body,
        )
        message = f"HTTP {response.status} {place}. Response: {body}"
        if response.status == http.HTTPStatus.UNAUTHORIZED:
            raise TadoAuthenticationError(message)
        if response.status == http.HTTPStatus.FORBIDDEN:
            raise TadoForbiddenError(message)
        if response.status == http.HTTPStatus.BAD_REQUEST:
            raise TadoBadRequestError(message)
        raise TadoError(message)

    async def _handle_error_response(self, response: Any, url: Any) -> None:
        """Handle error response by logging and raising."""
        path = getattr(url, "path", None) or str(url)
        await self._raise_http_error(response, path)

    def _build_url(
        self,
        uri: str | None,
        endpoint: str,
        proxy_url: str | None = None,
        proxy_token: str | None = None,
    ) -> URL:
        """Construct URL handling query parameters manually to avoid encoding issues."""
        if proxy_url:
            # Map endpoint to correct path on proxy
            parsed_proxy = URL(proxy_url)

            # If user already included the API path, use it as-is
            if parsed_proxy.path and parsed_proxy.path.startswith("/api"):
                url = parsed_proxy
            else:
                base_path = f"/{proxy_token.strip('/')}" if proxy_token else ""
                if endpoint == EIQ_HOST_URL:
                    url = parsed_proxy.with_path(f"{base_path}{EIQ_API_PATH}")
                else:
                    url = parsed_proxy.with_path(f"{base_path}{TADO_API_PATH}")

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
