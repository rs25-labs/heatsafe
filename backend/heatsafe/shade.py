"""Decide which points are in shade by "walking" from each point toward the sun.

A point is shaded when something between it and the sun (a building or tree in the
height raster) is taller than the sun's line of sight, or when it is under a canopy.
"""

import math
import os
import tempfile
from datetime import datetime, timedelta

import numpy as np
from affine import Affine

from heatsafe.config import PRESETS, SLOT_MINUTES, get_settings
from heatsafe.data_store import DataStore
from heatsafe.sun import SunPosition, sun_position

EdgeKey = tuple[int, int, int]

CANOPY_HEIGHT_M = 3.0
CHUNK_SIZE = 50_000


def heights_at(xy: np.ndarray, heights: np.ndarray, transform: Affine) -> np.ndarray:
    inverse = ~transform
    cols = np.floor(inverse.a * xy[..., 0] + inverse.b * xy[..., 1] + inverse.c).astype(np.int64)
    rows = np.floor(inverse.d * xy[..., 0] + inverse.e * xy[..., 1] + inverse.f).astype(np.int64)
    inside = (rows >= 0) & (rows < heights.shape[0]) & (cols >= 0) & (cols < heights.shape[1])
    values = np.zeros(rows.shape, dtype=np.float32)
    values[inside] = heights[rows[inside], cols[inside]]
    return values


def shaded_mask(
    points_xy: np.ndarray,
    heights: np.ndarray,
    transform: Affine,
    sun: SunPosition,
    eye_height_m: float = 1.5,
    max_distance_m: float = 300.0,
) -> np.ndarray:
    if sun.elevation_deg <= 0:
        return np.ones(len(points_xy), dtype=bool)

    slope = math.tan(math.radians(sun.elevation_deg))
    reach = (float(heights.max()) - eye_height_m) / slope
    steps = np.arange(1, int(min(max_distance_m, max(reach, 0.0))) + 1, dtype=np.float32)
    azimuth = math.radians(sun.azimuth_deg)
    direction = np.array([math.sin(azimuth), math.cos(azimuth)], dtype=np.float32)
    line_of_sight = eye_height_m + steps * slope

    result = np.empty(len(points_xy), dtype=bool)
    for start in range(0, len(points_xy), CHUNK_SIZE):
        chunk = points_xy[start : start + CHUNK_SIZE].astype(np.float32)
        under_canopy = heights_at(chunk, heights, transform) > CANOPY_HEIGHT_M
        if len(steps) == 0:
            result[start : start + len(chunk)] = under_canopy
            continue
        samples = chunk[:, None, :] + steps[None, :, None] * direction[None, None, :]
        blocked = (heights_at(samples, heights, transform) > line_of_sight[None, :]).any(axis=1)
        result[start : start + len(chunk)] = under_canopy | blocked
    return result


def slot_start(when: datetime) -> datetime:
    minutes = when.minute - when.minute % SLOT_MINUTES
    return when.replace(minute=minutes, second=0, microsecond=0)


def slot_after(when: datetime, slots: int) -> datetime:
    return slot_start(when) + timedelta(minutes=SLOT_MINUTES * slots)


def cache_name(store: DataStore, slot: datetime) -> str:
    return f"sun_{slot:%Y%m%d_%H%M}_{store.version}"


def load_cached_mask(store: DataStore, slot: datetime) -> np.ndarray | None:
    """Shade shipped with the app (packed bits, read-only) first, then the writable cache."""
    settings = get_settings()
    name = cache_name(store, slot)
    shipped = settings.data_dir / "processed" / "shade" / f"{name}.bits.npy"
    if shipped.exists():
        return np.unpackbits(np.load(shipped), count=len(store.sample_points)).astype(bool)
    cached = settings.cache_dir / f"{name}.npy"
    return np.load(cached) if cached.exists() else None


def sample_sun_mask(store: DataStore, when: datetime) -> np.ndarray:
    """For every 5 m sample point on the street network: is it in direct sun this slot?"""
    slot = slot_start(when)
    cached = load_cached_mask(store, slot)
    if cached is not None:
        return cached
    center = PRESETS["ocsa"]
    sun = sun_position(slot, float(center["lat"]), float(center["lon"]))
    in_sun = ~shaded_mask(store.sample_points, store.heights, store.heights_transform, sun)
    cache_dir = get_settings().cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    # mkstemp name must end in .npy: np.save appends ".npy" to anything else.
    # The leading dot keeps a crashed writer's leftover out of sun_*.npy globs.
    fd, tmp_name = tempfile.mkstemp(dir=cache_dir, prefix=".sun_tmp_", suffix=".npy")
    os.close(fd)
    try:
        np.save(tmp_name, in_sun)
        os.replace(tmp_name, cache_dir / f"{cache_name(store, slot)}.npy")
    except Exception:
        os.unlink(tmp_name)
        raise
    return in_sun


def fractions_from_mask(store: DataStore, in_sun: np.ndarray) -> dict[EdgeKey, float]:
    """Sun fraction per edge, on its shadier side when a street has two sidewalks."""
    variants = len(store.variant_lines)
    counts = np.bincount(store.sample_variant_index, minlength=variants)
    sunny = np.bincount(store.sample_variant_index, weights=in_sun.astype(np.float64), minlength=variants)
    per_variant = sunny / np.maximum(counts, 1)
    per_edge = np.minimum.reduceat(per_variant, store.edge_variant_start[:-1])
    return dict(zip(store.edge_keys, per_edge.tolist()))


def edge_sun_fractions(store: DataStore, when: datetime) -> dict[EdgeKey, float]:
    """Fraction of each street segment that is in direct sun during the 15-minute slot."""
    return fractions_from_mask(store, sample_sun_mask(store, when))


def path_sun_mask(store: DataStore, paths: list[list[EdgeKey]], when: datetime) -> np.ndarray:
    """Like sample_sun_mask, but only measures the samples on the given paths (fast)."""
    slot = slot_start(when)
    cached = load_cached_mask(store, slot)
    if cached is not None:
        return cached
    indexes = np.concatenate(
        [np.arange(len(store.sample_points))[store.edge_samples(key)] for path in paths for key in path]
    )
    center = PRESETS["ocsa"]
    sun = sun_position(slot, float(center["lat"]), float(center["lon"]))
    in_sun = np.zeros(len(store.sample_points), dtype=bool)
    in_sun[indexes] = ~shaded_mask(
        store.sample_points[indexes], store.heights, store.heights_transform, sun
    )
    return in_sun
