"""Plan a trip end to end: routes, scores, recommendation, and what to do if nothing is safe."""

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

import numpy as np
from pyproj import Transformer
from shapely.geometry import Point

from heatsafe.config import LOCAL_TZ, PROJECTED_CRS, STUDY_BBOX
from heatsafe.data_store import DataStore
from heatsafe.heat import ExposureLevel
from heatsafe.models import (
    AmenityOnRoute,
    LatLng,
    Route,
    RouteAtTime,
    RouteLabel,
    SafetyAlternatives,
    StopWithDepartures,
    TimelineSlot,
    TractContext,
    TripRequest,
    TripResponse,
)
from heatsafe.recommend import LLMClient, recommend
from heatsafe.routing import candidate_paths, nearest_node
from heatsafe.scoring import score_route
from heatsafe.shade import (
    EdgeKey,
    fractions_from_mask,
    path_sun_mask,
    sample_sun_mask,
    slot_after,
    slot_start,
)
from heatsafe.transit import Transit
from heatsafe.weather import WeatherService

MIN_TRIP_M = 50.0
LATEST_SLOT = time(20, 0)
COOL_KINDS = {"library", "cooling_center", "store"}

to_projected = Transformer.from_crs("EPSG:4326", PROJECTED_CRS, always_xy=True)


class TripError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


@dataclass
class SavedTrip:
    request: TripRequest
    paths: list[list[EdgeKey]]
    labels: list[RouteLabel]




def in_study_area(point: LatLng) -> bool:
    south, west, north, east = STUDY_BBOX
    return south <= point.lat <= north and west <= point.lon <= east


def distance_m(a: LatLng, b: LatLng) -> float:
    ax, ay = to_projected.transform(a.lon, a.lat)
    bx, by = to_projected.transform(b.lon, b.lat)
    return float(np.hypot(ax - bx, ay - by))


def local(when: datetime) -> datetime:
    tz = ZoneInfo(LOCAL_TZ)
    return when.replace(tzinfo=tz) if when.tzinfo is None else when.astimezone(tz)


def validate(request: TripRequest) -> None:
    if not (in_study_area(request.start) and in_study_area(request.end)):
        raise TripError(
            400, "out_of_area",
            "HeatSafe currently covers central Santa Ana; pick a place inside the map.",
        )
    if distance_m(request.start, request.end) < MIN_TRIP_M:
        raise TripError(
            400, "trip_too_short",
            "Start and destination are less than 50 m apart; pick a farther destination.",
        )


def labels_for(count: int) -> list[RouteLabel]:
    if count == 1:
        return ["fastest"]
    middle: list[RouteLabel] = ["balanced"] + ["alternate"] * (count - 3)
    return ["fastest", *middle[: count - 2], "shadiest"]


def tract_context(store: DataStore, point: LatLng) -> TractContext | None:
    matches = store.tracts[store.tracts.contains(Point(point.lon, point.lat))]
    if matches.empty:
        return None
    row = matches.iloc[0]
    skip = {"tract_id", "ces_version", "source_url", "geometry"}
    fields = {
        name: (None if row[name] != row[name] else round(float(row[name]), 1))
        for name in store.tracts.columns if name not in skip
    }
    return TractContext(
        tract_id=row["tract_id"], ces_version=row["ces_version"], fields=fields,
        source_url=row["source_url"],
    )


def score_paths(
    store: DataStore, saved: SavedTrip, in_sun: np.ndarray, weather_service: WeatherService,
    depart_at: datetime,
) -> list[Route]:
    weather = weather_service.get_conditions(depart_at)
    return [
        score_route(
            store, path, in_sun, weather, depart_at, saved.request.catch_at, f"r{i}", label,
            start=saved.request.start, end=saved.request.end,
        )
        for i, (path, label) in enumerate(zip(saved.paths, saved.labels, strict=True))
    ]


def timeline(
    store: DataStore, saved: SavedTrip, weather_service: WeatherService, start: time, end: time,
) -> list[TimelineSlot]:
    depart = local(saved.request.depart_at)
    slot = slot_start(depart.replace(hour=start.hour, minute=start.minute))
    last = depart.replace(hour=end.hour, minute=end.minute)
    slots = []
    while slot <= last:
        in_sun = path_sun_mask(store, saved.paths, slot)
        routes = score_paths(store, saved, in_sun, weather_service, slot)
        slots.append(
            TimelineSlot(
                at=slot,
                weather=weather_service.get_conditions(slot),
                routes=[
                    RouteAtTime(
                        route_id=r.id, shade_pct=r.shade_pct, sun_minutes=r.sun_minutes,
                        effective_heat_index_f=r.effective_heat_index_f, exposure=r.exposure,
                        segments=r.segments, arrives_in_time=r.arrives_in_time,
                        minutes_to_spare=r.minutes_to_spare,
                    )
                    for r in routes
                ],
            )
        )
        slot = slot_after(slot, 1)
    return slots


def cool_places(store: DataStore, point: LatLng) -> list[AmenityOnRoute]:
    nearby = sorted(
        (
            AmenityOnRoute(amenity=a, distance_along_m=round(distance_m(point, a.location), 1))
            for a in store.amenities if a.kind in COOL_KINDS
        ),
        key=lambda a: a.distance_along_m,
    )
    return nearby[:3]


def safety_alternatives(
    store: DataStore, saved: SavedTrip, weather_service: WeatherService, transit: Transit,
) -> SafetyAlternatives:
    depart = local(saved.request.depart_at)
    next_slot = slot_after(depart, 1)
    later = (
        timeline(store, saved, weather_service, next_slot.time(), LATEST_SLOT)
        if next_slot.date() == depart.date()
        else []
    )
    best = next(
        (s.at for s in later if any(r.exposure != ExposureLevel.extreme for r in s.routes)), None
    )
    stops = [
        StopWithDepartures(stop=stop, departures=transit.next_departures(stop.stop_id, depart))
        for stop in transit.nearest_stops(saved.request.start)
    ]
    return SafetyAlternatives(
        best_slot=best, cool_places=cool_places(store, saved.request.start), stops=stops
    )


def encode_trip(request: TripRequest) -> str:
    """The trip id carries the trip itself, so any server copy can rebuild it (no shared memory)."""
    fields = request.model_dump(mode="json", include={"start", "end", "depart_at", "catch_at"})
    return base64.urlsafe_b64encode(json.dumps(fields, separators=(",", ":")).encode()).decode().rstrip("=")


def decode_trip(trip_id: str) -> TripRequest:
    try:
        raw = base64.urlsafe_b64decode(trip_id + "=" * (-len(trip_id) % 4))
        return TripRequest.model_validate_json(raw)
    except (binascii.Error, ValueError) as error:
        raise TripError(404, "trip_not_found", "That trip link isn't valid; plan the trip again.") from error


def rebuild_trip(request: TripRequest, store: DataStore) -> tuple[SavedTrip, np.ndarray]:
    """Validate a request and find its routes; deterministic, so the same request gives the same routes."""
    validate(request)
    request = request.model_copy(
        update={
            "depart_at": local(request.depart_at),
            "catch_at": local(request.catch_at) if request.catch_at else None,
        }
    )
    source, _ = nearest_node(store.graph, request.start)
    target, _ = nearest_node(store.graph, request.end)
    if source == target:
        raise TripError(
            400, "trip_too_short",
            "Start and destination are too close together to compare routes; "
            "pick a farther destination.",
        )
    in_sun = sample_sun_mask(store, request.depart_at)
    paths = candidate_paths(store.graph, request.start, request.end, fractions_from_mask(store, in_sun))
    if not paths:
        raise TripError(404, "no_route", "No walking route connects these places; try nearby streets.")
    return SavedTrip(request=request, paths=paths, labels=labels_for(len(paths))), in_sun


def plan_trip(
    request: TripRequest, store: DataStore, weather_service: WeatherService,
    client: LLMClient | None, transit: Transit,
) -> TripResponse:
    saved, in_sun = rebuild_trip(request, store)
    request = saved.request
    depart = request.depart_at
    routes = score_paths(store, saved, in_sun, weather_service, depart)
    weather = weather_service.get_conditions(depart)
    trip_id = encode_trip(request)

    all_extreme = all(r.exposure == ExposureLevel.extreme for r in routes)
    return TripResponse(
        trip_id=trip_id,
        depart_at=depart,
        routes=routes,
        weather=weather,
        recommendation=recommend(routes, weather, request.note, request.lang, client),
        tract=tract_context(store, request.start),
        all_extreme=all_extreme,
        alternatives=safety_alternatives(store, saved, weather_service, transit) if all_extreme else None,
    )
