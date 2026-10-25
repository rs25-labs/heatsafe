from scripts.fetch_osm import drop_closed_places, load_closed_places


def test_closed_places_filter_drops_nearby_osm_amenity(tmp_path) -> None:
    closed_path = tmp_path / "closed_places.csv"
    closed_path.write_text(
        "name,lat,lon,reason,source_url,checked_on\n"
        "Santa Ana Public Library,33.751171,-117.873269,renovation,https://example.com/list.pdf,2026-10-23\n"
    )
    closed = load_closed_places(closed_path)
    near = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-117.873269, 33.751171]},
        "properties": {"kind": "library", "name": "Santa Ana Public Library"},
    }
    far = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-117.86, 33.75]},
        "properties": {"kind": "library", "name": "Other Library"},
    }
    assert drop_closed_places([near, far], closed) == [far]


def test_closed_places_filter_keeps_everything_when_list_empty() -> None:
    amenity = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-117.87, 33.75]},
        "properties": {"kind": "library", "name": "Santa Ana Public Library"},
    }
    assert drop_closed_places([amenity], []) == [amenity]
