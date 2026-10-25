"""List the hottest school-day afternoons (3-4 PM heat index at OCSA) since July 1, 2026."""

from datetime import date, datetime

import httpx

from heatsafe.config import LOCAL_TZ, PRESETS
from heatsafe.heat import heat_index_f
from heatsafe.weather import ARCHIVE_URL


def main() -> None:
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
        timeout=30,
    )
    response.raise_for_status()
    hourly = response.json()["hourly"]
    afternoons: dict[date, float] = {}
    for stamp, temp, humidity in zip(
        hourly["time"], hourly["temperature_2m"], hourly["relative_humidity_2m"]
    ):
        moment = datetime.fromisoformat(stamp)
        if moment.hour in (15, 16) and temp is not None and humidity is not None:
            value = heat_index_f(temp, humidity)
            afternoons[moment.date()] = max(afternoons.get(moment.date(), 0.0), value)

    hottest = sorted(afternoons.items(), key=lambda item: item[1], reverse=True)
    print("Hottest 3-4 PM heat index at OCSA (weekdays marked *):")
    for day, value in hottest[:10]:
        weekday = "*" if day.weekday() < 5 else " "
        print(f"  {day:%a %Y-%m-%d}{weekday}  {value:.0f} °F")


if __name__ == "__main__":
    main()
