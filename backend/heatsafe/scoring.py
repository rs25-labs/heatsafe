"""Turn a path through the street network into a scored route people can compare."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise

import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString, Point

from heatsafe.config import PROJECTED_CRS, WALK_SPEED_MPS
from heatsafe.data_store import DataStore
from heatsafe.heat import effective_heat_index_f, exposure_level
from heatsafe.models import AmenityOnRoute, LatLng, Route, RouteLabel, Segment, Weather
from heatsafe.shade import EdgeKey

AMENITY_RADIUS_M = 40.0
MIN_SEGMENT_M = 10.0
SPARE_MINUTES_NEEDED = 2.0
# Crossing the street is only worth it for more than this much extra shade.
CROSSING_COST_M = 30.0
MIN_TURN_SIN = 0.34  # about 20 degrees
MAX_CORNER_M = 25.0

to_latlng = Transformer.from_crs(PROJECTED_CRS, "EPSG:4326", always_xy=True)
to_projected = Transformer.from_crs("EPSG:4326", PROJECTED_CRS, always_xy=True)


@dataclass
class Piece:
    start_m: float
    end_m: float
    in_sun: bool
    points: list[tuple[float, float]]

    @property
    def length_m(self) -> float:
        return self.end_m - self.start_m


def projected(point: LatLng | None) -> Point | None:
    return None if point is None else Point(to_projected.transform(point.lon, point.lat))


def as_latlng(x: float, y: float) -> LatLng:
    lon, lat = to_latlng.transform(x, y)
    return LatLng(lat=round(lat, 6), lon=round(lon, 6))


def is_corner(store: DataStore, node: int) -> bool:
    """Where three or more ways meet; anywhere else is partway along a block."""
    graph = store.graph
    return len(set(graph.predecessors(node)) | set(graph.successors(node))) >= 3


def choose_sidewalks(
    store: DataStore, path: list[EdgeKey], in_sun: np.ndarray,
    start: Point | None = None, end: Point | None = None,
) -> list[int]:
    """Which sidewalk to walk on each block, for the whole route at once.

    Least sun overall, but crossing the street counts as CROSSING_COST_M of extra sun,
    is only allowed at corners, and the walk begins and ends on the side nearest the
    start and end (starting across the street would mean crossing mid-block, so that
    costs double). Footpaths have one line and join either sidewalk freely.
    """
    variants = [store.edge_variants(key) for key in path]

    def sun_m(i: int, side: int) -> float:
        return float(in_sun[variants[i][side][1]].mean()) * store.edge_line(path[i]).length

    def far_side_cost(i: int, side: int, point: Point | None) -> float:
        if point is None or len(variants[i]) == 1:
            return 0.0
        nearest = min(range(len(variants[i])), key=lambda s: variants[i][s][0].distance(point))
        return 0.0 if side == nearest else 2 * CROSSING_COST_M

    def switch_cost(i: int, before: int, after: int) -> float:
        if before == after or len(variants[i - 1]) == 1 or len(variants[i]) == 1:
            return 0.0
        return CROSSING_COST_M if is_corner(store, path[i][0]) else float("inf")

    costs = [sun_m(0, side) + far_side_cost(0, side, start) for side in range(len(variants[0]))]
    came_from: list[list[int]] = []
    for i in range(1, len(path)):
        # Ties keep to the same sidewalk.
        best = [
            min(range(len(costs)), key=lambda b, s=side: (costs[b] + switch_cost(i, b, s), b != s))
            for side in range(len(variants[i]))
        ]
        costs = [costs[b] + switch_cost(i, b, side) + sun_m(i, side) for side, b in enumerate(best)]
        came_from.append(best)
    last = len(path) - 1
    side = min(range(len(costs)), key=lambda s: costs[s] + far_side_cost(last, s, end))
    sides = [side]
    for best in reversed(came_from):
        side = best[side]
        sides.append(side)
    return sides[::-1]


def sidewalk_corner(a: LineString, b: LineString) -> tuple[float, float] | None:
    """Where two sidewalks meet at a turn: the point their lines reach if extended.

    A sidewalk line ends level with the middle of the cross street, so joining the two
    ends directly would cut back into the street. None when the streets are nearly in
    line (the ends already meet) or the lines would only meet far away.
    """
    (x1, y1), (x2, y2) = a.coords[-2], a.coords[-1]
    (x3, y3), (x4, y4) = b.coords[0], b.coords[1]
    ax, ay, bx, by = x2 - x1, y2 - y1, x4 - x3, y4 - y3
    cross = ax * by - ay * bx
    if abs(cross) < MIN_TURN_SIN * np.hypot(ax, ay) * np.hypot(bx, by):
        return None
    t = ((x3 - x1) * by - (y3 - y1) * bx) / cross
    corner = (x1 + t * ax, y1 + t * ay)
    if max(np.hypot(corner[0] - x2, corner[1] - y2), np.hypot(corner[0] - x3, corner[1] - y3)) > MAX_CORNER_M:
        return None
    return corner


def sample_pieces(
    store: DataStore, path: list[EdgeKey], in_sun: np.ndarray,
    start: Point | None = None, end: Point | None = None,
) -> list[Piece]:
    """One piece per 5 m sample along the route, in walking order."""
    blocks: list[tuple[LineString, bool, list[Piece]]] = []
    walked = 0.0
    for key, side in zip(path, choose_sidewalks(store, path, in_sun, start, end), strict=True):
        length = store.edge_line(key).length
        variants = store.edge_variants(key)
        line, samples = variants[side]
        states = in_sun[samples]
        step = 1 / len(states)
        pieces = []
        for i, state in enumerate(states):
            a = line.interpolate(i * step, normalized=True)
            b = line.interpolate((i + 1) * step, normalized=True)
            pieces.append(
                Piece(walked + i * step * length, walked + (i + 1) * step * length, bool(state),
                      [a.coords[0], b.coords[0]])
            )
        blocks.append((line, len(variants) > 1, pieces))
        walked += length

    # Turn street corners where the sidewalks meet; distances stay those of the mapped streets.
    for (line_a, sidewalk_a, pieces_a), (line_b, sidewalk_b, pieces_b) in pairwise(blocks):
        corner = sidewalk_corner(line_a, line_b) if sidewalk_a and sidewalk_b else None
        if corner is None:
            continue
        reach_a, reach_b = line_a.project(Point(corner)), line_b.project(Point(corner))
        for piece in pieces_a:
            piece.points = [corner if line_a.project(Point(p)) > reach_a else p for p in piece.points]
        for piece in pieces_b:
            piece.points = [corner if line_b.project(Point(p)) < reach_b else p for p in piece.points]
        pieces_a[-1].points[-1] = corner
        pieces_b[0].points[0] = corner
    return [piece for _, _, pieces in blocks for piece in pieces]


def merge_same_state(pieces: list[Piece]) -> list[Piece]:
    merged: list[Piece] = []
    for piece in pieces:
        if merged and merged[-1].in_sun == piece.in_sun:
            merged[-1].end_m = piece.end_m
            merged[-1].points.extend(piece.points[1:])
        else:
            merged.append(Piece(piece.start_m, piece.end_m, piece.in_sun, list(piece.points)))
    return merged


def drop_short_runs(pieces: list[Piece]) -> list[Piece]:
    """Fold runs shorter than 10 m into their neighbor so the map isn't speckled."""
    runs = merge_same_state(pieces)
    for i, run in enumerate(runs):
        if run.length_m < MIN_SEGMENT_M and len(runs) > 1:
            neighbor = runs[i - 1] if i > 0 else runs[i + 1]
            run.in_sun = neighbor.in_sun
    return merge_same_state(runs)


def route_line(store: DataStore, path: list[EdgeKey]) -> LineString:
    coords: list[tuple[float, float]] = []
    for key in path:
        part = list(store.edge_line(key).coords)
        coords.extend(part if not coords else part[1:])
    return LineString(coords)


def amenities_on_route(store: DataStore, line: LineString) -> list[AmenityOnRoute]:
    found = []
    for amenity in store.amenities:
        point = Point(to_projected.transform(amenity.location.lon, amenity.location.lat))
        if line.distance(point) <= AMENITY_RADIUS_M:
            found.append(
                AmenityOnRoute(amenity=amenity, distance_along_m=round(line.project(point), 1))
            )
    return sorted(found, key=lambda a: a.distance_along_m)


def score_route(
    store: DataStore,
    path: list[EdgeKey],
    in_sun: np.ndarray,
    weather: Weather,
    depart_at: datetime,
    catch_at: datetime | None,
    route_id: str,
    label: RouteLabel,
    start: LatLng | None = None,
    end: LatLng | None = None,
) -> Route:
    pieces = sample_pieces(store, path, in_sun, projected(start), projected(end))
    runs = drop_short_runs(pieces)
    distance = sum(p.length_m for p in runs)
    sun_length = sum(p.length_m for p in runs if p.in_sun)
    sun_fraction = sun_length / distance if distance else 0.0
    # Rate the same rounded number people see, so the label always matches it
    effective = round(effective_heat_index_f(weather.heat_index_f, sun_fraction), 1)
    duration_s = distance / WALK_SPEED_MPS

    segments = [
        Segment(
            coords=[as_latlng(x, y) for x, y in run.points],
            length_m=round(run.length_m, 1),
            in_sun=run.in_sun,
            start_m=round(run.start_m, 1),
        )
        for run in runs
    ]

    arrives_in_time = None
    minutes_to_spare = None
    if catch_at is not None:
        spare = (catch_at - (depart_at + timedelta(seconds=duration_s))).total_seconds() / 60
        minutes_to_spare = round(spare, 1)
        arrives_in_time = round(spare, 2) >= SPARE_MINUTES_NEEDED

    return Route(
        id=route_id,
        label=label,
        distance_m=round(distance, 1),
        duration_min=round(duration_s / 60, 1),
        sun_minutes=round(sun_length / WALK_SPEED_MPS / 60, 1),
        shade_pct=round(100 * (1 - sun_fraction)),
        effective_heat_index_f=effective,
        exposure=exposure_level(effective),
        segments=segments,
        amenities=amenities_on_route(store, route_line(store, path)),
        arrives_in_time=arrives_in_time,
        minutes_to_spare=minutes_to_spare,
    )
