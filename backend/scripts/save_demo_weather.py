"""Save the demo afternoons' weather from Open-Meteo's archive and ship it with the data.

Writes data/processed/weather/open_meteo_<date>.json (the archive's own response), so
the demo trip works even when the archive is down. Same days as bake_shade.py.
"""

import json

import httpx

from heatsafe.config import get_settings
from heatsafe.weather import (
    ARCHIVE_URL,
    TIMEOUT_S,
    parse_hours,
    query,
    saved_name,
    saved_weather_dir,
)
from scripts.bake_shade import EXTRA_DAYS


def main() -> None:
    settings = get_settings()
    out = saved_weather_dir()
    out.mkdir(parents=True, exist_ok=True)
    days = sorted({*EXTRA_DAYS, *([settings.demo_date] if settings.demo_date else [])})
    with httpx.Client(timeout=TIMEOUT_S * 4) as client:
        for day in days:
            response = client.get(ARCHIVE_URL, params=query(day))
            response.raise_for_status()
            body = response.json()
            hours = parse_hours(body)  # fails loudly if the response isn't usable
            (out / saved_name(day)).write_text(json.dumps(body, indent=1) + "\n")
            print(f"{day}: {len(hours)} hours saved")


if __name__ == "__main__":
    main()
