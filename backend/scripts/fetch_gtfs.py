"""Download bus (OCTA) and train (Metrolink) schedules in GTFS format."""

import io
import zipfile

import httpx

from heatsafe.config import get_settings

# OCTA open data page: https://octa.net/about/about-octa/open-data
# Metrolink producer URL as listed in the Mobility Database (mdb-96)
FEEDS = {
    "octa": "https://www.octa.net/current/google_transit.zip",
    "metrolink": "https://metrolinktrains.com/globalassets/about/gtfs/gtfs.zip",
}
NEEDED = {
    "stops.txt", "stop_times.txt", "trips.txt", "routes.txt", "calendar.txt",
    "calendar_dates.txt",
}


def main() -> None:
    settings = get_settings()
    for agency, url in FEEDS.items():
        response = httpx.get(
            url, follow_redirects=True, timeout=120,
            headers={"User-Agent": "Mozilla/5.0 HeatSafeOC student project"},
        )
        response.raise_for_status()
        (settings.data_dir / "raw" / f"{agency}_gtfs.zip").write_bytes(response.content)
        out = settings.data_dir / "processed" / "gtfs" / agency
        out.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            names = {n.split("/")[-1]: n for n in archive.namelist()}
            for name in NEEDED & names.keys():
                (out / name).write_bytes(archive.read(names[name]))
            print(agency, sorted(NEEDED & names.keys()))


if __name__ == "__main__":
    main()
