from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
from rasterio.transform import from_origin

import heatsafe.shade as shade_module
from heatsafe.config import Settings
from heatsafe.shade import sample_sun_mask, shaded_mask
from heatsafe.sun import SunPosition
from tests.synthetic import build_store

# 100 x 100 m raster, 1 m pixels, origin at (0, 100); a 10 m wall along x = 50
HEIGHTS = np.zeros((100, 100), dtype=np.float32)
HEIGHTS[:, 50] = 10.0
TRANSFORM = from_origin(0, 100, 1, 1)
LOW_EAST_SUN = SunPosition(azimuth_deg=90.0, elevation_deg=30.0)


def is_shaded(x: float, y: float, sun: SunPosition = LOW_EAST_SUN, heights=HEIGHTS) -> bool:
    return bool(shaded_mask(np.array([[x, y]]), heights, TRANSFORM, sun)[0])


def test_cache_write_is_atomic(monkeypatch, tmp_path) -> None:
    store = build_store()
    monkeypatch.setattr(
        shade_module, "get_settings", lambda: Settings(_env_file=None, data_dir=tmp_path)
    )

    def flaky_save(path: str, arr: np.ndarray) -> None:
        with open(path, "wb") as f:
            f.write(b"partial")
        raise OSError("disk blew up")

    monkeypatch.setattr(np, "save", flaky_save)
    when = datetime(2026, 9, 9, 15, 30, tzinfo=ZoneInfo("America/Los_Angeles"))
    try:
        sample_sun_mask(store, when)
    except OSError:
        pass
    else:
        raise AssertionError("expected OSError")
    assert list(tmp_path.glob("cache/sun_*.npy")) == []


def test_cache_file_round_trips(monkeypatch, tmp_path) -> None:
    store = build_store()
    monkeypatch.setattr(
        shade_module, "get_settings", lambda: Settings(_env_file=None, data_dir=tmp_path)
    )
    when = datetime(2026, 9, 9, 15, 30, tzinfo=ZoneInfo("America/Los_Angeles"))
    mask = sample_sun_mask(store, when)
    files = list(tmp_path.glob("cache/sun_*.npy"))
    assert len(files) == 1
    assert files[0].stat().st_size > 0
    assert np.array_equal(np.load(files[0]), mask)
    assert list(tmp_path.glob("cache/.sun_tmp_*.npy")) == []


def test_point_west_of_wall_shaded_when_sun_east_and_low() -> None:
    assert is_shaded(45.5, 50.5)


def test_point_east_of_wall_in_sun() -> None:
    assert not is_shaded(55.5, 50.5)


def test_point_far_from_wall_in_sun() -> None:
    assert not is_shaded(10.5, 50.5)


def test_under_canopy_is_shaded() -> None:
    heights = np.zeros((100, 100), dtype=np.float32)
    heights[20, 20] = 6.0
    assert is_shaded(20.5, 79.5, heights=heights)


def test_sun_below_horizon_all_shaded() -> None:
    points = np.array([[10.5, 10.5], [55.5, 50.5], [90.5, 90.5]])
    mask = shaded_mask(points, HEIGHTS, TRANSFORM, SunPosition(azimuth_deg=270, elevation_deg=-5))
    assert mask.all()


def test_edge_sun_fractions_cover_every_edge() -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from heatsafe.data_store import get_store
    from heatsafe.shade import edge_sun_fractions

    store = get_store()
    when = datetime(2026, 9, 5, 15, 30, tzinfo=ZoneInfo("America/Los_Angeles"))
    fractions = edge_sun_fractions(store, when)
    assert set(fractions) == set(store.graph.edges(keys=True))
    values = np.array(list(fractions.values()))
    assert ((values >= 0) & (values <= 1)).all()
    assert 0.2 < values.mean() < 0.95
