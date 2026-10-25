"""A tiny street grid (3 rows x 6 columns, 100 m blocks) in real UTM coordinates near OCSA.

Row 0 is the direct, sunny street. Row 1 is a parallel street in full shade, and the
cross streets are shaded too. Row 2 is sunny.
"""

import geopandas as gpd
import networkx as nx
import numpy as np
from pyproj import Transformer
from rasterio.transform import from_origin

from heatsafe.config import PROJECTED_CRS
from heatsafe.data_store import DataStore
from heatsafe.models import Amenity, LatLng

X0, Y0 = 417_000.0, 3_735_000.0
ROWS, COLS, BLOCK = 3, 6, 100.0
to_latlng = Transformer.from_crs(PROJECTED_CRS, "EPSG:4326", always_xy=True)


def node_id(row: int, col: int) -> int:
    return row * COLS + col


def latlng_at(x: float, y: float) -> LatLng:
    lon, lat = to_latlng.transform(x, y)
    return LatLng(lat=lat, lon=lon)


def node_latlng(row: int, col: int) -> LatLng:
    return latlng_at(X0 + BLOCK * col, Y0 + BLOCK * row)


def build_store(amenities: list[Amenity] | None = None) -> DataStore:
    graph = nx.MultiDiGraph(crs=PROJECTED_CRS)
    for row in range(ROWS):
        for col in range(COLS):
            graph.add_node(node_id(row, col), x=X0 + BLOCK * col, y=Y0 + BLOCK * row)
    for row in range(ROWS):
        for col in range(COLS):
            for d_row, d_col in ((0, 1), (1, 0)):
                r2, c2 = row + d_row, col + d_col
                if r2 < ROWS and c2 < COLS:
                    a, b = node_id(row, col), node_id(r2, c2)
                    graph.add_edge(a, b, 0, length=BLOCK)
                    graph.add_edge(b, a, 0, length=BLOCK)
    store = DataStore(
        graph=graph,
        amenities=amenities or [],
        tracts=gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"),
        heights=np.zeros((10, 10), dtype=np.float32),
        heights_transform=from_origin(X0, Y0 + 10, 1, 1),
    )
    store.sample_edges()
    return store


def sample_in_sun(store: DataStore) -> np.ndarray:
    """Row 0 and row 2 streets are in sun; row 1 and every cross street are shaded."""
    in_sun = np.zeros(len(store.sample_points), dtype=bool)
    for index, (u, v, _) in enumerate(store.edge_keys):
        same_row = u // COLS == v // COLS
        if same_row and u // COLS in (0, 2):
            in_sun[store.sample_edge_index == index] = True
    return in_sun
