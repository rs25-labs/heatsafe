from datetime import datetime, timedelta
from itertools import pairwise
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from heatsafe.data_store import DataStore
from heatsafe.heat import ExposureLevel
from heatsafe.models import Amenity, Weather
from heatsafe.scoring import score_route, to_projected
from tests.synthetic import COLS, X0, Y0, build_store, latlng_at, node_id, sample_in_sun

LA = ZoneInfo("America/Los_Angeles")
DEPART = datetime(2026, 9, 9, 15, 30, tzinfo=LA)
WEATHER = Weather(
    temp_f=100, rel_humidity=40, heat_index_f=109.0, valid_at=DEPART,
    source="test", source_url="https://open-meteo.com/",
)
SUNNY_ROW = [(node_id(0, c), node_id(0, c + 1), 0) for c in range(COLS - 1)]


def score(path=SUNNY_ROW, amenities=None, catch_at=None):
    store = build_store(amenities)
    return score_route(
        store, path, sample_in_sun(store), WEATHER, DEPART, catch_at, "r1", "fastest"
    )


def test_card_numbers_match_segments() -> None:
    # One shaded edge with alternating 5 m sunny blips: each blip is folded into
    # its neighbor, so the card must report no sun, like the segments do.
    from tests.synthetic import node_id

    store = build_store()
    in_sun = np.zeros(len(store.sample_points), dtype=bool)
    sl = store.edge_samples((node_id(0, 2), node_id(0, 3), 0))
    in_sun[sl] = [(i % 2 == 0) for i in range(sl.stop - sl.start)]
    route = score_route(store, SUNNY_ROW, in_sun, WEATHER, DEPART, None, "r1", "fastest")
    sun_from_segments = sum(s.length_m for s in route.segments if s.in_sun) / 1.3 / 60
    assert route.sun_minutes == pytest.approx(sun_from_segments, abs=0.1)
    assert all(a.in_sun != b.in_sun for a, b in zip(route.segments, route.segments[1:]))


def test_sun_minutes_from_length() -> None:
    route = score()
    assert route.distance_m == pytest.approx(500)
    assert route.sun_minutes == pytest.approx(500 / 1.3 / 60, abs=0.05)
    assert route.shade_pct == 0
    assert route.exposure == ExposureLevel.extreme


def test_segments_alternate_and_cover_route() -> None:
    path = [(node_id(0, 0), node_id(1, 0), 0)] + [
        (node_id(1, c), node_id(1, c + 1), 0) for c in range(COLS - 1)
    ] + [(node_id(1, COLS - 1), node_id(0, COLS - 1), 0)]
    route = score(path)
    assert sum(s.length_m for s in route.segments) == pytest.approx(700, abs=1)
    assert all(a.in_sun != b.in_sun for a, b in zip(route.segments, route.segments[1:]))
    assert route.shade_pct == 100


def test_amenity_within_40m_included_beyond_excluded() -> None:
    near = Amenity(kind="drinking_water", name="Fountain", location=latlng_at(X0 + 250, Y0 + 30), source="t")
    far = Amenity(kind="library", name="Library", location=latlng_at(X0 + 250, Y0 + 60), source="t")
    route = score(amenities=[near, far])
    assert [a.amenity.name for a in route.amenities] == ["Fountain"]
    assert route.amenities[0].distance_along_m == pytest.approx(250, abs=1)


def test_arrives_in_time_with_two_minutes_to_spare() -> None:
    walk = timedelta(seconds=500 / 1.3)
    on_time = score(catch_at=DEPART + walk + timedelta(minutes=2))
    late = score(catch_at=DEPART + walk + timedelta(minutes=1))
    assert on_time.arrives_in_time is True
    assert on_time.minutes_to_spare == pytest.approx(2, abs=0.05)
    assert late.arrives_in_time is False
    assert score().arrives_in_time is None


def test_exposure_matches_the_rounded_number_shown() -> None:
    store = build_store()
    shaded_path = [(node_id(1, c), node_id(1, c + 1), 0) for c in range(COLS - 1)]
    weather = WEATHER.model_copy(update={"heat_index_f": 114.96})
    route = score_route(store, shaded_path, sample_in_sun(store), weather, DEPART, None, "r1", "shadiest")
    assert route.effective_heat_index_f == 115.0
    assert route.exposure == ExposureLevel.extreme


def test_streets_are_walked_on_the_shadier_sidewalk() -> None:
    store = build_store()
    for u, v, k in SUNNY_ROW:
        store.graph.edges[u, v, k]["highway"] = "residential"
    store.sample_edges()
    # Left sidewalk (north of an eastbound street) shaded, right sidewalk sunny.
    first_variant = store.edge_variant_start[store.sample_edge_index]
    in_sun = store.sample_variant_index != first_variant
    route = score_route(store, SUNNY_ROW, in_sun, WEATHER, DEPART, None, "r1", "shadiest")
    assert route.shade_pct == 100
    assert route.distance_m == pytest.approx(500)
    lat_center = latlng_at(X0 + 250, Y0).lat
    lat_walked = route.segments[0].coords[0].lat
    assert lat_walked > lat_center  # on the north sidewalk, not the center line



def residential_row() -> DataStore:
    store = build_store()
    for u, v, k in SUNNY_ROW:
        store.graph.edges[u, v, k]["highway"] = "residential"
    store.sample_edges()
    return store


def walked_points(route) -> list[tuple[float, float]]:
    return [to_projected.transform(c.lon, c.lat) for s in route.segments for c in s.coords]


def north_side(route) -> list[bool]:
    """For every point walked along SUNNY_ROW: True when it's on the north sidewalk."""
    return [y > Y0 for _, y in walked_points(route)]


def sun_by_side(store: DataStore, north_sunny: set[int], south_sunny: set[int]) -> np.ndarray:
    """Sun on each sidewalk of SUNNY_ROW, chosen per block (0 = first block)."""
    in_sun = np.zeros(len(store.sample_points), dtype=bool)
    for block, key in enumerate(SUNNY_ROW):
        north, south = store.edge_variants(key)  # left of an eastbound street is north
        in_sun[north[1]] = block in north_sunny
        in_sun[south[1]] = block in south_sunny
    return in_sun


def test_does_not_cross_the_street_for_a_little_shade() -> None:
    # Only 10 m of the first block is shadier across the street: not worth crossing twice.
    store = residential_row()
    in_sun = sun_by_side(store, north_sunny={0}, south_sunny={0, 1, 2, 3, 4})
    first_south = store.edge_variants(SUNNY_ROW[0])[1][1]
    in_sun[first_south.start:first_south.start + 2] = False
    route = score_route(store, SUNNY_ROW, in_sun, WEATHER, DEPART, None, "r1", "shadiest")
    assert set(north_side(route)) == {True}


def test_crosses_at_a_corner_when_the_shade_is_worth_it() -> None:
    store = residential_row()
    in_sun = sun_by_side(store, north_sunny={2, 3, 4}, south_sunny={0, 1})
    route = score_route(store, SUNNY_ROW, in_sun, WEATHER, DEPART, None, "r1", "shadiest")
    assert route.shade_pct == 100
    sides = north_side(route)
    assert sides[0] is True and sides[-1] is False


def test_never_crosses_in_the_middle_of_a_block() -> None:
    store = residential_row()
    # No cross street at column 2, so that node is just a point partway along the block.
    store.graph.remove_edge(node_id(0, 2), node_id(1, 2), 0)
    store.graph.remove_edge(node_id(1, 2), node_id(0, 2), 0)
    store.sample_edges()
    in_sun = sun_by_side(store, north_sunny={2, 3, 4}, south_sunny={0, 1})
    route = score_route(store, SUNNY_ROW, in_sun, WEATHER, DEPART, None, "r1", "shadiest")
    points = walked_points(route)
    switches = [b[0] for a, b in pairwise(points) if (a[1] > Y0) != (b[1] > Y0)]
    assert len(switches) == 1
    assert abs(switches[0] - (X0 + 200)) > 50


def test_starts_on_the_side_of_the_street_you_are_on() -> None:
    store = residential_row()
    in_sun = np.ones(len(store.sample_points), dtype=bool)  # no shade anywhere: sides tie
    route = score_route(store, SUNNY_ROW, in_sun, WEATHER, DEPART, None, "r1", "fastest",
                        start=latlng_at(X0, Y0 - 20), end=latlng_at(X0 + 500, Y0 - 20))
    assert set(north_side(route)) == {False}


def test_turning_a_corner_never_walks_backward() -> None:
    # East along row 0, then north up column 2: on either sidewalk, the line should go
    # around the corner without doubling back into the street.
    store = build_store()
    path = [(node_id(0, 0), node_id(0, 1), 0), (node_id(0, 1), node_id(0, 2), 0),
            (node_id(0, 2), node_id(1, 2), 0)]
    for key in path:
        store.graph.edges[key]["highway"] = "residential"
    store.sample_edges()
    for sunny_side in (0, 1):
        in_sun = np.zeros(len(store.sample_points), dtype=bool)
        for key in path:
            in_sun[store.edge_variants(key)[sunny_side][1]] = True
        route = score_route(store, path, in_sun, WEATHER, DEPART, None, "r1", "shadiest")
        xs, ys = zip(*walked_points(route), strict=True)
        assert all(b >= a - 0.2 for a, b in pairwise(xs))  # lat/lon rounding wobbles ~0.1 m
        assert all(b >= a - 0.2 for a, b in pairwise(ys))
