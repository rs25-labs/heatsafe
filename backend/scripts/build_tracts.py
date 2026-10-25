"""Keep the CalEnviroScreen 5.0 census tracts that overlap the study area.

Source (data.ca.gov, released 2026-07-01):
https://data.ca.gov/dataset/calenviroscreen-5-0
"""

import geopandas as gpd
from shapely.geometry import box

from heatsafe.config import STUDY_BBOX, get_settings

CES_VERSION = "5.0"
SOURCE_URL = "https://data.ca.gov/dataset/calenviroscreen-5-0"

# Our name -> CalEnviroScreen 5.0 column (all are statewide percentiles, 0-100).
# CES 5.0 has no heat indicator; these are the vulnerability factors that make heat worse.
CES_FIELDS = {
    "ces_percentile": "CIscoreP",
    "pollution_burden_pct": "PollutionP",
    "pop_char_pct": "PopCharP",
    "asthma_pct": "asthmaP",
    "cardiovascular_pct": "cvdP",
    "poverty_pct": "povP",
    "linguistic_isolation_pct": "lingP",
    "housing_burden_pct": "housingBP",
}


def main() -> None:
    settings = get_settings()
    shp = next((settings.data_dir / "raw" / "ces").glob("*.shp"))
    tracts = gpd.read_file(shp).to_crs("EPSG:4326")
    south, west, north, east = STUDY_BBOX
    tracts = tracts[tracts.intersects(box(west, south, east, north))]

    out = gpd.GeoDataFrame(
        {
            "tract_id": tracts["tract"].astype("int64").astype(str).str.zfill(11),
            "ces_version": CES_VERSION,
            "source_url": SOURCE_URL,
            **{ours: tracts[theirs].where(tracts[theirs] >= 0) for ours, theirs in CES_FIELDS.items()},
        },
        geometry=tracts.geometry.values,
        crs="EPSG:4326",
    )
    out.to_file(settings.data_dir / "processed" / "tracts.geojson", driver="GeoJSON")
    print(f"{len(out)} tracts written")


if __name__ == "__main__":
    main()
