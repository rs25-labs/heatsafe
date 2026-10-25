import { useLang, useT } from "../i18n";
import { stopName } from "../lib/stops";
import { formatTime } from "../lib/time";
import type { SafetyAlternatives } from "../types";

const CDC_URL = "https://www.cdc.gov/extreme-heat/warning-signs/";

interface Props {
  alternatives: SafetyAlternatives;
  onLeaveAt: (iso: string) => void;
}

export default function NoSafeRoute({ alternatives, onLeaveAt }: Props) {
  const t = useT();
  const [lang] = useLang();
  const { best_slot, cool_places, stops } = alternatives;
  return (
    <section className="space-y-2 rounded border-2 border-heat-4 p-3" role="alert">
      <h2 className="font-semibold text-heat-4">{t("nosafe.title")}</h2>
      {best_slot ? (
        <button type="button" onClick={() => onLeaveAt(best_slot)}
          className="min-h-[48px] rounded-md bg-accent px-3 py-1.5 text-sm text-paper hover:bg-accent-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
          {t("nosafe.leaveAt", { time: formatTime(best_slot, lang) })}
        </button>
      ) : (
        <p className="text-sm">{t("nosafe.noBetter")}</p>
      )}
      <div className="text-sm">
        <p className="font-medium">{t("nosafe.cool")}</p>
        <ul className="list-disc pl-5">
          {cool_places.map((p) => (
            <li key={`${p.amenity.name}-${p.distance_along_m}`}>
              {t("nosafe.coolPlace", {
                name: p.amenity.name || t(`amenity.${p.amenity.kind}`),
                kind: t(`amenity.${p.amenity.kind}`),
                meters: Math.round(p.distance_along_m),
              })}
            </li>
          ))}
        </ul>
      </div>
      <div className="text-sm">
        <p className="font-medium">{t("nosafe.bus")}</p>
        <ul className="list-disc pl-5">
          {stops.filter((s) => s.departures.length).map((s) => (
            <li key={s.stop.stop_id}>
              {t("nosafe.stop", {
                name: stopName(s.stop, s.departures, lang),
                departures: s.departures.map((d) => `${d.route_name} ${formatTime(d.departs_at, lang)}`).join(", "),
              })}
            </li>
          ))}
        </ul>
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer font-medium focus-visible:outline-2 focus-visible:outline-accent">{t("nosafe.illnessTitle")}</summary>
        <p className="mt-1">{t("nosafe.exhaustion")}</p>
        <p className="mt-1">{t("nosafe.stroke")}</p>
        <a className="text-accent underline" href={CDC_URL} target="_blank" rel="noreferrer">{t("nosafe.source")}</a>
      </details>
    </section>
  );
}
