"""Heat index (NWS formula) and the four-level exposure rating used for each route."""

import math
from enum import StrEnum

# NWS: full sunshine can raise the heat index by up to 15 °F
FULL_SUN_BONUS_F = 15.0


class ExposureLevel(StrEnum):
    low = "low"
    moderate = "moderate"
    high = "high"
    extreme = "extreme"


def heat_index_f(temp_f: float, rel_humidity: float) -> float:
    """NWS heat index: https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml"""
    t, rh = temp_f, rel_humidity
    simple = 0.5 * (t + 61.0 + (t - 68.0) * 1.2 + rh * 0.094)
    if (simple + t) / 2 < 80:
        return simple

    hi = (
        -42.379 + 2.04901523 * t + 10.14333127 * rh - 0.22475541 * t * rh
        - 0.00683783 * t * t - 0.05481717 * rh * rh + 0.00122874 * t * t * rh
        + 0.00085282 * t * rh * rh - 0.00000199 * t * t * rh * rh
    )
    if rh < 13 and 80 <= t <= 112:
        hi -= ((13 - rh) / 4) * math.sqrt((17 - abs(t - 95.0)) / 17)
    elif rh > 85 and 80 <= t <= 87:
        hi += ((rh - 85) / 10) * ((87 - t) / 5)
    return hi


def effective_heat_index_f(heat_index: float, sun_fraction: float) -> float:
    return heat_index + FULL_SUN_BONUS_F * sun_fraction


def exposure_level(effective_hi_f: float) -> ExposureLevel:
    if effective_hi_f < 90:
        return ExposureLevel.low
    if effective_hi_f < 103:
        return ExposureLevel.moderate
    if effective_hi_f < 115:
        return ExposureLevel.high
    return ExposureLevel.extreme
