from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from heatsafe.config import PRESETS
from heatsafe.models import LatLng
from heatsafe.transit import Transit

LA = ZoneInfo("America/Los_Angeles")
TRANSIT = Transit.load(Path(__file__).parent / "fixtures" / "gtfs_small")
OCSA = LatLng(lat=PRESETS["ocsa"]["lat"], lon=PRESETS["ocsa"]["lon"])


def test_nearest_stops_sorted_by_distance() -> None:
    stops = TRANSIT.nearest_stops(OCSA, n=3)
    assert stops[0].stop_id == "octa:100"
    assert [s.distance_m for s in stops] == sorted(s.distance_m for s in stops)


def test_next_departures_after_time_and_service_day() -> None:
    wednesday = datetime(2026, 9, 9, 15, 30, tzinfo=LA)
    departures = TRANSIT.next_departures("octa:100", wednesday, n=3)
    assert [d.departs_at for d in departures] == [datetime(2026, 9, 9, 15, 50, tzinfo=LA)]
    assert departures[0].route_name == "53"
    assert departures[0].headsign == "Anaheim"


def test_metrolink_route_uses_long_name() -> None:
    wednesday = datetime(2026, 9, 9, 15, 30, tzinfo=LA)
    departures = TRANSIT.next_departures("metrolink:154", wednesday)
    assert departures[0].route_name == "Orange County Line"
