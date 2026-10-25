import { useEffect, useRef } from "react";
import { useT } from "../i18n";
import { WALK_SPEED_MPS, nextNotice, pointAtDistance, sunMinutesUpTo } from "../lib/routeGeometry";
import type { Route } from "../types";

// Playback speeds, as multiples of real walking speed (1.3 m/s).
export const SPEEDS = [10, 20, 40] as const;
export type Speed = (typeof SPEEDS)[number];

interface Props {
  route: Route;
  meters: number;
  playing: boolean;
  speed: Speed;
  onSpeed: (speed: Speed) => void;
  onMeters: (meters: number) => void;
  onPlaying: (playing: boolean) => void;
  onDone: () => void;
}

/** Play / pause / scrub controls and a live status line for walking a route. */
export default function WalkPlayer({ route, meters, playing, speed, onSpeed, onMeters, onPlaying, onDone }: Props) {
  const t = useT();
  const total = route.distance_m;
  const metersRef = useRef(meters);
  metersRef.current = meters;

  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    let last = performance.now();
    const step = (now: number) => {
      // Cap each step so a slow frame doesn't make the walker jump.
      const seconds = Math.min((now - last) / 1000, 0.1);
      const next = Math.min(total, metersRef.current + seconds * WALK_SPEED_MPS * speed);
      last = now;
      onMeters(next);
      if (next >= total) {
        onPlaying(false);
        return;
      }
      frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [playing, total, speed, onMeters, onPlaying]);

  const at = pointAtDistance(route.segments, meters);
  const notice = nextNotice(route, meters);
  const sun = sunMinutesUpTo(route.segments, meters).toFixed(1);
  const finished = meters >= total;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => {
            if (finished) onMeters(0);
            onPlaying(!playing || finished);
          }}
          className="flex h-11 min-w-24 items-center justify-center gap-2 rounded-md bg-accent px-4 font-medium text-paper hover:bg-accent-hover"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true" className="h-4 w-4 fill-current">
            {playing ? <path d="M6 5h4v14H6zM14 5h4v14h-4z" /> : <path d="M7 4l13 8-13 8z" />}
          </svg>
          {t(playing ? "player.pause" : finished ? "player.restart" : "player.resume")}
        </button>
        <label htmlFor="walk-scrub" className="sr-only">{t("player.scrub")}</label>
        <input id="walk-scrub" type="range" min={0} max={Math.round(total)} step={1} value={Math.round(meters)}
          onChange={(e) => { onPlaying(false); onMeters(Number(e.target.value)); }}
          className="min-h-[36px] flex-1 accent-accent" />
        <div role="group" aria-label={t("player.speed")} className="inline-flex rounded-md border border-control-soft text-sm">
          {SPEEDS.map((option) => (
            <button key={option} type="button" aria-pressed={speed === option} onClick={() => onSpeed(option)}
              title={t("player.speedTitle", { speed: option })}
              className="h-11 px-2.5 first:rounded-l-md last:rounded-r-md aria-pressed:bg-ink aria-pressed:text-paper">
              {option}×
            </button>
          ))}
        </div>
        <button type="button" onClick={onDone}
          className="h-11 rounded-md border border-control-soft bg-paper px-4 font-medium hover:border-subtle">
          {t("player.done")}
        </button>
      </div>
      <p className="text-sm" aria-live="off">
        {finished
          ? t("player.arrived", { minutes: (total / WALK_SPEED_MPS / 60).toFixed(1), sun })
          : t("player.status", {
              state: t(at.segment.in_sun ? "walk.inSun" : "walk.inShade"),
              meters: Math.round(meters),
              total: Math.round(total),
              minutes: (meters / WALK_SPEED_MPS / 60).toFixed(1),
              sun,
            })}
      </p>
      {notice && !finished && (
        <p className="text-sm font-medium">
          {notice.kind === "amenity"
            ? t("walk.amenityAhead", { name: notice.name ?? t(`amenity.${notice.amenityKind}`), meters: notice.meters_ahead })
            : t("walk.noShadeAhead", { meters: notice.meters_ahead })}
        </p>
      )}
    </div>
  );
}
