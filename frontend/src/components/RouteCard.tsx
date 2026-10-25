import { useState } from "react";
import { useLang, useT } from "../i18n";
import type { Recommendation, Route } from "../types";

const EXPOSURE_BG: Record<Route["exposure"], string> = {
  low: "bg-heat-1", moderate: "bg-heat-2", high: "bg-heat-3", extreme: "bg-heat-4",
};

interface Props {
  route: Route;
  /** The same route at the original departure; when given and different, changes are shown. */
  base?: Route;
  recommended: boolean;
  /** Why this route was recommended; only given for the recommended route. */
  reason?: Recommendation;
  selected: boolean;
  hovered: boolean;
  onSelect: () => void;
  onHover: (hovering: boolean) => void;
}

export default function RouteCard({ route, base, recommended, reason, selected, hovered, onSelect, onHover }: Props) {
  const t = useT();
  const [lang] = useLang();
  const [open, setOpen] = useState(false);
  const places = [...new Set(route.amenities.map((a) => a.amenity.name || t(`amenity.${a.amenity.kind}`)))];
  const was = (now: string | number, before: string | number | undefined, text: string) =>
    base && before !== undefined && before !== now ? (
      <span className="ml-1 text-muted">({t("card.change", { value: text })})</span>
    ) : null;

  return (
    <div
      onMouseEnter={() => onHover(true)}
      onMouseLeave={() => onHover(false)}
      className={`rounded-md border bg-paper transition-colors ${
        selected ? "border-2 border-accent" : hovered ? "border-subtle" : "border-rule hover:border-subtle"
      }`}
    >
      {/* Collapsed by default to two short lines; the ">" opens the rest. */}
      <div className="flex items-stretch">
        <button
          type="button"
          onClick={onSelect}
          onFocus={() => onHover(true)}
          onBlur={() => onHover(false)}
          aria-pressed={selected}
          className="min-w-0 flex-1 rounded-l-md py-2 pl-3 pr-1 text-left"
        >
          <span className="flex items-center gap-2">
            <span className="font-semibold">{t(`route.${route.label}`)}</span>
            {recommended && (
              <span className="rounded bg-ink px-1.5 py-px text-xs font-medium text-paper">{t("route.recommended")}</span>
            )}
          </span>
          <span className="flex flex-wrap items-center gap-x-1.5 text-sm">
            <span className="text-muted">{t("card.minutes", { minutes: Math.round(route.duration_min) })}</span>
            <span aria-hidden="true" className="text-muted">·</span>
            <span>
              {t("route.shaded", { pct: route.shade_pct })}
              {was(route.shade_pct, base?.shade_pct, `${base?.shade_pct}%`)}
            </span>
            <span aria-hidden="true" className="text-muted">·</span>
            <span className="inline-flex items-center gap-1.5 font-medium">
              <span aria-hidden="true" className={`inline-block h-2.5 w-2.5 rounded-sm ${EXPOSURE_BG[route.exposure]}`} />
              {t("card.exposure", { level: lang === "es" ? t(`exposure.${route.exposure}`).toLowerCase() : t(`exposure.${route.exposure}`) })}
              {was(route.exposure, base?.exposure, base ? t(`exposure.${base.exposure}`) : "")}
            </span>
          </span>
          {route.arrives_in_time === false && (
            <span className="block text-sm font-medium text-error">{t("route.late")}</span>
          )}
        </button>

        <button
          type="button"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          aria-controls={`details-${route.id}`}
          aria-label={t(open ? "card.less" : "card.more")}
          title={t(open ? "card.less" : "card.more")}
          className="flex w-10 shrink-0 items-center justify-center rounded-r-md text-muted hover:text-ink"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true" className={`h-4 w-4 fill-none stroke-current stroke-2 transition-transform ${open ? "rotate-90" : ""}`}>
            <path d="M9 6l6 6-6 6" />
          </svg>
        </button>
      </div>

      {open && (
        <div id={`details-${route.id}`} className="space-y-0.5 border-t border-rule px-3 py-2 text-sm">
          {reason && (
            <div className="mb-2">
              <p>{reason.explanations[lang] ?? reason.explanation}</p>
              <p className="text-[13px] text-muted">{t(reason.source === "ai" ? "card.whyAi" : "card.whyRule")}</p>
            </div>
          )}
          <p className="text-muted">
            {t("route.walk", { minutes: Math.round(route.duration_min), km: (route.distance_m / 1000).toFixed(1) })}
          </p>
          <p>
            {t("route.sun", { minutes: route.sun_minutes })}
            {was(route.sun_minutes, base?.sun_minutes, `${base?.sun_minutes}`)}
          </p>
          <p>{t("route.feelsLike", { temp: route.effective_heat_index_f.toFixed(1) })}</p>
          {places.length > 0 && <p className="text-muted">{t("route.places", { places: places.join(", ") })}</p>}
          {route.arrives_in_time && <p>{t("route.onTime", { minutes: route.minutes_to_spare ?? 0 })}</p>}
        </div>
      )}
    </div>
  );
}
