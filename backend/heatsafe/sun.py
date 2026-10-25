from dataclasses import dataclass
from datetime import datetime

import pandas as pd
from pvlib.solarposition import get_solarposition


@dataclass(frozen=True)
class SunPosition:
    azimuth_deg: float  # clockwise from north
    elevation_deg: float  # above the horizon; negative means the sun is down


def sun_position(when: datetime, lat: float, lon: float) -> SunPosition:
    if when.tzinfo is None:
        raise ValueError("when must include a time zone")
    position = get_solarposition(pd.DatetimeIndex([when]), lat, lon)
    return SunPosition(
        azimuth_deg=float(position["azimuth"].iloc[0]),
        elevation_deg=float(position["apparent_elevation"].iloc[0]),
    )
