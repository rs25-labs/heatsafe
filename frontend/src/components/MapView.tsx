import maplibregl, { type GeoJSONSource, type MapLayerMouseEvent, type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";
import { useLang, useT } from "../i18n";
import { theme } from "../lib/theme";
import type { AmenityKind, AmenityOnRoute, LatLng, Route } from "../types";

const MAPTILER_KEY = import.meta.env.VITE_MAPTILER_KEY as string | undefined;
const SANTA_ANA: [number, number] = [-117.862, 33.752];
const ROUTE_LAYERS = ["routes-hit"];

export type Basemap = "street" | "satellite";

export interface HeatOverlay {
  url: string;
  bounds: [number, number, number, number]; // west, south, east, north
}

const OSM_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

function styleFor(basemap: Basemap): string | StyleSpecification {
  if (!MAPTILER_KEY) return OSM_STYLE;
  const map = basemap === "satellite" ? "hybrid" : "streets-v2";
  return `https://api.maptiler.com/maps/${map}/style.json?key=${MAPTILER_KEY}`;
}

function routesGeoJSON(routes: Route[], selectedId: string | null, hoverId: string | null): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: routes.flatMap((route) =>
      route.segments.map((segment, index) => ({
        type: "Feature" as const,
        properties: {
          route_id: route.id,
          segment: index,
          in_sun: segment.in_sun,
          selected: route.id === selectedId,
          hover: route.id === hoverId && route.id !== selectedId,
        },
        geometry: {
          type: "LineString" as const,
          coordinates: segment.coords.map((c) => [c.lon, c.lat]),
        },
      })),
    ),
  };
}

function pointGeoJSON(points: (LatLng | null)[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: points.flatMap((p, i) =>
      p
        ? [{
            type: "Feature" as const,
            properties: { role: ["start", "end", "walker"][i] },
            geometry: { type: "Point" as const, coordinates: [p.lon, p.lat] },
          }]
        : [],
    ),
  };
}

function addLayers(map: maplibregl.Map): void {
  if (map.getSource("routes")) return;
  map.addSource("heat", {
    type: "image",
    url: "data:image/gif;base64,R0lGODlhAQABAAAAACw=",
    coordinates: [[0, 0], [0.0001, 0], [0.0001, 0.0001], [0, 0.0001]],
  });
  map.addLayer({ id: "heat", type: "raster", source: "heat", paint: { "raster-opacity": 0 } });
  map.addSource("routes", { type: "geojson", data: routesGeoJSON([], null, null) });
  map.addSource("points", { type: "geojson", data: pointGeoJSON([]) });
  // Draw unselected routes first so the chosen one sits on top.
  const order: maplibregl.DataDrivenPropertyValueSpecification<number> = ["case", ["get", "selected"], 2, ["get", "hover"], 1, 0];
  map.addLayer({
    id: "routes-casing", type: "line", source: "routes",
    layout: { "line-cap": "round", "line-join": "round", "line-sort-key": order },
    paint: { "line-color": theme.paper, "line-opacity": 0.95, "line-width": ["case", ["get", "selected"], 11, ["get", "hover"], 9, 6] },
  });
  for (const sun of [false, true]) {
    map.addLayer({
      id: sun ? "routes-sun" : "routes-shade",
      type: "line",
      source: "routes",
      filter: ["==", ["get", "in_sun"], sun],
      layout: { "line-join": "round", "line-cap": "round", "line-sort-key": order },
      paint: {
        "line-color": sun
          ? ["case", ["get", "selected"], theme.sun, ["get", "hover"], theme.sunHover, theme.sunOther]
          : ["case", ["get", "selected"], theme.accent, ["get", "hover"], theme.subtle, theme.routeOther],
        "line-width": ["case", ["get", "selected"], 6, ["get", "hover"], 5, 3.5],
      },
    });
  }
  // A wide invisible line makes routes easy to hover and click.
  map.addLayer({
    id: "routes-hit", type: "line", source: "routes",
    paint: { "line-color": "#000000", "line-opacity": 0, "line-width": 18 },
  });
  map.addLayer({
    id: "points", type: "circle", source: "points",
    paint: {
      "circle-radius": ["match", ["get", "role"], "walker", 9, 8],
      "circle-color": ["match", ["get", "role"], "start", theme.paper, "end", theme.accent, theme.walker],
      "circle-stroke-color": ["match", ["get", "role"], "walker", theme.paper, theme.accent],
      "circle-stroke-width": 3,
    },
  });
}

// Small line icons for places along the way (meaningful, not decorative).
const ICON_PATHS: Record<AmenityKind, string> = {
  drinking_water: "M12 3c3 4 6 7.5 6 11a6 6 0 0 1-12 0c0-3.5 3-7 6-11z",
  library: "M4 5h6a2 2 0 0 1 2 2v12a2 2 0 0 0-2-2H4zM20 5h-6a2 2 0 0 0-2 2v12a2 2 0 0 1 2-2h6z",
  cooling_center: "M12 3v18M4.2 7.5l15.6 9M4.2 16.5l15.6-9",
  store: "M5 8h14l-1 12H6zM9 8V6a3 3 0 0 1 6 0v2",
  pharmacy: "M12 5v14M5 12h14",
  park: "M12 3l5 8h-3l4 6H6l4-6H7zM12 17v4",
};

function amenityElement(kind: AmenityKind, label: string): HTMLElement {
  const button = document.createElement("button");
  button.type = "button";
  button.setAttribute("aria-label", label);
  button.className = "heatsafe-place";
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", ICON_PATHS[kind]);
  svg.appendChild(path);
  button.appendChild(svg);
  return button;
}

function popupContent(title: string, detail: string): HTMLElement {
  const box = document.createElement("div");
  const strong = document.createElement("strong");
  strong.textContent = title;
  const p = document.createElement("div");
  p.textContent = detail;
  box.append(strong, p);
  return box;
}

interface Hover {
  x: number;
  y: number;
  routeId: string;
  segment: number;
}

interface Props {
  routes: Route[];
  selectedId: string | null;
  hoverId?: string | null;
  start: LatLng | null;
  end: LatLng | null;
  walker?: LatLng | null;
  follow?: boolean;
  places?: AmenityOnRoute[];
  heatOverlay?: HeatOverlay | null;
  basemap?: Basemap;
  /** A small, non-interactive map (the inset during a walk). */
  inset?: boolean;
  onSelectRoute?: (id: string) => void;
  onHoverRoute?: (id: string | null) => void;
  onMapClick?: (point: LatLng) => void;
  fitKey?: string;
  className?: string;
}

export default function MapView({
  routes, selectedId, hoverId = null, start, end, walker = null, follow = false, places = [],
  heatOverlay = null, basemap = "street", inset = false, onSelectRoute, onHoverRoute, onMapClick,
  fitKey, className = "",
}: Props) {
  const t = useT();
  const [lang] = useLang();
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const handlers = useRef({ onMapClick, onSelectRoute, onHoverRoute });
  const [styleVersion, setStyleVersion] = useState(0);
  const [tilesFailed, setTilesFailed] = useState(false);
  const [hover, setHover] = useState<Hover | null>(null);
  const failedRef = useRef(false);
  handlers.current = { onMapClick, onSelectRoute, onHoverRoute };

  useEffect(() => {
    if (!container.current) return;
    const map = new maplibregl.Map({
      container: container.current,
      style: styleFor(basemap),
      center: SANTA_ANA,
      zoom: inset ? 13 : 14,
      attributionControl: inset ? false : { compact: true },
      interactive: !inset,
    });
    if (!inset) map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    let loaded = false;
    map.on("style.load", () => {
      loaded = true;
      addLayers(map);
      setStyleVersion((v) => v + 1);
    });
    map.on("error", () => {
      // A bad or expired MapTiler key: fall back to plain OpenStreetMap tiles once.
      if (loaded || failedRef.current || !MAPTILER_KEY) return;
      failedRef.current = true;
      setTilesFailed(true);
      map.setStyle(OSM_STYLE);
    });
    if (!inset) {
      map.on("mousemove", ROUTE_LAYERS[0], (e: MapLayerMouseEvent) => {
        const feature = e.features?.[0];
        if (!feature) return;
        map.getCanvas().style.cursor = "pointer";
        const routeId = String(feature.properties.route_id);
        setHover({ x: e.point.x, y: e.point.y, routeId, segment: Number(feature.properties.segment) });
        handlers.current.onHoverRoute?.(routeId);
      });
      map.on("mouseleave", ROUTE_LAYERS[0], () => {
        map.getCanvas().style.cursor = "";
        setHover(null);
        handlers.current.onHoverRoute?.(null);
      });
      map.on("click", (e) => {
        const hit = map.getLayer(ROUTE_LAYERS[0])
          ? map.queryRenderedFeatures(e.point, { layers: ROUTE_LAYERS })[0]
          : undefined;
        if (hit && handlers.current.onSelectRoute && !handlers.current.onMapClick) {
          handlers.current.onSelectRoute(String(hit.properties.route_id));
          return;
        }
        handlers.current.onMapClick?.({ lat: e.lngLat.lat, lon: e.lngLat.lng });
      });
    }
    // Re-measure whenever the box changes size (panel opening, window resize, layout settling).
    const observer = new ResizeObserver(() => map.resize());
    observer.observe(container.current);
    mapRef.current = map;
    return () => {
      observer.disconnect();
      map.remove();
    };
    // The map is created once; later prop changes are applied by the effects below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (failedRef.current) return;
    mapRef.current?.setStyle(styleFor(basemap), { diff: false });
  }, [basemap]);

  useEffect(() => {
    const source = mapRef.current?.getSource("routes") as GeoJSONSource | undefined;
    source?.setData(routesGeoJSON(routes, selectedId, hoverId));
  }, [routes, selectedId, hoverId, styleVersion]);

  useEffect(() => {
    const source = mapRef.current?.getSource("points") as GeoJSONSource | undefined;
    source?.setData(pointGeoJSON([start, end, walker]));
  }, [start, end, walker, styleVersion]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !follow || !walker) return;
    map.easeTo({ center: [walker.lon, walker.lat], duration: 250, zoom: Math.max(map.getZoom(), 16.5) });
  }, [follow, walker]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || routes.length === 0) return;
    const bounds = new maplibregl.LngLatBounds();
    routes.forEach((r) => r.segments.forEach((s) => s.coords.forEach((c) => bounds.extend([c.lon, c.lat]))));
    map.fitBounds(bounds, { padding: inset ? 16 : { top: 72, bottom: 120, left: 48, right: 48 }, duration: inset ? 0 : 600 });
    // Fit once per trip, not on every leave-later change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey, styleVersion > 0]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || inset) return;
    const markers = places.map((place) => {
      const kind = t(`amenity.${place.amenity.kind}`);
      const name = place.amenity.name || kind;
      const element = amenityElement(place.amenity.kind, name);
      const popup = new maplibregl.Popup({ offset: 14, closeButton: false })
        .setDOMContent(popupContent(name, place.amenity.name ? kind : ""));
      return new maplibregl.Marker({ element })
        .setLngLat([place.amenity.location.lon, place.amenity.location.lat])
        .setPopup(popup)
        .addTo(map);
    });
    return () => markers.forEach((m) => m.remove());
    // Rebuild markers only when the places or the language change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [places, inset, lang]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.getSource("heat")) return;
    if (heatOverlay) {
      const [w, s, e, n] = heatOverlay.bounds;
      (map.getSource("heat") as maplibregl.ImageSource).updateImage({
        url: heatOverlay.url,
        coordinates: [[w, n], [e, n], [e, s], [w, s]],
      });
      map.setPaintProperty("heat", "raster-opacity", 0.55);
    } else {
      map.setPaintProperty("heat", "raster-opacity", 0);
    }
  }, [heatOverlay, styleVersion]);

  const hoverRoute = hover ? routes.find((r) => r.id === hover.routeId) : undefined;
  const hoverSegment = hoverRoute?.segments[hover?.segment ?? 0];

  return (
    <div className={`relative ${className}`}>
      <div className="absolute inset-0">
        <div ref={container} style={{ width: "100%", height: "100%" }} aria-label={t("map.street")} role="region" />
      </div>
      {hover && hoverRoute && hoverSegment && (
        <div
          role="tooltip"
          className="pointer-events-none absolute z-10 max-w-64 rounded-md border border-rule bg-paper px-3 py-2 text-sm shadow-sm"
          style={{ left: hover.x + 14, top: hover.y + 14 }}
        >
          <p className="font-semibold">
            {t("map.tipRoute", {
              name: t(`route.${hoverRoute.label}`),
              minutes: Math.round(hoverRoute.duration_min),
              pct: hoverRoute.shade_pct,
              level: t(`exposure.${hoverRoute.exposure}`),
            })}
          </p>
          <p>{t(hoverSegment.in_sun ? "map.tipSun" : "map.tipShade", { meters: Math.round(hoverSegment.length_m) })}</p>
          {hoverRoute.id !== selectedId && <p className="text-muted">{t("map.choose")}</p>}
        </div>
      )}
      {!inset && tilesFailed && (
        <p className="absolute bottom-2 left-2 z-10 rounded bg-paper/90 px-2 py-1 text-xs text-muted">{t("map.keyFailed")}</p>
      )}
    </div>
  );
}
