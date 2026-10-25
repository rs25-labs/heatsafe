"""Find a few genuinely different walking routes, from fastest to shadiest.

Each route is the shortest path when sunny streets "cost" extra: a sun penalty of 0 gives
the fastest route, and bigger penalties give routes that trade distance for shade.
"""

from itertools import pairwise

import networkx as nx
import osmnx as ox
from pyproj import Transformer

from heatsafe.config import PROJECTED_CRS
from heatsafe.models import LatLng
from heatsafe.shade import EdgeKey

SUN_PENALTIES = [0, 2, 5, 10]
MAX_OVERLAP = 0.8
MAX_DETOUR = 1.6

to_projected = Transformer.from_crs("EPSG:4326", PROJECTED_CRS, always_xy=True)


def nearest_node(graph: nx.MultiDiGraph, point: LatLng) -> tuple[int, float]:
    x, y = to_projected.transform(point.lon, point.lat)
    node, distance = ox.distance.nearest_nodes(graph, x, y, return_dist=True)
    return int(node), float(distance)


def path_length(graph: nx.MultiDiGraph, path: list[EdgeKey]) -> float:
    return sum(graph.edges[u, v, k]["length"] for u, v, k in path)


def overlap(graph: nx.MultiDiGraph, a: list[EdgeKey], b: list[EdgeKey]) -> float:
    """Share of the shorter path's length that is also on the other path."""
    a_edges = {frozenset((u, v)): graph.edges[u, v, k]["length"] for u, v, k in a}
    b_edges = {frozenset((u, v)): graph.edges[u, v, k]["length"] for u, v, k in b}
    shared = sum(length for edge, length in a_edges.items() if edge in b_edges)
    return shared / max(min(sum(a_edges.values()), sum(b_edges.values())), 1e-9)


def best_path(
    graph: nx.MultiDiGraph, source: int, target: int,
    sun_fraction: dict[EdgeKey, float], penalty: float,
) -> list[EdgeKey]:
    def cost(u: int, v: int, k: int) -> float:
        return graph.edges[u, v, k]["length"] * (1 + penalty * sun_fraction.get((u, v, k), 1.0))

    def weight(u: int, v: int, data: dict) -> float:
        return min(cost(u, v, k) for k in data)

    nodes = nx.shortest_path(graph, source, target, weight=weight)
    return [
        (u, v, min(graph[u][v], key=lambda k, u=u, v=v: cost(u, v, k)))
        for u, v in pairwise(nodes)
    ]


def candidate_paths(
    graph: nx.MultiDiGraph, start: LatLng, end: LatLng, sun_fraction: dict[EdgeKey, float]
) -> list[list[EdgeKey]]:
    source, _ = nearest_node(graph, start)
    target, _ = nearest_node(graph, end)
    kept: list[list[EdgeKey]] = []
    for penalty in SUN_PENALTIES:
        try:
            path = best_path(graph, source, target, sun_fraction, penalty)
        except nx.NetworkXNoPath:
            return []
        if not path:
            continue
        if kept and path_length(graph, path) > MAX_DETOUR * path_length(graph, kept[0]):
            continue
        if any(overlap(graph, path, other) >= MAX_OVERLAP for other in kept):
            continue
        kept.append(path)
    return kept
