# HeatSafe OC

**Find the safest way to walk through extreme heat.**

In summer and early fall 2026, Orange County had record heat. School lets out in the afternoon, close to the hottest part of the day, and many students then walk to a bus stop or the train station. A 20-minute walk feels short until it's 105°F with little shade.

HeatSafe compares real walking routes by how much of each one is **in shade at the time you'll walk it**, estimates how hot the walk will feel, shows what relief is along the way (water, libraries, cooling centers, parks), and recommends one route. It works in English and Spanish.

Built for the 2026 Congressional App Challenge (CA-46).

## How it works

### 1. Finding routes
The street and sidewalk network comes from OpenStreetMap. To find different routes, we search for the shortest path several times, each time making sunny streets "cost" more (a sun penalty of 0, 2, 5, then 10). A penalty of 0 gives the fastest route; bigger penalties give routes that trade a little distance for more shade. We keep only routes that are really different (less than 80% overlap) and no more than 1.6× as long as the fastest one.

### 2. Calculating shade
I built a 1-meter map of how tall everything is: buildings from Overture Maps (92% have measured heights; others use their floor count, or 6 m) and trees from the Meta/WRI canopy height map. For any time of day we calculate where the sun is in the sky. Then, for points every 5 meters along every street, we "walk" from the point toward the sun: if a building or tree is taller than the sun's line of sight, that point is in shade. Points under tree canopy count as shaded too. We treat the ground as flat, since central Santa Ana has very little slope.

### 3. Rating heat exposure
I get the temperature and humidity for that hour (Open-Meteo) and compute the National Weather Service **heat index**. The NWS says full sun can make it feel up to 15°F hotter, so each route's "feels like" temperature is:

> heat index + 15°F × (fraction of the walk in direct sun)

Then: under 90°F is **Low**, 90–103 **Moderate**, 103–115 **High**, and 115 and above **Extreme**. These are estimates, and the app labels them that way.

### 4. What the AI does (and doesn't do)
The AI gets the already-scored routes, the weather and the person's note ("carrying a cello, need the 3:52 train"). It **chooses** a route, which the app marks **Recommended**. It doesn't calculate anything. It also writes a short reason for its choice; the app doesn't show this, but uses it as a check: every number in it must match the data. If the AI uses a number we didn't give it, picks a route that doesn't exist, or is slow or unavailable, a simple rule picks instead (lowest exposure, then least time in the sun).

### 5. The ground heat satellite layer
Landsat 9 measures how hot the ground surface actually gets. We use a clear scene from September 14, 2026 and color it from 90°F (light) to 130°F (dark), so hot parking lots and cooler parks stand out. It is labeled with its own date.

### 6. "Walk it" and the 3D street view
The slider moves you along the chosen route, showing whether each stretch is in shade or sun, how far you've walked, and what's coming up. With a Google Maps key, a 3D view of the real buildings and trees follows along, with shadows drawn for the trip's date and time.

### 7. When no route is safe
If every route is Extreme, the app says so plainly and offers to leave later (the time when a route first drops below Extreme), nearby cool places, and the next buses. It also lists the warning signs of heat illness.

## Data sources

| What | Source | Date |
|---|---|---|
| Streets, sidewalks, water fountains, libraries, stores, parks | [OpenStreetMap](https://www.openstreetmap.org/) via the [Geofabrik](https://download.geofabrik.de/north-america/us/california.html) Southern California extract | Oct 23, 2026 |
| Building footprints and heights | [Overture Maps](https://overturemaps.org/) | 2026 release |
| Tree canopy heights | [Meta/WRI 1 m global canopy height map](https://sustainability.atmeta.com/blog/2024/04/22/using-artificial-intelligence-to-map-the-earths-forests/) | 2024 |
| Cooling centers | [Orange County cooling centers list](https://www.ocgov.com/sites/ocgov/files/2026-08/OC-Cooling-Centers-2026-English-REV20260825.pdf) | Aug 25, 2026 |
| Weather (temperature, humidity) | [Open-Meteo](https://open-meteo.com/) | live / historical |
| Ground surface temperature | [Landsat 9 Collection 2 Level-2](https://planetarycomputer.microsoft.com/dataset/landsat-c2-l2) (Microsoft Planetary Computer) | Sep 14, 2026 |
| Neighborhood vulnerability | [CalEnviroScreen 5.0](https://data.ca.gov/dataset/calenviroscreen-5-0) (OEHHA) | Jul 1, 2026 |
| Bus and train schedules | [OCTA GTFS](https://octa.net/about/about-octa/open-data), [Metrolink GTFS](https://metrolinktrains.com/) | 2026 |
| Heat illness signs | [CDC](https://www.cdc.gov/extreme-heat/warning-signs/) | |

## Running it

You need [uv](https://docs.astral.sh/uv/) (Python) and [pnpm](https://pnpm.io/) (Node).

1. Copy `.env.example` to `.env` and fill in:
   - AI route choice (optional; without it the simple rule picks):
     - `OPENROUTER_API_KEY`: your OpenRouter key.
     - `HEATSAFE_MODEL`: an OpenRouter model id from https://openrouter.ai/models (there is
       no default: without it the app logs a warning and uses the rule-based pick).
   - `VITE_MAPTILER_KEY`: map and satellite tiles (optional; without it, basic OpenStreetMap tiles)
   - `VITE_GOOGLE_MAPS_KEY`: Google Map Tiles API, for the 3D street view (optional)
   - `HEATSAFE_DEMO_DATE`: the day the "Use demo day" button replays (we use `2026-09-10`, the school day after the hottest afternoon of the year, when the shadiest route rates a level safer than the fastest)
2. The processed data is already in the repo (`data/processed/`). To rebuild it from scratch (downloads go to `data/raw/`): Download the [SoCal OSM extract](https://download.geofabrik.de/north-america/us/california/socal-latest.osm.pbf), the two canopy tiles and the CalEnviroScreen shapefile as described at the top of each script, then:
   ```bash
   cd backend
   uv run overturemaps download --bbox=-117.905,33.715,-117.825,33.785 -f geoparquet --type=building -o ../data/raw/buildings.parquet
   uv run python scripts/fetch_osm.py
   uv run python scripts/fetch_gtfs.py
   uv run python scripts/build_tracts.py
   uv run python scripts/build_heights.py
   uv run python -m scripts.build_heat_overlay
   PYTHONPATH=. uv run python scripts/bake_shade.py   # precomputed demo-day shade
   PYTHONPATH=. uv run python scripts/save_demo_weather.py   # demo-day weather, for when Open-Meteo is down
   ```
   The data-building tools are in the `data` dependency group; the server itself only needs `requirements.txt` (exported with `uv export --no-dev --no-default-groups --no-emit-project --no-hashes --format requirements-txt`).
3. Start the back end and the front end:
   ```bash
   cd backend && uv run uvicorn heatsafe.api:app --reload --port 8000
   cd frontend && pnpm install && pnpm dev
   ```
4. Open http://localhost:5173.

## Deploying to Vercel

The whole app is one Vercel project (see `vercel.json` and `docs/vercel-deployment-plan.md`): the website is built from `frontend/` and served as static files, and `api/index.py` runs the FastAPI back end as a Python Function. In the Vercel project settings, add `OPENROUTER_API_KEY`, `HEATSAFE_MODEL`, `HEATSAFE_DEMO_DATE`, `VITE_MAPTILER_KEY` and `VITE_GOOGLE_MAPS_KEY`. Restrict the two `VITE_` keys to the site's address, since they are visible in the browser.

## Tests

```bash
cd backend && uv run pytest && uv run ruff check heatsafe tests scripts
cd frontend && pnpm test && pnpm tsc -b
```
