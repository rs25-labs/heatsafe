from datetime import datetime
from zoneinfo import ZoneInfo

from heatsafe.config import PRESETS
from heatsafe.sun import sun_position

LA = ZoneInfo("America/Los_Angeles")
LAT, LON = PRESETS["ocsa"]["lat"], PRESETS["ocsa"]["lon"]


def test_noon_summer_solstice_santa_ana() -> None:
    sun = sun_position(datetime(2026, 6, 21, 12, 55, tzinfo=LA), LAT, LON)
    assert abs(sun.elevation_deg - 79.5) <= 1.0


def test_sun_down_at_night() -> None:
    sun = sun_position(datetime(2026, 8, 1, 22, 0, tzinfo=LA), LAT, LON)
    assert sun.elevation_deg < 0
