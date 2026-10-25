import { useLang, useT } from "../i18n";
import { formatTime } from "../lib/time";
import type { TripResponse } from "../types";

export default function WhyPanel({ trip }: { trip: TripResponse }) {
  const t = useT();
  const [lang] = useLang();
  const { weather, tract } = trip;
  return (
    <div className="space-y-3 text-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-rule">
                {["why.route", "why.minutes", "why.sun", "why.shade", "why.feels", "why.exposure"].map((key) => (
                  <th key={key} scope="col" className={`py-1 pr-3 font-medium ${key === "why.route" ? "" : "text-right"}`}>{t(key)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {trip.routes.map((r) => (
                <tr key={r.id} className="border-b border-rule">
                  <th scope="row" className="py-1 pr-3 font-normal">{t(`route.${r.label}`)}</th>
                  <td className="pr-3 text-right">{r.duration_min} min</td>
                  <td className="pr-3 text-right">{r.sun_minutes} min</td>
                  <td className="pr-3 text-right">{r.shade_pct}%</td>
                  <td className="pr-3 text-right">{r.effective_heat_index_f}°F</td>
                  <td>{t(`exposure.${r.exposure}`)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>
          {t("why.weather", {
            time: formatTime(weather.valid_at, lang), temp: weather.temp_f,
            humidity: weather.rel_humidity, hi: Math.round(weather.heat_index_f),
          })}{" "}
          <a className="text-accent underline" href={weather.source_url} target="_blank" rel="noreferrer">
            {t("why.weatherSource", { source: weather.source })}
          </a>
        </p>
        <p className="text-ink">{t("why.heatMethod")}</p>
        {tract && (
          <div>
            <p>{t("why.tract", { tract: tract.tract_id, version: tract.ces_version })}</p>
            <ul className="mt-1 grid gap-x-4 sm:grid-cols-2">
              {Object.entries(tract.fields).filter(([, v]) => v !== null).map(([name, value]) => (
                <li key={name}>{t(`tract.${name}`)}: {Math.round(value as number)}</li>
              ))}
            </ul>
            <a className="text-accent underline" href={tract.source_url} target="_blank" rel="noreferrer">
              {t("why.tractSource")}
            </a>
          </div>
        )}
    </div>
  );
}
