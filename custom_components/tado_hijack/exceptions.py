"""Custom exceptions for Tado Hijack."""

from homeassistant.exceptions import HomeAssistantError


class TadoBridgeError(HomeAssistantError):
    """Base error for Tado Bridge."""


class TadoAuthenticationError(TadoBridgeError):
    """Error indicating auth failure."""


class TadoRateLimitError(TadoBridgeError):
    """Error indicating API rate limit hit."""

    def __init__(self, *args: object, retry_after: int = 0) -> None:
        """Store retry_after seconds for coordinator backoff."""
        super().__init__(*args)
        self.retry_after = retry_after


class TadoCommunicationError(TadoBridgeError):
    """Error communicating with Tado API."""


class TadoOfflineError(TadoBridgeError):
    """Tado cannot be called. The last change is kept until it answers."""

    def __init__(self) -> None:
        """One message for the UI and for callers."""
        super().__init__("Tado is offline. The last change is kept until it answers.")
