import { useLang, useT } from "../i18n";
import { formatDate } from "../lib/time";

export interface HeatMeta {
  bounds: [number, number, number, number];
  scene_id: string;
  platform: string;
  acquired: string;
  range_f: [number, number];
  source_url: string;
}

interface Props {
  meta: HeatMeta;
}

/** The ground-heat legend line, shown under the map controls while the layer is on. */
export default function HeatToggle({ meta }: Props) {
  const t = useT();
  const [lang] = useLang();
  return (
    <p className="mt-2 text-sm text-ink">
      <span
        aria-hidden="true"
        className="mr-2 inline-block h-3 w-24 rounded-sm align-middle"
        style={{ background: "linear-gradient(to right, #fff5eb, #fdd0a2, #fd8d3c, #d94801, #7f2704)" }}
      />
      {t("map.heatLegend", {
        date: formatDate(meta.acquired, lang),
        platform: meta.platform.replace("landsat-", ""),
        low: meta.range_f[0],
        high: meta.range_f[1],
      })}{" "}
      <a className="text-accent underline" href={meta.source_url} target="_blank" rel="noreferrer">
        {t("map.heatSource")}
      </a>
    </p>
  );
}
