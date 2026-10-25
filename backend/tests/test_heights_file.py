import rasterio
from pyproj import Transformer

from heatsafe.config import PRESETS, PROJECTED_CRS, get_settings


def test_heights_raster_shape_and_crs() -> None:
    path = get_settings().data_dir / "processed" / "heights_dm.tif"
    with rasterio.open(path) as raster:
        assert raster.crs.to_string() == PROJECTED_CRS
        assert raster.res == (1.0, 1.0)
        heights_m = raster.read(1) / 10
        assert 20 <= heights_m.max() <= 150
        x, y = Transformer.from_crs("EPSG:4326", PROJECTED_CRS, always_xy=True).transform(
            PRESETS["ocsa"]["lon"], PRESETS["ocsa"]["lat"]
        )
        row, col = raster.index(x, y)
        assert heights_m[row, col] < 30
