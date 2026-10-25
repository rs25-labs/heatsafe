"""Build a 1 m raster of how tall things are (trees and buildings) above the ground.

Inputs in data/raw/:
- canopy/*.tif: Meta/WRI global 1 m canopy height map tiles
  https://dataforgood-fb-data.s3.amazonaws.com/forests/v1/alsgedi_global_v6_float/chm/
- buildings.parquet: Overture Maps building footprints (overturemaps download --type=building)

Output: data/processed/heights_dm.tif (uint16, decimeters, EPSG:32611).
The ground is treated as flat; central Santa Ana has very little slope.
"""

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds

from heatsafe.config import PROJECTED_CRS, STUDY_BBOX, get_settings

DEFAULT_BUILDING_HEIGHT_M = 6.0
# Vegetation lower than this (shrubs, hedges) does not shade a walker's head and shoulders.
MIN_CANOPY_M = 3.0
FLOOR_HEIGHT_M = 3.5


def building_heights(buildings: gpd.GeoDataFrame) -> tuple[np.ndarray, dict[str, int]]:
    measured = buildings["height"].astype("float64")
    from_floors = buildings["num_floors"].astype("float64") * FLOOR_HEIGHT_M
    heights = measured.fillna(from_floors).fillna(DEFAULT_BUILDING_HEIGHT_M)
    counts = {
        "measured": int(measured.notna().sum()),
        "from_floors": int((measured.isna() & from_floors.notna()).sum()),
        "default": int((measured.isna() & from_floors.isna()).sum()),
    }
    return heights.to_numpy(), counts


def main() -> None:
    settings = get_settings()
    raw = settings.data_dir / "raw"
    south, west, north, east = STUDY_BBOX
    left, bottom, right, top = transform_bounds("EPSG:4326", PROJECTED_CRS, west, south, east, north)
    left, bottom, right, top = np.floor(left), np.floor(bottom), np.ceil(right), np.ceil(top)
    width, height = int(right - left), int(top - bottom)
    transform = from_origin(left, top, 1.0, 1.0)

    canopy = np.zeros((height, width), dtype=np.float32)
    for tile in sorted((raw / "canopy").glob("*.tif")):
        with rasterio.open(tile) as src:
            part = np.zeros_like(canopy)
            reproject(
                source=rasterio.band(src, 1),
                destination=part,
                dst_transform=transform,
                dst_crs=PROJECTED_CRS,
                # Nearest keeps tree edges sharp; bilinear smeared canopy onto sidewalks.
                resampling=Resampling.nearest,
                src_nodata=255,
                dst_nodata=0,
            )
            canopy = np.maximum(canopy, part)

    canopy[canopy < MIN_CANOPY_M] = 0

    buildings = gpd.read_parquet(raw / "buildings.parquet").to_crs(PROJECTED_CRS)
    heights_m, counts = building_heights(buildings)
    order = np.argsort(heights_m)  # taller buildings drawn last win overlaps
    building_raster = rasterize(
        ((buildings.geometry.iloc[i], heights_m[i]) for i in order),
        out_shape=(height, width),
        transform=transform,
        fill=0,
        dtype="float32",
    )
    print("building heights:", counts)

    combined_dm = np.round(np.maximum(canopy, building_raster) * 10).clip(0, 65535).astype("uint16")
    out = settings.data_dir / "processed" / "heights_dm.tif"
    with rasterio.open(
        out, "w", driver="GTiff", width=width, height=height, count=1, dtype="uint16",
        crs=PROJECTED_CRS, transform=transform, compress="deflate", tiled=True,
    ) as dst:
        dst.write(combined_dm, 1)
    # The server reads this copy (no rasterio needed at runtime).
    np.savez_compressed(
        settings.data_dir / "processed" / "heights_dm.npz",
        heights_dm=combined_dm, transform=np.array(list(transform)[:6], dtype=np.float64),
    )
    print(f"{width}x{height} px; {np.mean(combined_dm > 20) * 100:.1f}% of pixels taller than 2 m")


if __name__ == "__main__":
    main()
