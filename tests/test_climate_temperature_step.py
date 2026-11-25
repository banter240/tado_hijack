"""Regression tests for climate target temperature precision (#217)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.tado_hijack.climate_entity import TadoClimateEntity


def _entity(step: float | None) -> tuple[TadoClimateEntity, AsyncMock]:
    """A bare heating climate and the overlay mock its coordinator holds."""
    entity = object.__new__(TadoClimateEntity)
    entity._zone_id = 1
    entity._attr_target_temperature_step = step
    entity._state_memory = {}
    overlay_mock = AsyncMock()
    entity.coordinator = SimpleNamespace(  # type: ignore[assignment]
        async_set_multiple_zone_overlays=overlay_mock
    )
    return entity, overlay_mock


@pytest.mark.parametrize(
    ("temperature", "step", "expected"),
    [
        (17.5, 0.5, 17.5),
        (19.5, 0.5, 19.5),
        (19.0, 0.5, 19.0),
        (19.4, 0.5, 19.5),
        (19.4, 1.0, 19.0),
        (19.6, 1.0, 20.0),
        (19.6, None, 20.0),
    ],
)
def test_set_temperature_respects_advertised_step(
    temperature: float, step: float | None, expected: float
) -> None:
    """19.5 °C on a 0.5-step entity must not collapse to 19 or 20."""
    entity, overlay_mock = _entity(step)

    async def _run() -> None:
        await entity.async_set_temperature(temperature=temperature)

    asyncio.run(_run())

    overlay_mock.assert_awaited_once_with(
        zone_ids=[1],
        power="ON",
        temperature=expected,
        overlay_mode="room",
        ac_mode=None,
    )


def test_missing_temperature_is_ignored() -> None:
    """Do not send an overlay without a temperature."""
    entity, overlay_mock = _entity(0.5)

    async def _run() -> None:
        await entity.async_set_temperature()

    asyncio.run(_run())

    overlay_mock.assert_not_awaited()
