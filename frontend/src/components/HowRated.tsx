import { useT } from "../i18n";
import { EXPOSURE_BANDS, type ExposureBand } from "../lib/exposure";
import { theme } from "../lib/theme";

const heatColor = {
  low: theme.heat1,
  moderate: theme.heat2,
  high: theme.heat3,
  extreme: theme.heat4,
} as const;

function threshold(band: ExposureBand, t: (key: string, vars?: Record<string, string | number>) => string): string {
  if (band.minF === null && band.maxF !== null) return t("how.under", { max: band.maxF });
  if (band.maxF === null && band.minF !== null) return t("how.over", { min: band.minF });
  return t("how.range", { min: band.minF ?? 0, max: band.maxF ?? 0 });
}

/** Always-visible explainer above the footer; the header links here (#how). */
export default function HowRated() {
  const t = useT();
  return (
    <section id="how" aria-labelledby="how-title">
      <h2 id="how-title" className="sr-only">{t("how.title")}</h2>
      <p className="mt-1 max-w-prose text-sm">{t("how.body")}</p>
      <p className="mt-1 text-sm text-muted">{t("how.note")}</p>
      <ul className="mt-3 space-y-2">
        {EXPOSURE_BANDS.map((band) => (
          <li key={band.level} className="flex items-center gap-3">
            <span
              aria-hidden="true"
              className="inline-block h-4 w-8 rounded-sm"
              style={{ background: heatColor[band.level] }}
            />
            <span className="text-sm font-semibold">{t(`exposure.${band.level}`)}</span>
            <span className="text-sm text-muted">{threshold(band, t)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
