"""Entity registry utility functions for Tado Hijack."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from ..const import DOMAIN


def is_entity_disabled(hass: HomeAssistant, platform: str, unique_id: str) -> bool:
    """Check if an entity is disabled in the registry.

    Args:
        hass: Home Assistant instance
        platform: Entity platform (e.g., "number", "sensor")
        unique_id: Entity unique ID

    Returns:
        True if entity exists and is disabled, False otherwise

    """
    reg = er.async_get(hass)
    if eid := reg.async_get_entity_id(platform, DOMAIN, unique_id):
        entry = reg.async_get(eid)
        return bool(entry and entry.disabled)
    return False
