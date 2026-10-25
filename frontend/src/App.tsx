import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, getConfig, getPresets, getTimeline, planTrip, warmServer } from "./api";
import ConditionsBar from "./components/ConditionsBar";
import Dialog from "./components/Dialog";
import HeatToggle, { type HeatMeta } from "./components/HeatToggle";
import HowRated from "./components/HowRated";
import LanguageToggle from "./components/LanguageToggle";
import MapView, { type Basemap, type HeatOverlay } from "./components/MapView";
import NoSafeRoute from "./components/NoSafeRoute";
import RouteCard from "./components/RouteCard";
import StreetWalk3D from "./components/StreetWalk3D";
import TimeBar from "./components/TimeBar";
import TripForm, { type Place, type TripFormValues } from "./components/TripForm";
import WalkPlayer, { type Speed } from "./components/WalkPlayer";
import WhyPanel from "./components/WhyPanel";
import { useLang, useT } from "./i18n";
import { pointAtDistance } from "./lib/routeGeometry";
import { clockTime, formatDate, formatTime } from "./lib/time";
import type { AmenityOnRoute, Preset, Route, TimelineSlot, TripResponse } from "./types";

const GOOGLE_KEY = (import.meta.env.VITE_GOOGLE_MAPS_KEY as string | undefined) ?? "";
const MAPTILER_KEY = import.meta.env.VITE_MAPTILER_KEY as string | undefined;
const LATEST_CLOCK = "20:00";
const DATA_SOURCES = [
  { name: "OpenStreetMap contributors", url: "https://www.openstreetmap.org/copyright" },
  { name: "Overture Maps", url: "https://overturemaps.org/" },
  { name: "Meta & WRI canopy heights (CC BY 4.0)", url: "https://sustainability.atmeta.com/blog/2024/04/22/using-artificial-intelligence-to-map-the-earths-forests/" },
  { name: "Open-Meteo", url: "https://open-meteo.com/" },
  { name: "Landsat 9 (USGS)", url: "https://planetarycomputer.microsoft.com/dataset/landsat-c2-l2" },
  { name: "CalEnviroScreen 5.0 (OEHHA)", url: "https://data.ca.gov/dataset/calenviroscreen-5-0" },
  { name: "OCTA", url: "https://octa.net/about/about-octa/open-data" },
  { name: "Metrolink", url: "https://metrolinktrains.com/" },
  { name: "MapTiler", url: "https://www.maptiler.com/copyright/" },
  { name: "Google 3D Tiles", url: "https://cloud.google.com/maps-platform/terms" },
];
const overlayBox = "rounded-md border border-rule bg-paper/95 shadow-sm";

type DialogName = "why" | "how" | "sources" | null;

function uniquePlaces(routes: Route[]): AmenityOnRoute[] {
  const seen = new Map<string, AmenityOnRoute>();
  for (const route of routes) {
    for (const place of route.amenities) {
      const key = `${place.amenity.kind}:${place.amenity.location.lat.toFixed(5)},${place.amenity.location.lon.toFixed(5)}`;
      if (!seen.has(key)) seen.set(key, place);
    }
  }
  return [...seen.values()];
}

export default function App() {
  const t = useT();
  const [lang] = useLang();
  const [presets, setPresets] = useState<Preset[]>([]);
  const [demoDate, setDemoDate] = useState<string | null>(null);
  const [start, setStart] = useState<Place | null>(null);
  const [end, setEnd] = useState<Place | null>(null);
  const [picking, setPicking] = useState<"start" | "end" | null>(null);
  const [trip, setTrip] = useState<TripResponse | null>(null);
  const [editing, setEditing] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [slow, setSlow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [basemap, setBasemap] = useState<Basemap>("street");
  const [heatMeta, setHeatMeta] = useState<HeatMeta | null>(null);
  const [showHeat, setShowHeat] = useState(false);
  const [timeline, setTimeline] = useState<TimelineSlot[] | null>(null);
  const [timelineError, setTimelineError] = useState<string | null>(null);
  const [slotIndex, setSlotIndex] = useState(0);
  const [departure, setDeparture] = useState(() => new Date().toISOString());
  const [walking, setWalking] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [walkMeters, setWalkMeters] = useState(0);
  const [speed, setSpeed] = useState<Speed>(20);
  const [dialog, setDialog] = useState<DialogName>(null);
  const [cityLoaded, setCityLoaded] = useState(false);
  const [used3D, setUsed3D] = useState(false);
  const [playWhenReady, setPlayWhenReady] = useState(false);

  useEffect(() => {
    const warm = warmServer();
    // While a sleeping server wakes up, these can fail; try once more after the wake-up call returns.
    // While a sleeping server wakes up, these can fail; keep trying for a few seconds.
    const pause = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));
    const loadPresets = (tries: number): Promise<void> =>
      getPresets()
        .then((p) => { setPresets(p); setError(null); })
        .catch(() => (tries > 1 ? warm.then(() => pause(1500)).then(() => loadPresets(tries - 1)) : setError(t("error.network"))));
    const loadConfig = (tries: number): Promise<void> =>
      getConfig()
        .then((c) => setDemoDate(c.demo_date))
        .catch(() => (tries > 1 ? warm.then(() => pause(1500)).then(() => loadConfig(tries - 1)) : undefined));
    void loadPresets(4);
    void loadConfig(4);
    fetch("/overlay/heat.json")
      .then((r) => (r.ok ? (r.json() as Promise<HeatMeta>) : null))
      .then(setHeatMeta)
      .catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function submit(values: TripFormValues) {
    if (!start || !end) return;
    setLoading(true);
    setError(null);
    // A server that has been idle takes a few seconds to wake up; say so instead of looking stuck.
    const slowTimer = window.setTimeout(() => setSlow(true), 3000);
    try {
      const result = await planTrip({
        start: start.location, end: end.location, depart_at: values.departAt,
        catch_at: values.catchAt, note: values.note || null, lang,
      });
      setTrip(result);
      setEditing(false);
      setSelectedId(result.recommendation.route_id);
      setWalking(false);
      setPlaying(false);
      setWalkMeters(0);
      setTimeline(null);
      setTimelineError(null);
      setSlotIndex(0);
      const startClock = clockTime(result.depart_at);
      getTimeline(result.trip_id, startClock, startClock > LATEST_CLOCK ? startClock : LATEST_CLOCK)
        .then(setTimeline)
        .catch((e) => setTimelineError(e instanceof ApiError ? e.message : t("error.network")));
    } catch (e) {
      setError(e instanceof ApiError && e.message !== "network" ? e.message : t("error.network"));
    } finally {
      window.clearTimeout(slowTimer);
      setSlow(false);
      setLoading(false);
    }
  }

  const slot = timeline && slotIndex > 0 ? timeline[slotIndex] : null;
  // Most shaded first, most exposed last; ordered at the departure time so cards don't jump around.
  const routes: Route[] = useMemo(
    () =>
      [...(trip?.routes ?? [])].sort((a, b) => b.shade_pct - a.shade_pct || a.sun_minutes - b.sun_minutes).map((route) => {
        const later = slot?.routes.find((r) => r.route_id === route.id);
        return later ? { ...route, ...later, id: route.id } : route;
      }),
    [trip, slot],
  );
  const places = useMemo(() => uniquePlaces(trip?.routes ?? []), [trip]);
  const selected = routes.find((r) => r.id === selectedId) ?? null;
  const walker = selected && (walking || walkMeters > 0) ? pointAtDistance(selected.segments, walkMeters).point : null;
  const heatOverlay: HeatOverlay | null =
    showHeat && heatMeta ? { url: "/overlay/heat.png", bounds: heatMeta.bounds } : null;
  const can3D = Boolean(GOOGLE_KEY);
  const show3D = walking && can3D;
  const when = slot?.at ?? trip?.depart_at ?? departure;
  const showForm = !trip || editing;
  const onMeters = useCallback((m: number) => setWalkMeters(m), []);

  function selectRoute(id: string) {
    setSelectedId(id);
    setWalkMeters(0);
    setPlaying(false);
  }

  function startWalk() {
    if (!selected) return;
    setWalkMeters(0);
    setWalking(true);
    if (can3D && !cityLoaded) {
      // Wait for the 3D city before moving, or the view never settles enough to load.
      setUsed3D(true);
      setPlayWhenReady(true);
      setPlaying(false);
    } else {
      setPlaying(true);
    }
  }

  function cityReady() {
    setCityLoaded(true);
    if (playWhenReady) {
      setPlayWhenReady(false);
      setPlaying(true);
    }
  }

  const mapControls = (
    <div className={`${overlayBox} inline-flex text-sm`} role="group" aria-label={`${t("map.street")} / ${t("map.satellite")}`}>
      {(["street", "satellite"] as const).map((option) => (
        <button key={option} type="button" aria-pressed={basemap === option}
          disabled={!MAPTILER_KEY && option === "satellite"}
          onClick={() => setBasemap(option)}
          className="h-9 px-3 first:rounded-l-md aria-pressed:bg-ink aria-pressed:text-paper disabled:opacity-40">
          {t(option === "street" ? "map.street" : "map.satellite")}
        </button>
      ))}
      {heatMeta && (
        <button type="button" aria-pressed={showHeat} onClick={() => setShowHeat(!showHeat)}
          className="h-9 rounded-r-md px-3 aria-pressed:bg-ink aria-pressed:text-paper">
          {t("map.groundHeat")}
        </button>
      )}
    </div>
  );

  return (
    <div className="flex flex-col md:h-dvh">
      <header className="flex items-center justify-between gap-3 border-b border-rule px-4 py-2">
        <div className="flex flex-wrap items-center gap-x-3">
          {/* Back to an empty form, like any site's logo */}
          <a href="/" className="flex items-center gap-2 rounded-md text-[20px] font-bold tracking-[-0.01em]">
            <svg viewBox="0 0 32 32" aria-hidden="true" className="h-7 w-7 shrink-0">
              <rect width="32" height="32" rx="7" className="fill-accent" />
              <circle cx="21" cy="10" r="5" className="fill-sun" />
              <path d="M5 21a11 11 0 0 1 22 0z" className="fill-paper" />
              <path d="M16 21v5" className="stroke-paper" strokeWidth="2" strokeLinecap="round" />
            </svg>
            {t("app.title")}
          </a>
        </div>
        <div className="flex items-center gap-4">
          <a href="/guide.html" target="_blank" rel="noreferrer" className="text-sm text-accent underline">
            {t("links.docs")}
          </a>
          <LanguageToggle />
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        {/* Map side: stays in view while the panel changes */}
        {/* On phones the map takes more of the screen during a walk, so the 3D view isn't hidden behind the player. */}
        <section className={`sticky top-0 z-20 ${walking ? "h-[75dvh]" : "h-[48vh]"} shrink-0 border-b border-rule md:relative md:order-2 md:h-auto md:flex-1 md:border-b-0`}>
          {can3D && used3D && selected && trip && (
            <div className={`absolute inset-0 ${show3D ? "z-[1]" : "invisible"}`}>
              <StreetWalk3D route={selected} meters={walkMeters} when={when} apiKey={GOOGLE_KEY}
                active={show3D} moving={playing} onReady={cityReady} />
            </div>
          )}
          {!show3D && (
            <MapView
              className="h-full"
              routes={routes} selectedId={selectedId} hoverId={hoverId}
              start={start?.location ?? null} end={end?.location ?? null} walker={walker}
              follow={walking} places={places} basemap={basemap} heatOverlay={heatOverlay} fitKey={trip?.trip_id}
              onSelectRoute={selectRoute} onHoverRoute={setHoverId}
              onMapClick={picking ? (point) => {
                const place = { key: `picked:${point.lat.toFixed(4)},${point.lon.toFixed(4)}`, label: `${t("form.picked")} (${point.lat.toFixed(4)}, ${point.lon.toFixed(4)})`, location: point };
                if (picking === "start") setStart(place);
                else setEnd(place);
                setPicking(null);
              } : undefined}
            />
          )}

          {!show3D && (
            <div className="absolute left-3 top-3 z-10 space-y-2">
              {mapControls}
              <ConditionsBar at={when} />
            </div>
          )}
          {trip && !walking && (
            <p className={`${overlayBox} absolute left-1/2 top-3 z-10 hidden -translate-x-1/2 px-3 py-1.5 text-sm lg:block`}>
              {t("map.hint")}
            </p>
          )}

          {show3D && selected && (
            <div className="absolute bottom-[168px] right-3 z-10 h-[96px] w-[128px] md:h-[180px] md:w-[240px] overflow-hidden rounded-md border-2 border-paper shadow-md">
              <MapView inset className="h-full" routes={[selected]} selectedId={selected.id}
                start={start?.location ?? null} end={end?.location ?? null} walker={walker} fitKey={`${trip?.trip_id}-${selected.id}`} />
              <p className="pointer-events-none absolute left-2 top-2 rounded bg-paper/90 px-1.5 text-xs font-medium">{t("player.inset")}</p>
            </div>
          )}

          <div className="absolute inset-x-3 bottom-3 z-10 space-y-2">
            {!walking && showHeat && heatMeta && <div className={`${overlayBox} inline-block px-3 py-2 text-xs`}><HeatToggle meta={heatMeta} /></div>}
            {!walking && (
              <div className={`${overlayBox} hidden gap-4 px-3 py-1.5 text-sm md:inline-flex`}>
                <span className="inline-flex items-center gap-1.5">
                  <span aria-hidden="true" className="inline-block h-1.5 w-6 rounded-full bg-accent" />
                  {t("map.legendShade")}
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span aria-hidden="true" className="inline-block h-1.5 w-6 rounded-full bg-sun" />
                  {t("map.legendSun")}
                </span>
              </div>
            )}
            {trip && (
              <div className={`${overlayBox} px-4 py-3`}>
                {walking && selected ? (
                  <WalkPlayer route={selected} meters={walkMeters} playing={playing} speed={speed} onSpeed={setSpeed}
                    onMeters={onMeters} onPlaying={setPlaying}
                    onDone={() => { setWalking(false); setPlaying(false); }} />
                ) : (
                  <TimeBar timeline={timeline} error={timelineError} index={slotIndex} onIndex={setSlotIndex} />
                )}
              </div>
            )}
          </div>
        </section>

        {/* Panel side: the form, then the results in the same place */}
        <aside className="md:order-1 md:w-[400px] md:shrink-0 md:overflow-y-auto md:border-r md:border-rule">
          <div className="space-y-4 p-4">
            <div className={showForm ? "" : "hidden"}>
              <h1 className="text-[28px] font-bold leading-[1.2] tracking-[-0.015em]">{t("form.planTitle")}</h1>
              <p className="mt-1 text-muted">{t("form.planSentence")}</p>
              <div className="mt-4">
                <TripForm
                  presets={presets} demoDate={demoDate} start={start} end={end} picking={picking}
                  loading={loading} loadingLabel={slow ? t("form.waking") : undefined} error={error} onDepartureChange={setDeparture}
                  onPlace={(field, place) => (field === "start" ? setStart(place) : setEnd(place))}
                  onPick={setPicking}
                  onSubmit={(values) => void submit(values)}
                />
              </div>
            </div>

            {trip && !showForm && (
              <>
                <div className="flex items-start justify-between gap-3 border-b border-rule pb-3">
                  <p className="text-sm">
                    <span className="font-semibold">{start?.label} → {end?.label}</span>
                    <br />
                    <span className="text-muted">{formatDate(trip.depart_at.slice(0, 10), lang)} · {formatTime(trip.depart_at, lang)}</span>
                  </p>
                  <button type="button" onClick={() => setEditing(true)}
                    className="h-9 shrink-0 rounded-md border border-control-soft px-3 text-sm hover:border-subtle">
                    {t("trip.edit")}
                  </button>
                </div>

                {trip.all_extreme && trip.alternatives && slot === null && (
                  <NoSafeRoute alternatives={trip.alternatives}
                    onLeaveAt={(iso) => {
                      const index = timeline?.findIndex((s) => new Date(s.at).getTime() === new Date(iso).getTime()) ?? -1;
                      if (index >= 0) setSlotIndex(index);
                    }} />
                )}

                <section aria-labelledby="compare-title" className="space-y-2">
                  <div className="flex items-baseline justify-between gap-3">
                    <h2 id="compare-title" className="text-sm font-semibold text-muted">{t("results.compare")}</h2>
                    <button type="button" onClick={() => setDialog("why")} className="text-sm text-accent underline">
                      {t("links.why")}
                    </button>
                  </div>
                  {slot && (
                    <p className="text-[13px] text-muted">{t("later.recommendationFor", { time: formatTime(trip.depart_at, lang) })}</p>
                  )}
                  {routes.map((route) => (
                    <RouteCard key={route.id} route={route}
                      base={slot ? trip.routes.find((r) => r.id === route.id) : undefined}
                      recommended={route.id === trip.recommendation.route_id}
                      reason={route.id === trip.recommendation.route_id ? trip.recommendation : undefined}
                      selected={route.id === selectedId} hovered={route.id === hoverId}
                      onSelect={() => selectRoute(route.id)}
                      onHover={(on) => setHoverId(on ? route.id : null)} />
                  ))}
                </section>

                {/* Stays in view at the bottom of the panel, whichever route card is picked. */}
                {selected && (
                  <div className="sticky bottom-0 z-10 -mx-4 border-t border-rule bg-paper px-4 pb-3 pt-3">
                    <button type="button" onClick={startWalk}
                      className="flex min-h-[48px] w-full items-center justify-center gap-2 rounded-md bg-accent px-4 font-medium text-paper hover:bg-accent-hover">
                      <svg viewBox="0 0 24 24" aria-hidden="true" className="h-4 w-4 fill-current"><path d="M7 4l13 8-13 8z" /></svg>
                      {t("player.play", { route: t(`route.${selected.label}`).toLowerCase() })}
                    </button>
                  </div>
                )}
              </>
            )}

            <footer className="border-t border-rule pt-3 text-[13px] leading-[1.6] text-muted">
              <p className="flex flex-wrap gap-x-4">
                <button type="button" onClick={() => setDialog("how")} className="text-accent underline">{t("links.how")}</button>
                <button type="button" onClick={() => setDialog("sources")} className="text-accent underline">{t("links.sources")}</button>
              </p>
              <p className="mt-1">{t("footer.built")}</p>
            </footer>
          </div>
        </aside>
      </div>

      <Dialog title={t("links.why")} open={dialog === "why"} onClose={() => setDialog(null)}>
        {trip && <WhyPanel trip={trip} />}
      </Dialog>
      <Dialog title={t("links.how")} open={dialog === "how"} onClose={() => setDialog(null)}>
        <HowRated />
      </Dialog>
      <Dialog title={t("links.sources")} open={dialog === "sources"} onClose={() => setDialog(null)}>
        <p className="text-sm">{t("footer.data")}</p>
        <ul className="mt-2 space-y-1 text-sm">
          {DATA_SOURCES.map((source) => (
            <li key={source.name}><a href={source.url} target="_blank" rel="noreferrer" className="text-accent underline">{source.name}</a></li>
          ))}
        </ul>
      </Dialog>
    </div>
  );
}
