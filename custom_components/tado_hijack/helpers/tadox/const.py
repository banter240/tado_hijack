"""Constants for Tado X helpers."""

from typing import Final

# OAuth2 Endpoints
TADO_OAUTH_BASE: Final = "https://login.tado.com/oauth2"
TADO_DEVICE_AUTH_URL: Final = f"{TADO_OAUTH_BASE}/device_authorize"
TADO_TOKEN_URL: Final = f"{TADO_OAUTH_BASE}/token"

# Public Client ID for Tado X (Device Flow)
TADO_X_CLIENT_ID: Final = "1bb50063-6b0c-4d11-bd99-387f4a91cc46"

# Hops API
HOPS_BASE_URL: Final = "https://hops.tado.com"

# Grant Types
GRANT_TYPE_DEVICE: Final = "urn:ietf:params:oauth:grant-type:device_code"
GRANT_TYPE_REFRESH: Final = "refresh_token"

# Auth Status Errors
AUTH_ERROR_PENDING: Final = "authorization_pending"
AUTH_ERROR_EXPIRED: Final = "expired_token"
AUTH_ERROR_SLOW_DOWN: Final = "slow_down"
