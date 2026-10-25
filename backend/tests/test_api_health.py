from fastapi.testclient import TestClient

from heatsafe.api import app


def test_health_returns_ok() -> None:
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_warm_loads_the_data_ahead_of_the_first_trip() -> None:
    from heatsafe.data_store import get_store

    response = TestClient(app).get("/api/warm")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert get_store.cache_info().currsize == 1
