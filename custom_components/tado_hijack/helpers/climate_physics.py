"""Shared atmospheric physics for indoor climate calculations.

All functions are pure (no HA state access) — they operate only on
temperature (°C) and relative humidity (%) values.

Used by both the Tado Classic (v3) and Tado X parsers to avoid duplication.

References:
  - Magnus formula: Bolton (1980), valid -30...+35 degC, error < 0.1 % over water
  - Building physics thresholds: fRSI approx 0.70-0.85, mid-EU housing stock

"""

from __future__ import annotations

import math

_MAGNUS_A: float = 17.67
_MAGNUS_B: float = 243.5  # °C

# Absolute humidity factor: M_water / R * 100 = 18.015 / 8.314 * 100
# Converts saturation vapour pressure (hPa) to absolute humidity (g/m³)
_AH_FACTOR: float = 216.7  # g·K/J

# Minimum indoor-outdoor absolute humidity delta (g/m³) for ventilation.
# Matches DEFAULT_VENTILATION_AH_THRESHOLD in const.py.
VENTILATION_AH_THRESHOLD: float = 1.0  # g/m³

# Mold risk thresholds - dew point spread (T_room - Td) in degC
_MOLD_SPREAD_NONE: float = 7.0  # > 7 degC -> no risk
_MOLD_SPREAD_LOW: float = 5.0  # 5-7 degC -> low
_MOLD_SPREAD_MEDIUM: float = 3.0  # 3-5 degC -> medium  /  <= 3 degC -> high


def compute_dew_point(temp: float, rh: float) -> float:
    """Compute dew point (°C) via the Magnus formula.

    Args:
        temp: Air temperature in °C.
        rh:   Relative humidity in %, must be > 0.

    Returns:
        Dew point temperature in °C.

    """
    gamma = (_MAGNUS_A * temp) / (_MAGNUS_B + temp) + math.log(rh / 100.0)
    return (_MAGNUS_B * gamma) / (_MAGNUS_A - gamma)


def compute_absolute_humidity(temp: float, rh: float) -> float:
    """Compute absolute humidity (g/m³) from temperature (°C) and RH (%).

    AH = (RH/100) * es(T) * _AH_FACTOR / (T + 273.15)
    where es(T) = 6.112 * exp(a*T / (b+T))  [Magnus saturation vapour pressure, hPa]
    """
    es = 6.112 * math.exp((_MAGNUS_A * temp) / (_MAGNUS_B + temp))
    return (rh / 100.0) * es * _AH_FACTOR / (temp + 273.15)


def compute_mold_risk_level(temp: float, rh: float) -> str:
    """Return mold risk level string from temperature (°C) and relative humidity (%).

    The spread T_room - Td represents the margin between room air and its dew
    point. Cold surface spots are closer to the dew point than room air — a
    small spread means those surfaces approach 100 % surface RH.

    Thresholds:
        > 7 °C spread → "none"    (surface RH well below 70 %)
        > 5 °C spread → "low"     (cold bridges / poor-insulation spots)
        > 3 °C spread → "medium"  (corners, airing recommended)
                      → "high"    (near-condensation, widespread risk)
    """
    if rh <= 0:
        return "none"
    spread = temp - compute_dew_point(temp, rh)
    if spread > _MOLD_SPREAD_NONE:
        return "none"
    if spread > _MOLD_SPREAD_LOW:
        return "low"
    return "medium" if spread > _MOLD_SPREAD_MEDIUM else "high"


def compute_ventilation_beneficial(
    indoor_ah: float, outdoor_ah: float, threshold: float
) -> bool:
    """Return True if opening windows meaningfully reduces indoor moisture.

    Args:
        indoor_ah:  Indoor absolute humidity in g/m³.
        outdoor_ah: Outdoor absolute humidity in g/m³.
        threshold:  Minimum AH delta (g/m³) to consider ventilation worthwhile.
                    Prevents automation chatter from negligible differences.

    Returns:
        True when indoor AH exceeds outdoor AH by at least `threshold`.

    """
    return (indoor_ah - outdoor_ah) >= threshold
