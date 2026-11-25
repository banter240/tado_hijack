"""Regression tests for issue #215: flow temp write fold-through.

After a successful PATCH the written value must survive the optimistic
grace: the regular poll never re-reads the flow endpoint, so without
folding the write into the mapper cache the entities revert to the
pre-write GET value once the grace expires.
"""

from __future__ import annotations

from custom_components.tado_hijack.helpers.tadox.mapper import TadoXMapper
from custom_components.tado_hijack.lib.tadox_models import TadoXFlowTempSettings


def _mapper(cached: TadoXFlowTempSettings | None) -> TadoXMapper:
    """A mapper with a pre-seeded cache; no network plumbing needed."""
    mapper = object.__new__(TadoXMapper)
    mapper._flow_temp_cached = cached
    return mapper


def _settings(max_temp: float = 45.0, adapt: bool = False) -> TadoXFlowTempSettings:
    return TadoXFlowTempSettings.model_validate(
        {
            "maxFlowTemperature": max_temp,
            "maxFlowTemperatureConstraints": {"min": 25, "max": 80},
            "autoAdaptation": {"enabled": adapt, "maxFlowTemperature": None},
        }
    )


def test_fold_updates_max_flow_temperature() -> None:
    mapper = _mapper(_settings(45.0))
    mapper.note_written_flow_temp({"maxFlowTemperature": 43})

    folded = mapper.get_flow_temp_cached()
    assert folded is not None
    assert folded.max_flow_temperature == 43.0
    assert folded.auto_adaptation.enabled is False


def test_fold_updates_auto_adaptation_only() -> None:
    mapper = _mapper(_settings(45.0, adapt=False))
    mapper.note_written_flow_temp({"autoAdaptation": {"enabled": True}})

    folded = mapper.get_flow_temp_cached()
    assert folded is not None
    assert folded.max_flow_temperature == 45.0
    assert folded.auto_adaptation.enabled is True


def test_fold_preserves_adapted_value_when_enabled() -> None:
    """Folding `enabled=true` must not wipe the adapted max value."""
    settings = _settings(45.0)
    settings.auto_adaptation.max_flow_temperature = 38.0
    mapper = _mapper(settings)
    mapper.note_written_flow_temp({"autoAdaptation": {"enabled": True}})

    folded = mapper.get_flow_temp_cached()
    assert folded is not None
    assert folded.auto_adaptation.max_flow_temperature == 38.0


def test_fold_without_cache_is_noop() -> None:
    """No prior GET (fresh reload): nothing to fold, next GET provides truth."""
    mapper = _mapper(None)
    mapper.note_written_flow_temp({"maxFlowTemperature": 43})
    assert mapper.get_flow_temp_cached() is None


def test_fold_with_unrelated_payload_is_noop() -> None:
    mapper = _mapper(_settings(45.0))
    mapper.note_written_flow_temp({})
    folded = mapper.get_flow_temp_cached()
    assert folded is not None
    assert folded.max_flow_temperature == 45.0


def test_fold_does_not_mutate_shared_instance() -> None:
    """model_copy(update=...) keeps the old cached object untouched."""
    original = _settings(45.0)
    mapper = _mapper(original)
    mapper.note_written_flow_temp({"maxFlowTemperature": 43})

    assert original.max_flow_temperature == 45.0
    assert mapper.get_flow_temp_cached() is not original
