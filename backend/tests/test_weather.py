import json
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from heatsafe.heat import heat_index_f
from heatsafe.weather import WeatherService, WeatherUnavailable

FIXTURES = Path(__file__).parent / "fixtures"
LA = ZoneInfo("America/Los_Angeles")


def fixture_transport(name: str) -> httpx.MockTransport:
    body = json.loads((FIXTURES / name).read_text())
    return httpx.MockTransport(lambda request: httpx.Response(200, json=body))


def test_archive_picks_nearest_hour() -> None:
    service = WeatherService(transport=fixture_transport("open_meteo_archive.json"))
    weather = service.get_conditions(datetime(2026, 9, 5, 15, 40, tzinfo=LA))
    assert weather.valid_at == datetime(2026, 9, 5, 16, 0, tzinfo=LA)
    assert weather.temp_f == 85.1
    assert weather.rel_humidity == 32


def test_heat_index_computed_from_fixture() -> None:
    service = WeatherService(transport=fixture_transport("open_meteo_archive.json"))
    weather = service.get_conditions(datetime(2026, 9, 5, 15, 0, tzinfo=LA))
    assert weather.heat_index_f == pytest.approx(heat_index_f(89.7, 21))


def test_archive_vs_forecast_uses_pacific_date(monkeypatch) -> None:
    import heatsafe.weather as weather_module
    from heatsafe.weather import WeatherService

    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, json={"hourly": {
            "time": ["2026-10-17T12:00"],
            "temperature_2m": [80.0],
            "relative_humidity_2m": [40],
        }})

    real_date = weather_module.date
    real_datetime = weather_module.datetime

    class FrozenDate(real_date):
        @classmethod
        def today(cls) -> real_date:
            # 2026-10-23 06:30 UTC is still Oct 22 in Santa Ana; the server
            # (UTC) would say Oct 23.
            return real_date(2026, 10, 23)

    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            moment = real_datetime(2026, 10, 23, 6, 30, tzinfo=UTC)
            return moment.astimezone(tz) if tz is not None else moment.replace(tzinfo=None)

    monkeypatch.setattr(weather_module, "date", FrozenDate)
    monkeypatch.setattr(weather_module, "datetime", FrozenDateTime)
    service = WeatherService(transport=httpx.MockTransport(handler))
    service.get_conditions(datetime(2026, 10, 17, 12, 0, tzinfo=LA))
    assert len(requested) == 1
    assert "archive-api" not in requested[0]
    assert "api.open-meteo.com" in requested[0]


def test_timeout_raises_weather_unavailable() -> None:
    def time_out(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    service = WeatherService(transport=httpx.MockTransport(time_out))
    with pytest.raises(WeatherUnavailable):
        service.get_conditions(datetime(2026, 9, 5, 15, 0, tzinfo=LA))


def test_archive_down_falls_back_to_the_forecast_service() -> None:
    forecast = json.loads((FIXTURES / "open_meteo_archive.json").read_text())
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.host)
        if request.url.host == "archive-api.open-meteo.com":
            return httpx.Response(503)
        return httpx.Response(200, json=forecast)

    service = WeatherService(transport=httpx.MockTransport(handler), saved_dir=None)
    weather = service.get_conditions(datetime(2026, 9, 5, 15, 40, tzinfo=LA))
    assert requested == ["archive-api.open-meteo.com", "api.open-meteo.com"]
    assert weather.temp_f == 85.1
    assert "forecast" in weather.source


def test_saved_day_needs_no_network(tmp_path) -> None:
    (tmp_path / "open_meteo_2026-09-05.json").write_text((FIXTURES / "open_meteo_archive.json").read_text())

    def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    service = WeatherService(transport=httpx.MockTransport(offline), saved_dir=tmp_path)
    weather = service.get_conditions(datetime(2026, 9, 5, 15, 40, tzinfo=LA))
    assert weather.temp_f == 85.1
    assert weather.rel_humidity == 32
    assert "saved" in weather.source
