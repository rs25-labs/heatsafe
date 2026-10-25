"""Compare the demo trip across the hottest school-day afternoons.

For the 10 hottest weekday afternoons since 2026-07-01 (same ranking as
pick_demo_date.py), plan OCSA -> station at 15:30 and print each route's shade %,
sun minutes, and rating, plus whether the ratings differ. Rule-based pick
(client=None): no AI calls. Does not change HEATSAFE_DEMO_DATE.

Run from backend/: uv run python -m scripts.compare_days
"""

import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from heatsafe.config import LOCAL_TZ, PRESETS
from heatsafe.data_store import get_store
from heatsafe.heat import heat_index_f
from heatsafe.models import LatLng, TripRequest
from heatsafe.transit import get_transit
from heatsafe.trips import TripError, plan_trip
from heatsafe.weather import ARCHIVE_URL, WeatherService, WeatherUnavailable

LA = ZoneInfo(LOCAL_TZ)


def hottest_school_days(limit: int = 10) -> list[tuple[date, float]]:
    response = httpx.get(
        ARCHIVE_URL,
        params={
            "latitude": PRESETS["ocsa"]["lat"],
            "longitude": PRESETS["ocsa"]["lon"],
            "hourly": "temperature_2m,relative_humidity_2m",
            "temperature_unit": "fahrenheit",
            "timezone": LOCAL_TZ,
            "start_date": "2026-07-01",
            "end_date": "2026-10-16",
        },
        timeout=60,
    )
    response.raise_for_status()
    hourly = response.json()["hourly"]
    afternoons: dict[date, float] = {}
    for stamp, temp, humidity in zip(
        hourly["time"], hourly["temperature_2m"], hourly["relative_humidity_2m"]
    ):
        moment = datetime.fromisoformat(stamp)
        if moment.hour in (15, 16) and temp is not None and humidity is not None:
            day = moment.date()
            if day.weekday() < 5:
                afternoons[day] = max(afternoons.get(day, 0.0), heat_index_f(temp, humidity))
    return sorted(afternoons.items(), key=lambda item: item[1], reverse=True)[:limit]


def main() -> int:
    days = hottest_school_days()
    store = get_store()
    transit = get_transit()
    weather = WeatherService()
    ocsa, station = PRESETS["ocsa"], PRESETS["sartc"]
    print("demo trip OCSA -> station at 15:30 PT (rule-based pick, no AI calls)")
    print("date        HI_F  routes: shade%/sun_min/rating each  ratings_differ")
    for day, heat_index in days:
        depart = datetime(day.year, day.month, day.day, 15, 30, tzinfo=LA)
        try:
            trip = plan_trip(
                TripRequest(
                    start=LatLng(lat=ocsa["lat"], lon=ocsa["lon"]),
                    end=LatLng(lat=station["lat"], lon=station["lon"]),
                    depart_at=depart, lang="en",
                ),
                store, weather, None, transit,
            )
        except (TripError, WeatherUnavailable) as exc:
            print(f"{day} {heat_index:5.1f}  ERROR {exc}")
            continue
        cells = "  ".join(
            f"{r.shade_pct:>3}%/{r.sun_minutes:>4.1f}m/{r.exposure.value:<8}" for r in trip.routes
        )
        differ = "YES" if len({r.exposure for r in trip.routes}) > 1 else "no"
        print(f"{day} {heat_index:5.1f}  {cells}  {differ}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
