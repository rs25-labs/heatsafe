"""Nearby bus and train stops and their next departures, from OCTA and Metrolink GTFS."""

import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import cache
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from pyproj import Transformer

from heatsafe.config import LOCAL_TZ, PROJECTED_CRS, STUDY_BBOX, get_settings
from heatsafe.models import Departure, LatLng, Stop

AGENCIES = ("octa", "metrolink")
BBOX_MARGIN_DEG = 0.01
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

to_projected = Transformer.from_crs("EPSG:4326", PROJECTED_CRS, always_xy=True)


def read(folder: Path, name: str, **kwargs: object) -> pd.DataFrame:
    return pd.read_csv(folder / name, dtype=str, encoding="utf-8-sig", **kwargs)


@dataclass
class Transit:
    stops: pd.DataFrame  # stop_id, name, agency, lat, lon, x, y
    departures: pd.DataFrame  # stop_id, seconds, service_id, agency, route_name, headsign
    calendars: dict[str, pd.DataFrame]
    calendar_dates: dict[str, pd.DataFrame]

    @classmethod
    def load(cls, gtfs_dir: Path) -> "Transit":
        south, west, north, east = STUDY_BBOX
        stops_parts, departure_parts = [], []
        calendars, calendar_dates = {}, {}
        for agency in AGENCIES:
            folder = gtfs_dir / agency
            stops = read(folder, "stops.txt", usecols=["stop_id", "stop_name", "stop_lat", "stop_lon"])
            stops["lat"] = stops["stop_lat"].astype(float)
            stops["lon"] = stops["stop_lon"].astype(float)
            stops = stops[
                stops["lat"].between(south - BBOX_MARGIN_DEG, north + BBOX_MARGIN_DEG)
                & stops["lon"].between(west - BBOX_MARGIN_DEG, east + BBOX_MARGIN_DEG)
            ]
            stops = stops.assign(stop_id=agency + ":" + stops["stop_id"], agency=agency)
            stops = stops.rename(columns={"stop_name": "name"})[["stop_id", "name", "agency", "lat", "lon"]]
            stops_parts.append(stops)

            times = read(folder, "stop_times.txt", usecols=["trip_id", "departure_time", "stop_id"])
            times["stop_id"] = agency + ":" + times["stop_id"]
            times = times[times["stop_id"].isin(stops["stop_id"])]
            trips = read(folder, "trips.txt", usecols=["route_id", "service_id", "trip_id", "trip_headsign"])
            routes = read(folder, "routes.txt", usecols=["route_id", "route_short_name", "route_long_name"])
            routes["route_name"] = routes["route_short_name"].fillna(routes["route_long_name"])
            merged = times.merge(trips, on="trip_id").merge(routes[["route_id", "route_name"]], on="route_id")
            hms = merged["departure_time"].str.strip().str.split(":", expand=True).astype(int)
            merged["seconds"] = hms[0] * 3600 + hms[1] * 60 + hms[2]
            merged["agency"] = agency
            merged["headsign"] = merged["trip_headsign"].fillna("")
            departure_parts.append(
                merged[["stop_id", "seconds", "service_id", "agency", "route_name", "headsign"]]
            )
            calendars[agency] = read(folder, "calendar.txt")
            calendar_dates[agency] = read(folder, "calendar_dates.txt")

        all_stops = pd.concat(stops_parts, ignore_index=True)
        x, y = to_projected.transform(all_stops["lon"].to_numpy(), all_stops["lat"].to_numpy())
        all_stops["x"], all_stops["y"] = x, y
        return cls(all_stops, pd.concat(departure_parts, ignore_index=True), calendars, calendar_dates)

    def nearest_stops(self, point: LatLng, n: int = 3) -> list[Stop]:
        x, y = to_projected.transform(point.lon, point.lat)
        distances = np.hypot(self.stops["x"] - x, self.stops["y"] - y)
        nearest = self.stops.assign(distance=distances).nsmallest(n, "distance")
        return [
            Stop(
                stop_id=row.stop_id, name=row.name, agency=row.agency,
                location=LatLng(lat=row.lat, lon=row.lon), distance_m=round(row.distance, 1),
            )
            for row in nearest.itertuples()
        ]

    def active_services(self, agency: str, day: date) -> set[str]:
        """Services running that day. If the day is outside the feed's dates, match by weekday."""
        calendar = self.calendars[agency]
        stamp = day.strftime("%Y%m%d")
        in_range = (calendar["start_date"] <= stamp) & (calendar["end_date"] >= stamp)
        if not in_range.any():
            in_range = pd.Series(True, index=calendar.index)
        runs_today = calendar[WEEKDAYS[day.weekday()]].astype(int) == 1
        services = set(calendar.loc[in_range & runs_today, "service_id"])
        exceptions = self.calendar_dates[agency]
        today = exceptions[exceptions["date"] == stamp]
        services |= set(today.loc[today["exception_type"] == "1", "service_id"])
        services -= set(today.loc[today["exception_type"] == "2", "service_id"])
        return services

    def next_departures(self, stop_id: str, after: datetime, n: int = 3) -> list[Departure]:
        local = after.astimezone(ZoneInfo(LOCAL_TZ))
        agency = stop_id.split(":", 1)[0]
        midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
        after_seconds = (local - midnight).total_seconds()
        rows = self.departures[
            (self.departures["stop_id"] == stop_id)
            & (self.departures["seconds"] >= after_seconds)
            & (self.departures["service_id"].isin(self.active_services(agency, local.date())))
        ].nsmallest(n, "seconds")
        return [
            Departure(
                route_name=row.route_name, headsign=row.headsign,
                departs_at=midnight + timedelta(seconds=int(row.seconds)),
            )
            for row in rows.itertuples()
        ]


_transit_lock = threading.Lock()


@cache
def _load_transit() -> Transit:
    return Transit.load(get_settings().data_dir / "processed" / "gtfs")


def get_transit() -> Transit:
    """Schedules, loaded once per server process (see data_store.get_store)."""
    with _transit_lock:
        return _load_transit()
