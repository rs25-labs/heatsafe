"""Build the walking network and useful places for the study area from OpenStreetMap.

Input: the Geofabrik Southern California extract, downloaded to data/raw/:
https://download.geofabrik.de/north-america/us/california/socal-latest.osm.pbf
(Public Overpass servers were too unreliable to use.)
"""

import csv
import json
import re
from pathlib import Path

import osmium
import osmnx as ox
from pyproj import Transformer
from shapely.geometry import MultiPoint

from heatsafe.config import PROJECTED_CRS, STUDY_BBOX, get_settings

# Same exclusions OSMnx uses for network_type="walk"
EXCLUDED_HIGHWAY = re.compile(
    "abandoned|bus_guideway|construction|cycleway|motor|no|planned|platform|proposed|raceway|razed"
)
STORE_SHOPS = {"supermarket", "convenience", "mall", "department_store"}
AMENITY_KINDS = {"drinking_water", "library", "pharmacy"}


def is_walkable(tags: osmium.osm.TagList) -> bool:
    highway = tags.get("highway")
    if highway is None or EXCLUDED_HIGHWAY.search(highway):
        return False
    if tags.get("area") == "yes" or tags.get("foot") == "no":
        return False
    return "private" not in tags.get("access", "") and "private" not in tags.get("service", "")


def kind_for(tags: osmium.osm.TagList) -> str | None:
    if tags.get("amenity") in AMENITY_KINDS:
        return tags.get("amenity")
    if tags.get("shop") in STORE_SHOPS:
        return "store"
    if tags.get("leisure") == "park":
        return "park"
    return None


def in_bbox(lat: float, lon: float, margin: float = 0.0) -> bool:
    south, west, north, east = STUDY_BBOX
    return (
        south - margin <= lat <= north + margin and west - margin <= lon <= east + margin
    )


def amenity_feature(kind: str, name: str, lon: float, lat: float, source: str) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {"kind": kind, "name": name, "source": source},
    }


CLOSED_RADIUS_M = 50.0
to_projected = Transformer.from_crs("EPSG:4326", PROJECTED_CRS, always_xy=True)


def load_closed_places(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def drop_closed_places(amenities: list[dict], closed: list[dict]) -> list[dict]:
    """Drop amenities within CLOSED_RADIUS_M of a hand-listed closed place."""
    closed_xy = [
        to_projected.transform(float(row["lon"]), float(row["lat"])) for row in closed
    ]
    kept = []
    for feature in amenities:
        lon, lat = feature["geometry"]["coordinates"]
        x, y = to_projected.transform(lon, lat)
        if any((x - cx) ** 2 + (y - cy) ** 2 <= CLOSED_RADIUS_M**2 for cx, cy in closed_xy):
            continue
        kept.append(feature)
    return kept


def main() -> None:
    settings = get_settings()
    raw = settings.data_dir / "raw"
    processed = settings.data_dir / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    pbf = raw / "socal-latest.osm.pbf"
    study_osm = raw / "study_area.osm"

    amenities: list[dict] = []
    processor = (
        osmium.FileProcessor(pbf)
        .with_locations()
        .with_filter(osmium.filter.KeyFilter("highway", "amenity", "shop", "leisure"))
    )
    with osmium.BackReferenceWriter(str(study_osm), ref_src=str(pbf), overwrite=True) as writer:
        for obj in processor:
            if obj.is_node():
                kind = kind_for(obj.tags)
                if kind and obj.location.valid() and in_bbox(obj.location.lat, obj.location.lon):
                    amenities.append(
                        amenity_feature(
                            kind, obj.tags.get("name", ""), obj.location.lon,
                            obj.location.lat, "OpenStreetMap",
                        )
                    )
            elif obj.is_way():
                points = [(n.lon, n.lat) for n in obj.nodes if n.location.valid()]
                if not points or not any(in_bbox(lat, lon, 0.002) for lon, lat in points):
                    continue
                if is_walkable(obj.tags):
                    writer.add_way(obj)
                kind = kind_for(obj.tags)
                if kind:
                    center = MultiPoint(points).centroid
                    if in_bbox(center.y, center.x):
                        amenities.append(
                            amenity_feature(
                                kind, obj.tags.get("name", ""), center.x, center.y,
                                "OpenStreetMap",
                            )
                        )

    # Walkers can use one-way streets in both directions
    graph = ox.graph_from_xml(study_osm, bidirectional=True, simplify=True, retain_all=False)
    south, west, north, east = STUDY_BBOX
    graph = ox.truncate.truncate_graph_bbox(graph, (west, south, east, north))
    graph = ox.truncate.largest_component(graph, strongly=True)
    graph = ox.project_graph(graph, to_crs=PROJECTED_CRS)
    ox.save_graphml(graph, processed / "walk_graph.graphml")
    print(f"walk graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges")

    closed = load_closed_places(settings.data_dir / "manual" / "closed_places.csv")
    amenities = drop_closed_places(amenities, closed)
    print(f"amenities after dropping {len(closed)} closed places: {len(amenities)}")

    with open(settings.data_dir / "manual" / "cooling_centers.csv", newline="") as f:
        for row in csv.DictReader(f):
            amenities.append(
                amenity_feature(
                    "cooling_center", row["name"], float(row["lon"]), float(row["lat"]),
                    row["source_url"],
                )
            )

    with open(processed / "amenities.geojson", "w") as f:
        json.dump({"type": "FeatureCollection", "features": amenities}, f)
    counts: dict[str, int] = {}
    for feature in amenities:
        kind = feature["properties"]["kind"]
        counts[kind] = counts.get(kind, 0) + 1
    print("amenities:", counts)


if __name__ == "__main__":
    main()
