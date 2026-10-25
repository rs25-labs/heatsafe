from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from heatsafe.api import app, weather_service
from heatsafe.models import Weather
from heatsafe.weather import WeatherUnavailable

LA = ZoneInfo("America/Los_Angeles")
WHEN = datetime(2026, 9, 10, 15, 30, tzinfo=LA)


class FixedWeatherService:
    def __init__(self, heat_index_f: float) -> None:
        self.heat_index_f = heat_index_f

    def get_conditions(self, when: datetime) -> Weather:
        return Weather(
            temp_f=100.0, rel_humidity=40, heat_index_f=self.heat_index_f,
            valid_at=when, source="test", source_url="https://open-meteo.com/",
        )


class FailingWeatherService:
    def get_conditions(self, when: datetime) -> Weather:
        raise WeatherUnavailable("down")


def test_conditions_levels() -> None:
    app.dependency_overrides[weather_service] = lambda: FixedWeatherService(108.0)
    try:
        response = TestClient(app).get("/api/conditions", params={"at": WHEN.isoformat()})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    data = response.json()
    assert data["weather"]["heat_index_f"] == 108.0
    assert data["shade_level"] == "high"
    assert data["sun_level"] == "extreme"


def test_conditions_weather_unavailable_503() -> None:
    app.dependency_overrides[weather_service] = lambda: FailingWeatherService()
    try:
        response = TestClient(app).get("/api/conditions", params={"at": WHEN.isoformat()})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "weather_unavailable"
