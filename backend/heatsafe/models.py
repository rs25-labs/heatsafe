from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from heatsafe.heat import ExposureLevel

AmenityKind = Literal["drinking_water", "library", "cooling_center", "store", "pharmacy", "park"]


class LatLng(BaseModel):
    lat: float
    lon: float


class Amenity(BaseModel):
    kind: AmenityKind
    name: str
    location: LatLng
    source: str


class Weather(BaseModel):
    temp_f: float
    rel_humidity: float
    heat_index_f: float
    valid_at: datetime
    source: str
    source_url: str


class Conditions(BaseModel):
    weather: Weather
    shade_level: ExposureLevel
    sun_level: ExposureLevel


class Segment(BaseModel):
    coords: list[LatLng]
    length_m: float
    in_sun: bool
    start_m: float


class AmenityOnRoute(BaseModel):
    amenity: Amenity
    distance_along_m: float


RouteLabel = Literal["fastest", "shadiest", "balanced", "alternate"]


class Route(BaseModel):
    id: str
    label: RouteLabel
    distance_m: float
    duration_min: float
    sun_minutes: float
    shade_pct: int
    effective_heat_index_f: float
    exposure: ExposureLevel
    segments: list[Segment]
    amenities: list[AmenityOnRoute]
    arrives_in_time: bool | None
    minutes_to_spare: float | None


class Stop(BaseModel):
    stop_id: str
    name: str
    agency: Literal["octa", "metrolink"]
    location: LatLng
    distance_m: float


class Departure(BaseModel):
    route_name: str
    headsign: str
    departs_at: datetime


class StopWithDepartures(BaseModel):
    stop: Stop
    departures: list[Departure]


Lang = Literal["en", "es"]


class Recommendation(BaseModel):
    route_id: str
    explanation: str
    lang: Lang
    source: Literal["ai", "fallback"]
    # The same reason in English and Spanish, so switching languages doesn't need a new trip.
    explanations: dict[Lang, str]


class TripRequest(BaseModel):
    start: LatLng
    end: LatLng
    depart_at: datetime
    catch_at: datetime | None = None
    note: str | None = Field(default=None, max_length=500)
    lang: Lang = "en"


class TractContext(BaseModel):
    tract_id: str
    ces_version: str
    fields: dict[str, float | None]
    source_url: str


class SafetyAlternatives(BaseModel):
    best_slot: datetime | None
    cool_places: list[AmenityOnRoute]
    stops: list[StopWithDepartures]


class TripResponse(BaseModel):
    trip_id: str
    depart_at: datetime
    routes: list[Route]
    weather: Weather
    recommendation: Recommendation
    tract: TractContext | None
    all_extreme: bool
    alternatives: SafetyAlternatives | None


class RouteAtTime(BaseModel):
    route_id: str
    shade_pct: int
    sun_minutes: float
    effective_heat_index_f: float
    exposure: ExposureLevel
    segments: list[Segment]
    arrives_in_time: bool | None
    minutes_to_spare: float | None


class TimelineSlot(BaseModel):
    at: datetime
    weather: Weather
    routes: list[RouteAtTime]


class Preset(BaseModel):
    id: str
    name: str
    location: LatLng
