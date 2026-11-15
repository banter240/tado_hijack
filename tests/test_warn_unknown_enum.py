"""Tests for the warn_unknown_enum latch (API-drift visibility helper)."""

from __future__ import annotations

import logging

import pytest

from custom_components.tado_hijack.const import KNOWN_PRESENCE_STATES
from custom_components.tado_hijack.helpers.logging_utils import (
    _warned_unknown_values,
    warn_unknown_enum,
)


def _latch_size() -> int:
    return len(_warned_unknown_values)


def test_unknown_value_warns_once(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="custom_components.tado_hijack"):
        before = _latch_size()
        warn_unknown_enum(
            logging.getLogger("custom_components.tado_hijack"),
            "presence",
            "HOLIDAY",
            KNOWN_PRESENCE_STATES,
        )
        warn_unknown_enum(
            logging.getLogger("custom_components.tado_hijack"),
            "presence",
            "HOLIDAY",
            KNOWN_PRESENCE_STATES,
        )
    assert _latch_size() == before + 1
    assert len(caplog.records) == 1
    assert "HOLIDAY" in caplog.records[0].getMessage()


def test_known_value_does_not_warn() -> None:
    before = _latch_size()
    warn_unknown_enum(
        logging.getLogger("custom_components.tado_hijack"),
        "presence",
        "AWAY",
        KNOWN_PRESENCE_STATES,
    )
    assert _latch_size() == before


def test_empty_value_does_not_warn() -> None:
    before = _latch_size()
    warn_unknown_enum(
        logging.getLogger("custom_components.tado_hijack"),
        "presence",
        None,
        KNOWN_PRESENCE_STATES,
    )
    warn_unknown_enum(
        logging.getLogger("custom_components.tado_hijack"),
        "presence",
        "",
        KNOWN_PRESENCE_STATES,
    )
    assert _latch_size() == before


def test_matching_is_case_insensitive() -> None:
    before = _latch_size()
    warn_unknown_enum(
        logging.getLogger("custom_components.tado_hijack"),
        "presence",
        " home ",
        KNOWN_PRESENCE_STATES,
    )
    assert _latch_size() == before


def test_distinct_values_latch_separately() -> None:
    before = _latch_size()
    warn_unknown_enum(
        logging.getLogger("custom_components.tado_hijack"),
        "presence",
        "OOF",
        KNOWN_PRESENCE_STATES,
    )
    warn_unknown_enum(
        logging.getLogger("custom_components.tado_hijack"),
        "connection state",
        "OOF",
        KNOWN_PRESENCE_STATES,
    )
    assert _latch_size() == before + 2
