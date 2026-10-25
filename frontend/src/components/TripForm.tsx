import { useEffect, useState, type FormEvent } from "react";
import { getStopsNear } from "../api";
import { useLang, useT } from "../i18n";
import { stopLabel } from "../lib/stops";
import { clockTime, formatDate, localDateTime, santaAnaIso, todayInSantaAna } from "../lib/time";
import type { LatLng, Preset, StopWithDepartures } from "../types";

export interface Place {
  key: string;
  label: string;
  location: LatLng;
  departsAt?: string;
}

export interface TripFormValues {
  departAt: string;
  catchAt: string | null;
  note: string;
}

type Field = "start" | "end";

interface Props {
  presets: Preset[];
  demoDate: string | null;
  start: Place | null;
  end: Place | null;
  picking: Field | null;
  loading: boolean;
  loadingLabel?: string;
  error: string | null;
  onPlace: (field: Field, place: Place | null) => void;
  onPick: (field: Field | null) => void;
  onSubmit: (values: TripFormValues) => void;
  onDepartureChange?: (departAt: string) => void;
}

const MAPTILER_KEY = import.meta.env.VITE_MAPTILER_KEY as string | undefined;
const BBOX = "-117.900,33.720,-117.830,33.780";
const inputClass =
  "min-h-[44px] w-full rounded-md border border-control px-2 py-1.5 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent";
const labelClass = "block text-sm font-semibold text-ink";

function PlaceField({
  field, presets, stops, value, picking, onPlace, onPick, linkActions,
}: {
  field: Field;
  presets: Preset[];
  stops: StopWithDepartures[];
  value: Place | null;
  picking: boolean;
  onPlace: (place: Place | null) => void;
  onPick: () => void;
  linkActions?: boolean;
}) {
  const t = useT();
  const [lang] = useLang();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Place[]>([]);
  const [showSearch, setShowSearch] = useState(false);

  async function search() {
    if (!MAPTILER_KEY || !query.trim()) return;
    const url = `https://api.maptiler.com/geocoding/${encodeURIComponent(query)}.json?key=${MAPTILER_KEY}&bbox=${BBOX}&limit=5`;
    const response = await fetch(url);
    if (!response.ok) return;
    const data = (await response.json()) as { features: { place_name: string; center: [number, number] }[] };
    setResults(data.features.map((f) => ({
      key: `search:${f.place_name}`, label: f.place_name,
      location: { lon: f.center[0], lat: f.center[1] },
    })));
  }

  const options: Place[] = [
    ...presets.map((p) => ({ key: `preset:${p.name}`, label: p.name, location: p.location })),
    ...stops.map((s) => ({
      key: `stop:${s.stop.stop_id}`,
      label: stopLabel(s.stop, s.departures, lang),
      location: s.stop.location,
      departsAt: s.departures[0]?.departs_at,
    })),
    ...results.map((r) => ({ ...r, key: `search:${r.label}` })),
    ...(value && ![...presets.map((p) => p.name), ...results.map((r) => r.label)].includes(value.label) ? [value] : []),
  ];
  const id = `${field}-place`;

  return (
    <fieldset className="space-y-1.5">
      <label htmlFor={id} className={labelClass}>{t(field === "start" ? "form.from" : "form.to")}</label>
      <select
        id={id}
        className={inputClass}
        value={value?.label ?? ""}
        onChange={(e) => onPlace(options.find((o) => o.label === e.target.value) ?? null)}
      >
        <option value="">{t("form.choose")}</option>
        {options.map((o) => <option key={o.key} value={o.label}>{o.label}</option>)}
      </select>
      {linkActions ? (
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
          <button type="button" onClick={onPick} aria-pressed={picking}
            className="text-accent underline aria-pressed:font-semibold">
            {t("form.pickOnMap")}
          </button>
          {MAPTILER_KEY && (
            <button type="button" onClick={() => setShowSearch((v) => !v)} aria-expanded={showSearch}
              className="text-accent underline">
              {t("form.search")}
            </button>
          )}
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={onPick} aria-pressed={picking}
            className="rounded-md border border-control-soft px-2 py-1 text-sm aria-pressed:bg-ink aria-pressed:text-paper focus-visible:outline-2 focus-visible:outline-accent">
            {t("form.pickOnMap")}
          </button>
          {MAPTILER_KEY && (
            <div className="flex flex-1 gap-1">
              <input aria-label={t("form.search")} placeholder={t("form.searchPlaceholder")} className={inputClass}
                value={query} onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void search(); } }} />
              <button type="button" onClick={() => void search()}
                className="rounded-md border border-control-soft px-2 text-sm focus-visible:outline-2 focus-visible:outline-accent">
                {t("form.search")}
              </button>
            </div>
          )}
        </div>
      )}
      {MAPTILER_KEY && linkActions && showSearch && (
        <div className="flex flex-1 gap-1">
          <input aria-label={t("form.search")} placeholder={t("form.searchPlaceholder")} className={inputClass}
            value={query} onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void search(); } }} />
          <button type="button" onClick={() => void search()}
            className="rounded-md border border-control-soft px-2 text-sm focus-visible:outline-2 focus-visible:outline-accent">
            {t("form.search")}
          </button>
        </div>
      )}
      {picking && <p className="text-sm text-ink">{t("form.pickOnMapHint")}</p>}
    </fieldset>
  );
}

export default function TripForm({
  presets, demoDate, start, end, picking, loading, loadingLabel, error, onPlace, onPick, onSubmit, onDepartureChange,
}: Props) {
  const t = useT();
  const [lang] = useLang();
  const [mode, setMode] = useState<"now" | "at">("now");
  const [date, setDate] = useState(todayInSantaAna());
  const [time, setTime] = useState("15:30");
  const [catchTime, setCatchTime] = useState("");
  const [note, setNote] = useState("");
  const [stops, setStops] = useState<StopWithDepartures[]>([]);
  const [missing, setMissing] = useState(false);

  const departAt = mode === "now" ? new Date().toISOString() : santaAnaIso(date, time);

  useEffect(() => {
    onDepartureChange?.(mode === "now" ? new Date().toISOString() : santaAnaIso(date, time));
  }, [mode, date, time, onDepartureChange]);

  useEffect(() => {
    if (!start) return;
    getStopsNear(start.location, mode === "now" ? new Date().toISOString() : santaAnaIso(date, time))
      .then(setStops)
      .catch(() => setStops([]));
  }, [start, mode, date, time]);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!start || !end) {
      setMissing(true);
      return;
    }
    setMissing(false);
    const catchDate = mode === "now" ? todayInSantaAna() : date;
    onSubmit({ departAt, catchAt: catchTime ? localDateTime(catchDate, catchTime) : null, note });
  }

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <PlaceField field="start" presets={presets} stops={[]} value={start} picking={picking === "start"} linkActions
        onPlace={(p) => onPlace("start", p)} onPick={() => onPick(picking === "start" ? null : "start")} />
      <PlaceField field="end" presets={presets} stops={stops} value={end} picking={picking === "end"} linkActions
        onPlace={(p) => {
          onPlace("end", p);
          if (p?.departsAt) setCatchTime(clockTime(p.departsAt));
        }}
        onPick={() => onPick(picking === "end" ? null : "end")} />

      <fieldset className="space-y-1.5">
        <legend className={labelClass}>{t("form.leave")}</legend>
        <div className="flex flex-wrap gap-4 text-sm">
          {(["now", "at"] as const).map((m) => (
            <label key={m} htmlFor={`leave-${m}`} className="inline-flex items-center gap-1.5">
              <input id={`leave-${m}`} type="radio" name="mode" checked={mode === m} onChange={() => setMode(m)} />
              {t(m === "now" ? "form.now" : "form.at")}
            </label>
          ))}
        </div>
        {mode === "at" && (
          <div className="flex gap-2">
            <input type="date" aria-label={t("form.at")} className={inputClass} value={date} onChange={(e) => setDate(e.target.value)} />
            <input type="time" aria-label={t("form.at")} className={inputClass} value={time} onChange={(e) => setTime(e.target.value)} />
          </div>
        )}
        {demoDate && (
          <button type="button"
            onClick={() => { setMode("at"); setDate(demoDate); setTime("15:30"); }}
            className="text-sm text-accent underline focus-visible:outline-2 focus-visible:outline-accent">
            {t("form.demoDay", { date: formatDate(demoDate, lang) })}
          </button>
        )}
      </fieldset>

      <div className="space-y-1.5">
        <label htmlFor="catch" className={labelClass}>{t("form.catch")} <span className="font-normal text-muted">{t("form.optional")}</span></label>
        <input id="catch" type="time" className={inputClass} value={catchTime} onChange={(e) => setCatchTime(e.target.value)} />
      </div>

      <div className="space-y-1.5">
        <label htmlFor="note" className={labelClass}>{t("form.note")} <span className="font-normal text-muted">{t("form.optional")}</span></label>
        <textarea id="note" rows={2} maxLength={500} className={inputClass} placeholder={t("form.notePlaceholder")}
          value={note} onChange={(e) => setNote(e.target.value)} />
      </div>

      {/* Stays in view at the bottom of the panel, however tall the form gets. */}
      <div className="sticky bottom-0 z-10 -mx-4 border-t border-rule bg-paper px-4 pb-3 pt-3">
      <button type="submit" disabled={loading}
        className="min-h-[48px] w-full rounded-md bg-accent px-4 py-2 font-medium text-paper hover:bg-accent-hover disabled:opacity-60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
        {loading ? loadingLabel ?? t("form.loading") : t("form.submit")}
      </button>
      </div>
      <div aria-live="polite">
        {missing && <p className="text-sm text-error">{t("form.missingPlaces")}</p>}
        {error && <p className="text-sm text-error">{error}</p>}
      </div>
    </form>
  );
}
