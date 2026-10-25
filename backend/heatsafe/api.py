from datetime import datetime, time
from typing import Annotated

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from heatsafe.config import PRESETS, get_settings
from heatsafe.data_store import DataStore, get_store
from heatsafe.heat import exposure_level
from heatsafe.models import (
    Conditions,
    LatLng,
    Preset,
    StopWithDepartures,
    TimelineSlot,
    TripRequest,
    TripResponse,
)
from heatsafe.recommend import LLMClient, default_client
from heatsafe.transit import Transit, get_transit
from heatsafe.trips import TripError, decode_trip, local, plan_trip, rebuild_trip, timeline
from heatsafe.weather import WeatherService, WeatherUnavailable, get_weather_service

app = FastAPI(title="HeatSafe OC")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


@app.exception_handler(TripError)
def trip_error(_: Request, exc: TripError) -> JSONResponse:
    return error(exc.status, exc.code, exc.message)


@app.exception_handler(WeatherUnavailable)
def weather_error(_: Request, exc: WeatherUnavailable) -> JSONResponse:
    return error(
        503, "weather_unavailable",
        "Weather data couldn't be loaded right now; try again in a minute.",
    )


@app.exception_handler(Exception)
def unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    return error(
        500, "server_error",
        "Something went wrong on the HeatSafe server; try again, and check the server log if it repeats.",
    )


@app.exception_handler(RequestValidationError)
def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(p) for p in first.get("loc", []) if p != "body")
    return error(400, "invalid_request", f"Check the {where or 'request'}: {first.get('msg', 'invalid value')}.")


def store() -> DataStore:
    return get_store()


def weather_service() -> WeatherService:
    return get_weather_service()


def llm_client() -> LLMClient | None:
    return default_client()


def transit() -> Transit:
    return get_transit()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/conditions")
def conditions(
    at: datetime, weather: Annotated[WeatherService, Depends(weather_service)]
) -> Conditions:
    moment = local(at)
    current = weather.get_conditions(moment)
    return Conditions(
        weather=current,
        shade_level=exposure_level(round(current.heat_index_f, 1)),
        sun_level=exposure_level(round(current.heat_index_f + 15, 1)),
    )


@app.get("/api/warm")
def warm() -> dict[str, str]:
    """Load the street, shade and schedule data now, so the visitor's first trip is fast.

    The page calls this as soon as it opens; on a server that was idle, this is the slow part.
    """
    get_store()
    get_transit()
    return {"status": "ready"}


@app.get("/api/presets")
def presets() -> list[Preset]:
    return [
        Preset(id=key, name=str(p["name"]), location=LatLng(lat=p["lat"], lon=p["lon"]))
        for key, p in PRESETS.items()
    ]


@app.get("/api/config")
def config() -> dict[str, str | None]:
    demo = get_settings().demo_date
    return {"demo_date": demo.isoformat() if demo else None}


@app.post("/api/trip")
def trip(
    request: TripRequest,
    data: Annotated[DataStore, Depends(store)],
    weather: Annotated[WeatherService, Depends(weather_service)],
    client: Annotated[LLMClient | None, Depends(llm_client)],
    schedules: Annotated[Transit, Depends(transit)],
) -> TripResponse:
    return plan_trip(request, data, weather, client, schedules)


@app.get("/api/trip/{trip_id}/timeline")
def trip_timeline(
    trip_id: str,
    data: Annotated[DataStore, Depends(store)],
    weather: Annotated[WeatherService, Depends(weather_service)],
    start: Annotated[time, Query()] = time(15, 0),
    end: Annotated[time, Query()] = time(19, 0),
) -> list[TimelineSlot]:
    saved, _ = rebuild_trip(decode_trip(trip_id), data)
    return timeline(data, saved, weather, start, end)


@app.get("/api/stops/near")
def stops_near(
    lat: float,
    lon: float,
    at: datetime,
    schedules: Annotated[Transit, Depends(transit)],
    n: Annotated[int, Query(ge=1, le=10)] = 5,
) -> list[StopWithDepartures]:
    when = local(at)
    return [
        StopWithDepartures(stop=stop, departures=schedules.next_departures(stop.stop_id, when))
        for stop in schedules.nearest_stops(LatLng(lat=lat, lon=lon), n)
    ]
