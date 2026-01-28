"""Utility functions for Tado Hijack."""

from __future__ import annotations

import random


def apply_jitter(value: float, percent: float) -> float:
    """Apply a random jitter to a value.

    Args:
        value: The base value.
        percent: Max variation percentage (e.g. 10.0 for +/- 10%).

    Returns:
        The value with jitter applied.

    """
    if percent <= 0:
        return value

    factor = percent / 100.0
    variation = value * factor
    return value + random.uniform(-variation, variation)
