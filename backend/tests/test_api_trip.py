import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from heatsafe.api import app, llm_client, weather_service
from heatsafe.config import PRESETS
from heatsafe.weather import WeatherService

FIXTURES = Path(__file__).parent / "fixtures"
DEPART = "2026-09-05T15:30:00-07:00"
OCSA = {"lat": PRESETS["ocsa"]["lat"], "lon": PRESETS["ocsa"]["lon"]}
STATION = {"lat": PRESETS["sartc"]["lat"], "lon": PRESETS["sartc"]["lon"]}


class FirstRouteClient:
    def choose(self, payload: dict, lang: str) -> dict:
        route = payload["routes"][-1]
        return {"route_id": route["id"], "explanation": f"{route['shade_pct']}% shaded.",
                "translation": f"{route['shade_pct']}% con sombra."}


def weather_from(body: dict) -> WeatherService:
    return WeatherService(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)))


@pytest.fixture
def client():
    archive = json.loads((FIXTURES / "open_meteo_archive.json").read_text())
    app.dependency_overrides[weather_service] = lambda: weather_from(archive)
    app.dependency_overrides[llm_client] = lambda: FirstRouteClient()
    yield TestClient(app)
    app.dependency_overrides.clear()


def plan(client: TestClient, **overrides: object) -> httpx.Response:
    body = {"start": OCSA, "end": STATION, "depart_at": DEPART, **overrides}
    return client.post("/api/trip", json=body)


def test_trip_ocsa_to_station_returns_routes_and_recommendation(client: TestClient) -> None:
    response = plan(client)
    assert response.status_code == 200
    data = response.json()
    assert len(data["routes"]) >= 2
    assert data["routes"][0]["label"] == "fastest"
    assert data["recommendation"]["route_id"] in {r["id"] for r in data["routes"]}
    assert data["recommendation"]["source"] == "ai"
    assert data["tract"]["ces_version"] == "5.0"
    assert data["depart_at"] == DEPART


def test_out_of_area_400(client: TestClient) -> None:
    response = plan(client, start={"lat": 33.6510, "lon": -117.7430})  # Irvine Spectrum
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "out_of_area"
    assert "central Santa Ana" in response.json()["error"]["message"]


def test_trip_too_short_400(client: TestClient) -> None:
    response = plan(client, end={"lat": OCSA["lat"] + 0.0001, "lon": OCSA["lon"]})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "trip_too_short"
    assert response.json()["error"]["message"] == ("Start and destination are less than 50 m apart; "
                                                       "pick a farther destination.")


def test_same_node_is_trip_too_short(client: TestClient) -> None:
    # 70 m apart as the crow flies, but both points snap to the same graph node.
    from heatsafe.models import LatLng
    from heatsafe.trips import distance_m

    start = {"lat": 33.734193, "lon": -117.865513}
    end = {"lat": 33.734199, "lon": -117.864758}
    assert distance_m(LatLng(**start), LatLng(**end)) >= 50
    response = plan(client, start=start, end=end)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "trip_too_short"
    assert response.json()["error"]["message"] == ("Start and destination are too close together "
                                                       "to compare routes; pick a farther destination.")


def test_timeline_same_route_ids_each_slot(client: TestClient) -> None:
    trip = plan(client).json()
    response = client.get(f"/api/trip/{trip['trip_id']}/timeline", params={"start": "15:00", "end": "16:00"})
    assert response.status_code == 200
    slots = response.json()
    assert len(slots) == 5
    route_ids = {r["id"] for r in trip["routes"]}
    assert all({r["route_id"] for r in slot["routes"]} == route_ids for slot in slots)


def test_timeline_unknown_trip_404(client: TestClient) -> None:
    response = client.get("/api/trip/nope/timeline", params={"start": "15:00", "end": "16:00"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "trip_not_found"


def test_all_extreme_includes_alternatives(client: TestClient) -> None:
    archive = json.loads((FIXTURES / "open_meteo_archive.json").read_text())
    archive["hourly"]["temperature_2m"] = [112.0] * len(archive["hourly"]["time"])
    archive["hourly"]["relative_humidity_2m"] = [30] * len(archive["hourly"]["time"])
    app.dependency_overrides[weather_service] = lambda: weather_from(archive)
    data = plan(client).json()
    assert data["all_extreme"] is True
    assert data["alternatives"]["cool_places"]
    assert data["alternatives"]["stops"]


def test_presets_and_nearby_stops(client: TestClient) -> None:
    presets = client.get("/api/presets").json()
    assert {p["id"] for p in presets} == set(PRESETS)
    assert {"ocsa", "sartc"} <= set(PRESETS)
    stops = client.get("/api/stops/near", params={**OCSA, "n": 3, "at": DEPART}).json()
    assert len(stops) == 3
    assert stops[0]["departures"]


def test_local_times_without_offset_are_santa_ana_time(client: TestClient) -> None:
    response = plan(client, depart_at="2026-09-05T15:30:00", catch_at="2026-09-05T15:52:00")
    assert response.status_code == 200
    data = response.json()
    assert data["depart_at"] == DEPART
    assert all(r["arrives_in_time"] is not None for r in data["routes"])


def test_unexpected_error_uses_error_shape() -> None:
    def broken():
        raise RuntimeError("boom")

    app.dependency_overrides[weather_service] = broken
    try:
        response = TestClient(app, raise_server_exceptions=False).post(
            "/api/trip", json={"start": OCSA, "end": STATION, "depart_at": DEPART}
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "server_error"


def test_walkers_can_use_one_way_streets_in_both_directions(client: TestClient) -> None:
    response = plan(client, end={"lat": 33.77857, "lon": -117.87040})
    assert response.status_code == 200


def test_timeline_starts_at_departure_and_rechecks_arrival(client: TestClient) -> None:
    trip = plan(client, catch_at="2026-09-05T15:52:00-07:00").json()
    slots = client.get(
        f"/api/trip/{trip['trip_id']}/timeline", params={"start": "15:30", "end": "16:30"}
    ).json()
    assert slots[0]["at"] == DEPART
    assert slots[0]["routes"][0]["arrives_in_time"] is True
    assert slots[-1]["routes"][0]["arrives_in_time"] is False


def test_timeline_works_on_a_server_copy_that_never_saw_the_trip(client: TestClient) -> None:
    from heatsafe.models import LatLng, TripRequest
    from heatsafe.trips import encode_trip

    trip_id = encode_trip(TripRequest(start=LatLng(**OCSA), end=LatLng(**STATION), depart_at=DEPART))
    response = client.get(f"/api/trip/{trip_id}/timeline", params={"start": "15:30", "end": "16:00"})
    assert response.status_code == 200
    assert len(response.json()) == 3


def test_every_preset_is_inside_the_map() -> None:
    from heatsafe.models import LatLng
    from heatsafe.trips import in_study_area

    for key, p in PRESETS.items():
        assert in_study_area(LatLng(lat=p["lat"], lon=p["lon"])), key
