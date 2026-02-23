"""Library module for Tado X support - tadoasync compatible."""

from __future__ import annotations

from .patches import apply_patches, get_handler
from .tadox_api import TadoXApi
from .tadox_models import (
    HopsRoomsAndDevicesResponse,
    TadoXDevice,
    TadoXZoneState,
)

__all__ = [
    "TadoXApi",
    "TadoXZoneState",
    "TadoXDevice",
    "HopsRoomsAndDevicesResponse",
    "apply_patches",
    "get_handler",
]
