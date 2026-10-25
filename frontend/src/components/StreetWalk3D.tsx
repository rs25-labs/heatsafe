import { useEffect, useRef, useState } from "react";
import { useLang, useT } from "../i18n";
import { theme } from "../lib/theme";
import { bearingDeg, pointAtDistance, routeLength } from "../lib/routeGeometry";
import { formatTime } from "../lib/time";
import type { Route } from "../types";

type CesiumModule = typeof import("cesium");

interface Props {
  route: Route;
  meters: number;
  when: string;
  apiKey: string;
  /** False while hidden: rendering pauses but the loaded city is kept for next time. */
  active?: boolean;
  /** True while playback moves the camera. */
  moving?: boolean;
  /** Called once, when the first 3D tiles have arrived. */
  onReady?: () => void;
}

// Drone-style view: about 120 m above the walker, looking down at 45°. Google's
// photo-built 3D model looks smooth from here; at rooftop height it breaks into polygons.
const CAMERA_PITCH_DEG = -45;
const CAMERA_RANGE_M = 170;
// Sharper tiles (Cesium's default allowed blur is 16), soft high-resolution shadows,
// and antialiasing so edges aren't jagged.
const TILE_DETAIL_SSE = 4;
// While the camera moves, slightly softer tiles keep up with it; full detail returns on pause.
const MOVING_DETAIL_SSE = 16;
const SHADOW_MAP_SIZE = 4096;
const MSAA_SAMPLES = 4;
const READY_CAP_MS = 10_000;
const HEIGHT_SAMPLE_M = 10;
// Look this far ahead to choose the camera direction, and ease into turns.
const LOOKAHEAD_M = 40;
const TURN_EASING = 0.12;
// Ground level is the lowest height within this many samples (±20 m), so the walker
// never lands on a roof edge beside the sidewalk.
const GROUND_WINDOW = 2;
const CLAMP_HEIGHT_M = 200;
// Lateral offsets (~6 m) around each route point: clamping from above can land on
// roofs or canopies, so the street level is the lowest of the nearby samples.
const HEIGHT_OFFSET_DEG = 0.00006;
const HEIGHT_OFFSETS = [
  [0, 0], [HEIGHT_OFFSET_DEG, 0], [-HEIGHT_OFFSET_DEG, 0],
  [0, HEIGHT_OFFSET_DEG], [0, -HEIGHT_OFFSET_DEG],
];
const ROUTE_COLOR = theme.accent;

interface Viewer3D {
  Cesium: CesiumModule;
  viewer: import("cesium").Viewer;
  tileset: import("cesium").Cesium3DTileset;
}

interface Walk3D {
  walker: import("cesium").Entity;
  heights: number[];
}

export default function StreetWalk3D({ route, meters, when, apiKey, active = true, moving = false, onReady }: Props) {
  const t = useT();
  const [lang] = useLang();
  const container = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer3D | null>(null);
  const walkRef = useRef<Walk3D | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "failed">(apiKey ? "loading" : "failed");
  const [walkVersion, setWalkVersion] = useState(0);
  const [firstTiles, setFirstTiles] = useState(false);
  const headingRef = useRef<number | null>(null);

  // The viewer and Google 3D tiles are created once per key.
  useEffect(() => {
    if (!apiKey || !container.current) return;
    let cancelled = false;
    let readyTimer = 0;
    let viewer: import("cesium").Viewer | null = null;
    setStatus("loading");

    (async () => {
      // Not named "Cesium": in production the Cesium plugin maps this import to a global of that
      // name, and a local const with the same name would shadow it and crash on first use.
      const cesiumLib = await import("cesium");
      await import("cesium/Build/Cesium/Widgets/widgets.css");
      if (cancelled || !container.current) return;
      cesiumLib.GoogleMaps.defaultApiKey = apiKey;
      viewer = new cesiumLib.Viewer(container.current, {
        globe: false, baseLayer: false, timeline: false, animation: false, baseLayerPicker: false,
        geocoder: false, homeButton: false, sceneModePicker: false, navigationHelpButton: false,
        fullscreenButton: false, infoBox: false, selectionIndicator: false, shadows: true,
        msaaSamples: MSAA_SAMPLES,
      });
      viewer.clock.shouldAnimate = false;
      viewer.shadowMap.size = SHADOW_MAP_SIZE;
      viewer.shadowMap.softShadows = true;
      viewer.shadowMap.darkness = 0.35;
      if (!viewer.scene.msaaSupported) viewer.scene.postProcessStages.fxaa.enabled = true;
      const tileset = await cesiumLib.createGooglePhotorealistic3DTileset();
      tileset.shadows = cesiumLib.ShadowMode.ENABLED;
      tileset.maximumScreenSpaceError = TILE_DETAIL_SSE;
      // Lets screenshots (and people) know the sharpest tiles have arrived.
      tileset.allTilesLoaded.addEventListener(() => container.current?.setAttribute("data-tiles-loaded", "true"));
      // Ready once the first view has its tiles (or after a short cap, so nobody waits forever).
      // The first camera placement happens before any tiles exist; it's placed again on ready.
      tileset.initialTilesLoaded.addEventListener(() => setFirstTiles(true));
      readyTimer = window.setTimeout(() => setFirstTiles(true), READY_CAP_MS);
      viewer.scene.primitives.add(tileset);
      if (cancelled) return;
      viewerRef.current = { Cesium: cesiumLib, viewer, tileset };
      setStatus("ready");
    })().catch(() => {
      if (!cancelled) setStatus("failed");
    });

    return () => {
      cancelled = true;
      window.clearTimeout(readyTimer);
      viewerRef.current = null;
      walkRef.current = null;
      viewer?.destroy();
    };
  }, [apiKey]);

  // On a new route or time: move the sun and redraw the route; keep the viewer.
  useEffect(() => {
    const current = viewerRef.current;
    if (status !== "ready" || !current) return;
    const { Cesium, viewer } = current;
    let cancelled = false;
    viewer.clock.currentTime = Cesium.JulianDate.fromIso8601(when);
    viewer.entities.removeAll();
    for (const segment of route.segments) {
      viewer.entities.add({
        polyline: {
          positions: segment.coords.map((c) => Cesium.Cartesian3.fromDegrees(c.lon, c.lat)),
          width: 6,
          clampToGround: true,
          classificationType: Cesium.ClassificationType.CESIUM_3D_TILE,
          material: segment.in_sun
            ? Cesium.Color.fromCssColorString(theme.sun)
            : Cesium.Color.fromCssColorString(ROUTE_COLOR),
        },
      });
    }
    const walker = viewer.entities.add({
      point: {
        pixelSize: 14, color: Cesium.Color.fromCssColorString(theme.walker),
        outlineColor: Cesium.Color.WHITE, outlineWidth: 3,
        // Always draw on top of trees and buildings so the marker stays visible.
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
    });
    const points = Array.from(
      { length: Math.floor(routeLength(route.segments) / HEIGHT_SAMPLE_M) + 1 },
      (_, i) => pointAtDistance(route.segments, i * HEIGHT_SAMPLE_M).point,
    );
    const samples = points.flatMap((p) =>
      HEIGHT_OFFSETS.map(([dlon, dlat]) =>
        Cesium.Cartesian3.fromDegrees(p.lon + dlon, p.lat + dlat, CLAMP_HEIGHT_M),
      ),
    );
    walkRef.current = { walker, heights: points.map(() => 0) };
    setWalkVersion((v) => v + 1);
    viewer.scene.clampToHeightMostDetailed(samples)
      .then((clamped) => {
        if (cancelled || !walkRef.current) return;
        walkRef.current.heights = points.map((_, i) => {
          const nearby: number[] = [];
          for (const c of clamped.slice(i * HEIGHT_OFFSETS.length, (i + 1) * HEIGHT_OFFSETS.length)) {
            if (c) nearby.push(Cesium.Cartographic.fromCartesian(c).height);
          }
          return nearby.length ? Math.min(...nearby) : 0;
        }).map((_, i, raw) =>
          Math.min(...raw.slice(Math.max(0, i - GROUND_WINDOW), i + GROUND_WINDOW + 1)),
        );
        setWalkVersion((v) => v + 1);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [status, route, when]);

  useEffect(() => {
    if (firstTiles) onReady?.();
    // Fire once per load; onReady identity changes don't matter.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firstTiles]);

  useEffect(() => {
    const viewer = viewerRef.current?.viewer;
    if (viewer) viewer.useDefaultRenderLoop = active;
  }, [active, status]);

  useEffect(() => {
    const tileset = viewerRef.current?.tileset;
    if (tileset) tileset.maximumScreenSpaceError = moving ? MOVING_DETAIL_SSE : TILE_DETAIL_SSE;
  }, [moving, status]);

  // Follow the walker as the slider moves.
  useEffect(() => {
    const current = viewerRef.current;
    const walk = walkRef.current;
    if (status !== "ready" || !current || !walk) return;
    const { Cesium, viewer } = current;
    const at = pointAtDistance(route.segments, meters);
    const ahead = pointAtDistance(route.segments, Math.min(meters + LOOKAHEAD_M, routeLength(route.segments)));
    const target = meters + 1 < routeLength(route.segments) ? bearingDeg(at.point, ahead.point) : at.bearingDeg;
    const previous = headingRef.current;
    const turn = previous === null ? 0 : ((target - previous + 540) % 360) - 180;
    const heading = previous === null || !moving ? target : (previous + turn * TURN_EASING + 360) % 360;
    headingRef.current = heading;
    const index = Math.min(Math.round(meters / HEIGHT_SAMPLE_M), walk.heights.length - 1);
    const position = Cesium.Cartesian3.fromDegrees(at.point.lon, at.point.lat, walk.heights[index] + 1.5);
    walk.walker.position = new Cesium.ConstantPositionProperty(position);
    container.current?.setAttribute("data-tiles-loaded", "false");
    viewer.camera.lookAt(
      position,
      new Cesium.HeadingPitchRange(
        Cesium.Math.toRadians(heading),
        Cesium.Math.toRadians(CAMERA_PITCH_DEG),
        CAMERA_RANGE_M,
      ),
    );
  }, [meters, status, route, walkVersion, firstTiles, moving]);

  // The notice (not the viewer state) decides: on a small screen there is no key,
  // so there is no container to build a viewer in when the key comes back.
  // No key, or the 3D view couldn't start: say so rather than "loading" forever.
  if (!apiKey || status === "failed") {
    return (
      <div className="grid h-full w-full place-items-center bg-band p-6 text-center text-sm text-ink">
        <p>{t("walk3d.unavailable")}</p>
      </div>
    );
  }
  return (
    <div className="relative h-full w-full">
      <div ref={container} className="absolute inset-0" />
      <p className="pointer-events-none absolute left-3 top-3 z-10 rounded bg-paper/90 px-2 py-1 text-sm font-medium">
        {t("player.view3d", { time: formatTime(when, lang) })}
      </p>
      {(status === "loading" || !firstTiles) && (
        <p className="absolute inset-0 z-10 grid place-items-center bg-paper/80 text-sm">{t("walk3d.loading")}</p>
      )}
    </div>
  );
}
