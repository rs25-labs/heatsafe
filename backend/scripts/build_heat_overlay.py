"""Make the "ground heat" map layer from a Landsat thermal image near the demo date.

Landsat 8/9 Collection 2 Level-2 surface temperature, via the Microsoft Planetary Computer:
https://planetarycomputer.microsoft.com/dataset/landsat-c2-l2
Output: data/processed/overlay/heat.png and heat.json (bounds, date, scene id, °F range).
"""

import json
from datetime import timedelta

import numpy as np
import planetary_computer
import rasterio
from PIL import Image
from pystac_client import Client
from rasterio.warp import Resampling, reproject

from heatsafe.config import STUDY_BBOX, get_settings

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
SOURCE_URL = "https://planetarycomputer.microsoft.com/dataset/landsat-c2-l2"
SEARCH_DAYS = 10
MAX_CLOUD_PCT = 10
RANGE_F = (90.0, 130.0)
PIXEL_DEG = 0.0003  # about 30 m, Landsat's resolution

# Single-hue sequential ramp (light to dark orange-brown) for 90-130 °F
RAMP = np.array(
    [[255, 245, 235], [253, 208, 162], [253, 141, 60], [217, 72, 1], [127, 39, 4]],
    dtype=np.float32,
)


def dn_to_fahrenheit(dn: float | np.ndarray) -> float | np.ndarray:
    kelvin = dn * 0.00341802 + 149.0
    return (kelvin - 273.15) * 9 / 5 + 32


def colorize(fahrenheit: np.ndarray, valid: np.ndarray) -> np.ndarray:
    low, high = RANGE_F
    position = np.clip((fahrenheit - low) / (high - low), 0, 1) * (len(RAMP) - 1)
    index = np.minimum(position.astype(int), len(RAMP) - 2)
    t = (position - index)[..., None]
    rgb = RAMP[index] * (1 - t) + RAMP[index + 1] * t
    alpha = np.where(valid, 255, 0)[..., None]
    return np.concatenate([rgb, alpha], axis=-1).astype(np.uint8)


def main() -> None:
    settings = get_settings()
    if settings.demo_date is None:
        raise SystemExit("Set HEATSAFE_DEMO_DATE in .env first.")
    south, west, north, east = STUDY_BBOX
    start = settings.demo_date - timedelta(days=SEARCH_DAYS)
    end = settings.demo_date + timedelta(days=SEARCH_DAYS)

    catalog = Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)
    items = list(
        catalog.search(
            collections=["landsat-c2-l2"],
            bbox=[west, south, east, north],
            datetime=f"{start.isoformat()}/{end.isoformat()}",
            query={"eo:cloud_cover": {"lt": MAX_CLOUD_PCT}, "platform": {"in": ["landsat-8", "landsat-9"]}},
        ).items()
    )
    if not items:
        raise SystemExit("No clear Landsat scene within 10 days of the demo date.")
    item = min(items, key=lambda i: abs(i.datetime.date() - settings.demo_date))

    width = round((east - west) / PIXEL_DEG)
    height = round((north - south) / PIXEL_DEG)
    grid = np.zeros((height, width), dtype=np.float32)
    with rasterio.open(item.assets["lwir11"].href) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=grid,
            dst_transform=rasterio.transform.from_bounds(west, south, east, north, width, height),
            dst_crs="EPSG:4326",
            resampling=Resampling.bilinear,
            src_nodata=0,
            dst_nodata=0,
        )
    valid = grid > 0
    fahrenheit = np.where(valid, dn_to_fahrenheit(grid), np.nan)

    out = settings.data_dir / "processed" / "overlay"
    out.mkdir(parents=True, exist_ok=True)
    Image.fromarray(colorize(np.nan_to_num(fahrenheit), valid), "RGBA").save(out / "heat.png")
    meta = {
        "bounds": [west, south, east, north],
        "scene_id": item.id,
        "platform": item.properties["platform"],
        "acquired": item.datetime.date().isoformat(),
        "min_f": round(float(np.nanmin(fahrenheit)), 1),
        "max_f": round(float(np.nanmax(fahrenheit)), 1),
        "range_f": list(RANGE_F),
        "source_url": SOURCE_URL,
    }
    (out / "heat.json").write_text(json.dumps(meta, indent=2))
    print(meta)


if __name__ == "__main__":
    main()
