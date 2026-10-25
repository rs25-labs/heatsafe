import json
import threading
import zlib
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
from affine import Affine
from shapely.geometry import LineString

from heatsafe.config import get_settings
from heatsafe.models import Amenity, LatLng

SAMPLE_SPACING_M = 5.0
# Distance from a street's mapped center line to where people walk (about half the street).
SIDEWALK_OFFSET_M = {
    "living_street": 5.0, "residential": 6.0, "unclassified": 6.0,
    "tertiary": 7.0, "tertiary_link": 6.0, "secondary": 9.0, "secondary_link": 7.0,
    "primary": 11.0, "primary_link": 8.0,
}


@dataclass
class DataStore:
    graph: nx.MultiDiGraph
    amenities: list[Amenity]
    tracts: gpd.GeoDataFrame
    heights: np.ndarray  # meters above ground, 1 m pixels
    heights_transform: Affine
    version: str = ""  # changes whenever the street graph or height map is rebuilt
    edge_keys: list[tuple[int, int, int]] = field(default_factory=list)
    sample_points: np.ndarray = field(default_factory=lambda: np.empty((0, 2)))
    sample_edge_index: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=np.int64))
    edge_position: dict[tuple[int, int, int], int] = field(default_factory=dict)
    edge_sample_start: np.ndarray = field(default_factory=lambda: np.zeros(1, dtype=np.int64))
    # Each edge has one or more "variants": its own line, or for streets, the two sidewalks.
    variant_lines: list[LineString] = field(default_factory=list)
    variant_sample_start: np.ndarray = field(default_factory=lambda: np.zeros(1, dtype=np.int64))
    edge_variant_start: np.ndarray = field(default_factory=lambda: np.zeros(1, dtype=np.int64))
    sample_variant_index: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=np.int64))

    @classmethod
    def load(cls, data_dir: Path) -> "DataStore":
        processed = data_dir / "processed"
        graph = ox.load_graphml(processed / "walk_graph.graphml")
        with open(processed / "amenities.geojson") as f:
            features = json.load(f)["features"]
        amenities = [
            Amenity(
                kind=feature["properties"]["kind"],
                name=feature["properties"]["name"],
                location=LatLng(
                    lon=feature["geometry"]["coordinates"][0],
                    lat=feature["geometry"]["coordinates"][1],
                ),
                source=feature["properties"]["source"],
            )
            for feature in features
        ]
        tracts = gpd.read_file(processed / "tracts.geojson")
        # A plain NumPy copy of heights_dm.tif, so the server doesn't need rasterio.
        with np.load(processed / "heights_dm.npz") as packed:
            heights = packed["heights_dm"].astype(np.float32) / 10
            heights_transform = Affine(*packed["transform"].tolist())
        store = cls(
            graph=graph, amenities=amenities, tracts=tracts, heights=heights,
            heights_transform=heights_transform,
        )
        store.sample_edges()
        # Named by content, not file times, so shade files shipped with a deployment still match.
        checksum = 0
        for name in ("walk_graph.graphml", "heights_dm.npz"):
            checksum = zlib.crc32((processed / name).read_bytes(), checksum)
        store.version = f"{len(store.sample_points)}_{checksum:08x}"
        return store

    def edge_line(self, key: tuple[int, int, int]) -> LineString:
        u, v, k = key
        data = self.graph.edges[u, v, k]
        if "geometry" in data:
            return data["geometry"]
        nodes = self.graph.nodes
        return LineString([(nodes[u]["x"], nodes[u]["y"]), (nodes[v]["x"], nodes[v]["y"])])

    def walk_lines(self, key: tuple[int, int, int]) -> list[LineString]:
        """Where people actually walk: footpaths as mapped; streets on both sidewalks."""
        line = self.edge_line(key)
        highway = self.graph.edges[key].get("highway")
        highway = highway[0] if isinstance(highway, list) else highway
        offset = SIDEWALK_OFFSET_M.get(str(highway))
        if not offset or line.length < 1:
            return [line]
        sides = [line.offset_curve(offset), line.offset_curve(-offset)]
        if all(isinstance(side, LineString) and not side.is_empty for side in sides):
            return sides
        return [line]

    def sample_edges(self, spacing_m: float = SAMPLE_SPACING_M) -> None:
        """Points every 5 m along every place people walk, used to measure shade.

        Distances always follow the mapped line; sidewalk samples sit at the same
        fractions along their offset line, so both sides of a block line up.
        """
        self.edge_keys = list(self.graph.edges(keys=True))
        points: list[np.ndarray] = []
        edge_index: list[np.ndarray] = []
        variant_index: list[np.ndarray] = []
        self.variant_lines = []
        edge_variant_counts: list[int] = []
        for index, key in enumerate(self.edge_keys):
            center = self.edge_line(key)
            fractions = sample_offsets(center.length, spacing_m) / max(center.length, 1e-9)
            lines = self.walk_lines(key)
            for line in lines:
                coords = np.array([line.interpolate(f, normalized=True).coords[0] for f in fractions])
                points.append(coords)
                edge_index.append(np.full(len(coords), index))
                variant_index.append(np.full(len(coords), len(self.variant_lines)))
                self.variant_lines.append(line)
            edge_variant_counts.append(len(lines))
        self.sample_points = np.concatenate(points)
        self.sample_edge_index = np.concatenate(edge_index)
        self.sample_variant_index = np.concatenate(variant_index)
        self.edge_position = {key: index for index, key in enumerate(self.edge_keys)}
        self.variant_sample_start = np.concatenate([[0], np.cumsum([len(p) for p in points])])
        self.edge_variant_start = np.concatenate([[0], np.cumsum(edge_variant_counts)])
        self.edge_sample_start = self.variant_sample_start[self.edge_variant_start]

    def edge_samples(self, key: tuple[int, int, int]) -> slice:
        """All samples of an edge, every variant included."""
        index = self.edge_position[key]
        return slice(int(self.edge_sample_start[index]), int(self.edge_sample_start[index + 1]))

    def edge_variants(self, key: tuple[int, int, int]) -> list[tuple[LineString, slice]]:
        index = self.edge_position[key]
        first, last = int(self.edge_variant_start[index]), int(self.edge_variant_start[index + 1])
        return [
            (
                self.variant_lines[v],
                slice(int(self.variant_sample_start[v]), int(self.variant_sample_start[v + 1])),
            )
            for v in range(first, last)
        ]


def sample_offsets(length_m: float, spacing_m: float = 5.0) -> np.ndarray:
    count = max(1, round(length_m / spacing_m))
    return (np.arange(count) + 0.5) * (length_m / count)


_store_lock = threading.Lock()


@cache
def _load_store() -> DataStore:
    return DataStore.load(get_settings().data_dir)


def get_store() -> DataStore:
    """The data, loaded once per server process.

    Requests that arrive while it is loading wait for that one load. Loading a copy per
    request would multiply the ~0.9 GB it takes and crash the server (Vercel's limit is 2 GB).
    """
    with _store_lock:
        return _load_store()


get_store.cache_info = _load_store.cache_info  # type: ignore[attr-defined]
get_store.cache_clear = _load_store.cache_clear  # type: ignore[attr-defined]
