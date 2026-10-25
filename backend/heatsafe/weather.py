"""Hourly temperature and humidity at OCSA from Open-Meteo (past days and forecasts).

Past days come from Open-Meteo's historical archive. The demo days are also saved with
the app (scripts/save_demo_weather.py), so the demo works when the archive is down; for
other past days the forecast service, which keeps about three months, is the backup.
"""

import json
from datetime import date, datetime, timedelta
from functools import cache
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from heatsafe.config import LOCAL_TZ, PRESETS, get_settings
from heatsafe.heat import heat_index_f
from heatsafe.models import Weather

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
SOURCE_PAGE = "https://open-meteo.com/"
ARCHIVE_DELAY_DAYS = 6  # the archive lags a few days behind today
TIMEOUT_S = 8.0


class WeatherUnavailable(Exception):
    pass


SOURCE_ARCHIVE = "Open-Meteo"
SOURCE_SAVED = "Open-Meteo (saved copy)"
SOURCE_FORECAST = "Open-Meteo forecast model (historical archive unavailable)"

Hours = dict[datetime, tuple[float, float]]


def saved_weather_dir() -> Path:
    return get_settings().data_dir / "processed" / "weather"


def saved_name(day: date) -> str:
    return f"open_meteo_{day.isoformat()}.json"


def query(day: date) -> dict[str, str | float]:
    return {
        "latitude": PRESETS["ocsa"]["lat"],
        "longitude": PRESETS["ocsa"]["lon"],
        "hourly": "temperature_2m,relative_humidity_2m",
        "temperature_unit": "fahrenheit",
        "timezone": LOCAL_TZ,
        "start_date": day.isoformat(),
        "end_date": day.isoformat(),
    }


def parse_hours(body: dict) -> Hours:
    hourly = body["hourly"]
    tz = ZoneInfo(LOCAL_TZ)
    return {
        datetime.fromisoformat(stamp).replace(tzinfo=tz): (temp, humidity)
        for stamp, temp, humidity in zip(
            hourly["time"], hourly["temperature_2m"], hourly["relative_humidity_2m"]
        )
        if temp is not None and humidity is not None
    }


class WeatherService:
    def __init__(
        self, transport: httpx.BaseTransport | None = None, saved_dir: Path | None = None,
    ) -> None:
        self.client = httpx.Client(transport=transport, timeout=TIMEOUT_S)
        self.saved_dir = saved_dir
        self.hourly: dict[date, tuple[Hours, str]] = {}

    def get_conditions(self, when: datetime) -> Weather:
        forced = get_settings().force_weather
        if forced:
            temp_f, humidity = (float(v) for v in forced.split(","))
            return self.build(when, temp_f, humidity, "Forced test values (development only)")

        local = when.astimezone(ZoneInfo(LOCAL_TZ))
        nearest = (local + timedelta(minutes=30)).replace(minute=0, second=0, microsecond=0)
        hours, source = self.hours_for(nearest.date())
        if nearest not in hours:
            raise WeatherUnavailable(f"No weather data for {nearest:%Y-%m-%d %H:%M}")
        temp_f, humidity = hours[nearest]
        return self.build(nearest, temp_f, humidity, source)

    def build(self, valid_at: datetime, temp_f: float, humidity: float, source: str) -> Weather:
        return Weather(
            temp_f=temp_f,
            rel_humidity=humidity,
            heat_index_f=heat_index_f(temp_f, humidity),
            valid_at=valid_at,
            source=source,
            source_url=SOURCE_PAGE,
        )

    def hours_for(self, day: date) -> tuple[Hours, str]:
        if day not in self.hourly:
            self.hourly[day] = self.fetch(day)
        return self.hourly[day]

    def fetch(self, day: date) -> tuple[Hours, str]:
        saved = self.saved_dir / saved_name(day) if self.saved_dir else None
        if saved is not None and saved.exists():
            return parse_hours(json.loads(saved.read_text())), SOURCE_SAVED
        today_la = datetime.now(ZoneInfo(LOCAL_TZ)).date()
        if day > today_la - timedelta(days=ARCHIVE_DELAY_DAYS):
            return self.get(FORECAST_URL, day), SOURCE_ARCHIVE
        try:
            return self.get(ARCHIVE_URL, day), SOURCE_ARCHIVE
        except WeatherUnavailable:
            return self.get(FORECAST_URL, day), SOURCE_FORECAST

    def get(self, url: str, day: date) -> Hours:
        try:
            response = self.client.get(url, params=query(day))
            response.raise_for_status()
            return parse_hours(response.json())
        except (httpx.HTTPError, KeyError, ValueError) as error:
            raise WeatherUnavailable(str(error)) from error


@cache
def get_weather_service() -> WeatherService:
    return WeatherService(saved_dir=saved_weather_dir())


def get_conditions(when: datetime) -> Weather:
    return get_weather_service().get_conditions(when)
