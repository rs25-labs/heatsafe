import { useEffect, useState } from "react";
import { getConditions, type Conditions } from "../api";
import { useLang, useT } from "../i18n";
import { summaryText } from "../lib/conditions";
import { theme } from "../lib/theme";
import { formatDate, formatTime } from "../lib/time";

const heatColor: Record<Conditions["shade_level"], string> = {
  low: theme.heat1,
  moderate: theme.heat2,
  high: theme.heat3,
  extreme: theme.heat4,
};

/** Current heat conditions for the chosen departure; refreshes (debounced) as it changes. */
export default function ConditionsBar({ at }: { at: string }) {
  const t = useT();
  const [lang] = useLang();
  const [data, setData] = useState<Conditions | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
    const id = setTimeout(() => {
      getConditions(at)
        .then((conditions) => setData(conditions))
        .catch(() => setFailed(true));
    }, 300);
    return () => clearTimeout(id);
  }, [at]);

  return (
    <section aria-live="polite" aria-label={t("conditions.label")} className="max-w-[340px] rounded-md border border-rule bg-paper/95 px-3 py-2 shadow-sm">
      {failed ? (
        <p className="text-sm text-ink">{t("conditions.error")}</p>
      ) : data ? (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-ink sm:text-sm">
          <span className="font-semibold">
            {formatDate(at.slice(0, 10), lang)} {formatTime(at, lang)}
          </span>
          <span>
            {t("conditions.reading", {
              temp: data.weather.temp_f.toFixed(1),
              humidity: data.weather.rel_humidity,
              hi: Math.round(data.weather.heat_index_f),
            })}
          </span>
          <span
            aria-hidden="true"
            className="inline-block h-3 w-3 rounded-sm"
            style={{ background: heatColor[data.shade_level] }}
          />
          <span>{summaryText(data.shade_level, data.sun_level, lang)}</span>
        </div>
      ) : null}
    </section>
  );
}
