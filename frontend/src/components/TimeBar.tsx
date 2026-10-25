import { useLang, useT } from "../i18n";
import { formatTime } from "../lib/time";
import type { TimelineSlot } from "../types";

interface Props {
  timeline: TimelineSlot[] | null;
  error: string | null;
  index: number;
  onIndex: (index: number) => void;
}

/** "Leave at" control that sits on the map, so its effect on the routes is visible right away. */
export default function TimeBar({ timeline, error, index, onIndex }: Props) {
  const t = useT();
  const [lang] = useLang();
  if (error) return <p className="text-sm text-error">{error}</p>;
  if (!timeline || timeline.length === 0) return <p className="text-sm text-muted">{t("timebar.loading")}</p>;
  const first = timeline[0].at;
  const last = timeline[timeline.length - 1].at;
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor="timebar" className="text-sm font-semibold">
          {t("timebar.now", { time: formatTime(timeline[index].at, lang) })}
        </label>
        <span className="hidden text-xs text-muted md:inline">{t("timebar.hint")}</span>
      </div>
      <div className="mt-1 flex items-center gap-3 text-xs text-muted">
        <span>{formatTime(first, lang)}</span>
        <input id="timebar" type="range" min={0} max={timeline.length - 1} step={1} value={index}
          onChange={(e) => onIndex(Number(e.target.value))}
          aria-valuetext={formatTime(timeline[index].at, lang)}
          className="min-h-[36px] flex-1 accent-accent" />
        <span>{formatTime(last, lang)}</span>
      </div>
    </div>
  );
}
