from datetime import date
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]

# (south, west, north, east) in WGS84: central Santa Ana
STUDY_BBOX = (33.720, -117.900, 33.780, -117.830)
PROJECTED_CRS = "EPSG:32611"
LOCAL_TZ = "America/Los_Angeles"
WALK_SPEED_MPS = 1.3
SLOT_MINUTES = 15


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", extra="ignore", populate_by_name=True
    )

    openrouter_api_key: str | None = Field(default=None, validation_alias="OPENROUTER_API_KEY")
    model: str | None = Field(default=None, validation_alias="HEATSAFE_MODEL")
    demo_date: date | None = Field(default=None, validation_alias="HEATSAFE_DEMO_DATE")
    data_dir: Path = Field(default=REPO_ROOT / "data", validation_alias="HEATSAFE_DATA_DIR")
    # Must be writable; on Vercel only /tmp is.
    cache_dir_override: Path | None = Field(default=None, validation_alias="HEATSAFE_CACHE_DIR")
    # Dev-only "temp_f,humidity" override used to preview the no-safe-route screen
    force_weather: str | None = Field(default=None, validation_alias="HEATSAFE_FORCE_WEATHER")

    @property
    def cache_dir(self) -> Path:
        return self.cache_dir_override or self.data_dir / "cache"


def get_settings() -> Settings:
    return Settings()

# Geocoded once from OpenStreetMap Nominatim (2026-10-23)
PRESETS: dict[str, dict[str, object]] = {
    "ocsa": {
        "name": "Orange County School of the Arts",
        "lat": 33.75361,
        "lon": -117.86771,
    },
    "sartc": {
        "name": "Santa Ana Regional Transportation Center",
        "lat": 33.75161,
        "lon": -117.85647,
    },
    # High schools in the study area, geocoded the same way from their OSM street
    # addresses (Santa Ana High has none in OSM, so by name).
    "santa-ana-high": {"name": "Santa Ana High School", "lat": 33.74241, "lon": -117.87354},
    "century-high": {"name": "Century High School", "lat": 33.72945, "lon": -117.84777},
    "valley-high": {"name": "Valley High School", "lat": 33.72388, "lon": -117.89773},
    "mater-dei": {"name": "Mater Dei High School", "lat": 33.72603, "lon": -117.88376},
    "legacy-prep": {"name": "Legacy College Prep", "lat": 33.75959, "lon": -117.84773},
    # The bus stops served by the most OCTA routes in the study area (OCTA GTFS,
    # data/raw/octa_gtfs.zip): the middle of each intersection's stops.
    "stop-17th-bristol": {"name": "Bus stops: 17th St & Bristol St", "lat": 33.75997, "lon": -117.88512},
    "stop-17th-main": {"name": "Bus stops: 17th St & Main St", "lat": 33.76027, "lon": -117.86729},
    "stop-civic-main": {"name": "Bus stops: Civic Center Dr & Main St", "lat": 33.75089, "lon": -117.86747},
    "stop-1st-main": {"name": "Bus stops: 1st St & Main St", "lat": 33.74516, "lon": -117.86769},
    # Each high school's nearest stop with two or more routes, from the same GTFS.
    "stop-1st-ross": {"name": "Bus stops: 1st St & Ross St", "lat": 33.74547, "lon": -117.87251},
    "stop-edinger-grand": {"name": "Bus stops: Edinger Ave & Grand Ave", "lat": 33.72689, "lon": -117.85018},
    "stop-edinger-center": {"name": "Bus stops: Edinger Ave & Center St", "lat": 33.72741, "lon": -117.89817},
    "stop-bristol-edinger": {"name": "Bus stops: Bristol St & Edinger Ave", "lat": 33.72703, "lon": -117.88512},
    "stop-17th-grand": {"name": "Bus stops: 17th St & Grand Ave", "lat": 33.76015, "lon": -117.85212},
}
