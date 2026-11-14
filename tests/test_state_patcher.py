"""Unit tests for helpers/state_patcher.override_timing_attributes (shape-based #196 fix)."""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.tado_hijack.helpers.state_patcher import (
    override_timing_attributes,
)


def classic_state(
    termination: object = None, overlay_active: bool = True
) -> SimpleNamespace:
    overlay = SimpleNamespace(
        termination=termination, projected_expiry="2026-11-12T18:00:00Z"
    )
    return SimpleNamespace(
        overlay_active=overlay_active, overlay=overlay, manual_control_termination=None
    )


def tadox_state(
    termination: object = None, overlay_active: bool = True
) -> SimpleNamespace:
    return SimpleNamespace(
        overlay_active=overlay_active,
        overlay=None,
        manual_control_termination=termination,
    )


class TestGuardPaths:
    def test_none_state_is_empty(self) -> None:
        assert override_timing_attributes(None) == {}

    def test_inactive_overlay_is_empty(self) -> None:
        assert override_timing_attributes(classic_state(overlay_active=False)) == {}
        assert override_timing_attributes(tadox_state(overlay_active=False)) == {}

    def test_missing_termination_is_empty(self) -> None:
        assert override_timing_attributes(classic_state(termination=None)) == {}
        assert override_timing_attributes(tadox_state(termination=None)) == {}

    def test_unknown_termination_kind_is_empty(self) -> None:
        term = SimpleNamespace(type=None, type_skill_based_app=None)
        assert override_timing_attributes(tadox_state(term)) == {}


class TestClassicShapes:
    def test_timer_reports_expiry_from_overlay(self) -> None:
        term = SimpleNamespace(type="TIMER", projected_expiry="2026-11-12T19:00:00Z")
        attrs = override_timing_attributes(classic_state(term))
        assert attrs["override_termination"] == "TIMER"
        assert attrs["override_expires_at"] == "2026-11-12T19:00:00Z"

    def test_manual_has_no_expiry(self) -> None:
        term = SimpleNamespace(type="MANUAL", projected_expiry="2026-11-12T19:00:00Z")
        attrs = override_timing_attributes(classic_state(term))
        assert attrs["override_termination"] == "MANUAL"
        assert "override_expires_at" not in attrs

    def test_next_time_block_mapped_from_type_skill_based_app(self) -> None:
        term = SimpleNamespace(
            type="something_app_specific",
            type_skill_based_app="NEXT_TIME_BLOCK",
            projected_expiry=None,
        )
        state = classic_state(term)
        state.overlay.projected_expiry = None
        attrs = override_timing_attributes(state)
        assert attrs["override_termination"] == "NEXT_TIME_BLOCK"
        assert "override_expires_at" not in attrs

    def test_overlay_projected_expiry_used_as_fallback(self) -> None:
        term = SimpleNamespace(type="TADO_MODE", projected_expiry=None)
        attrs = override_timing_attributes(classic_state(term))
        assert attrs["override_expires_at"] == "2026-11-12T18:00:00Z"


class TestTadoXShapes:
    def test_termination_on_manual_control_field(self) -> None:
        term = SimpleNamespace(
            type="TIMER",
            type_skill_based_app=None,
            projected_expiry="2026-11-12T20:00:00Z",
            remaining_time_in_seconds=None,
        )
        attrs = override_timing_attributes(tadox_state(term))
        assert attrs["override_termination"] == "TIMER"
        assert attrs["override_expires_at"] == "2026-11-12T20:00:00Z"

    def test_remaining_time_in_seconds_positive_only(self) -> None:
        term = SimpleNamespace(
            type="TIMER",
            type_skill_based_app=None,
            projected_expiry=None,
            remaining_time_in_seconds=600,
        )
        attrs = override_timing_attributes(tadox_state(term))
        assert attrs["remaining_time_in_seconds"] == 600

    def test_remaining_zero_or_negative_omitted(self) -> None:
        for bad in (0, -5, "600", None):
            term = SimpleNamespace(
                type="TIMER",
                type_skill_based_app=None,
                projected_expiry=None,
                remaining_time_in_seconds=bad,
            )
            attrs = override_timing_attributes(tadox_state(term))
            assert "remaining_time_in_seconds" not in attrs

    def test_next_time_block_via_skill_based_flag(self) -> None:
        term = SimpleNamespace(
            type="TIMER",
            type_skill_based_app="NEXT_TIME_BLOCK",
            projected_expiry=None,
            remaining_time_in_seconds=120,
        )
        attrs = override_timing_attributes(tadox_state(term))
        assert attrs["override_termination"] == "NEXT_TIME_BLOCK"
        assert "override_expires_at" not in attrs
        assert attrs["remaining_time_in_seconds"] == 120
