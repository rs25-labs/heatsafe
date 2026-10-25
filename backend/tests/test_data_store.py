import osmnx as ox
import pytest
from pyproj import Transformer

from heatsafe.config import PRESETS, PROJECTED_CRS
from heatsafe.data_store import get_store

KNOWN_KINDS = {"drinking_water", "library", "cooling_center", "store", "pharmacy", "park"}
to_projected = Transformer.from_crs("EPSG:4326", PROJECTED_CRS, always_xy=True)


@pytest.mark.parametrize("preset", ["ocsa", "sartc"])
def test_graph_covers_ocsa_and_station(preset: str) -> None:
    store = get_store()
    x, y = to_projected.transform(PRESETS[preset]["lon"], PRESETS[preset]["lat"])
    _, distance = ox.distance.nearest_nodes(store.graph, x, y, return_dist=True)
    assert distance < 60


def test_amenities_have_known_kinds() -> None:
    store = get_store()
    assert store.amenities
    assert {a.kind for a in store.amenities} <= KNOWN_KINDS


def test_cooling_centers_have_sources() -> None:
    centers = [a for a in get_store().amenities if a.kind == "cooling_center"]
    assert centers
    assert all(a.source.startswith("https://") for a in centers)


def test_simultaneous_requests_load_the_data_only_once() -> None:
    import threading

    from heatsafe import data_store

    data_store.get_store.cache_clear()
    threads = [threading.Thread(target=data_store.get_store) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert data_store.get_store.cache_info().misses == 1
