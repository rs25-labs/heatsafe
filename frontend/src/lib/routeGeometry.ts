import type { AmenityKind, LatLng, Route, Segment } from "../types";

export const WALK_SPEED_MPS = 1.3;
const EARTH_RADIUS_M = 6_371_000;
const AMENITY_LOOKAHEAD_M = 200;
const NO_SHADE_WARNING_M = 150;

const toRad = (deg: number) => (deg * Math.PI) / 180;
const toDeg = (rad: number) => (rad * 180) / Math.PI;

export function distanceM(a: LatLng, b: LatLng): number {
  const dLat = toRad(b.lat - a.lat);
  const dLon = toRad(b.lon - a.lon);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(h));
}

export function bearingDeg(a: LatLng, b: LatLng): number {
  const y = Math.sin(toRad(b.lon - a.lon)) * Math.cos(toRad(b.lat));
  const x =
    Math.cos(toRad(a.lat)) * Math.sin(toRad(b.lat)) -
    Math.sin(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.cos(toRad(b.lon - a.lon));
  return (toDeg(Math.atan2(y, x)) + 360) % 360;
}

export function routeLength(segments: Segment[]): number {
  const last = segments[segments.length - 1];
  return last ? last.start_m + last.length_m : 0;
}

export function pointAtDistance(
  segments: Segment[],
  meters: number,
): { point: LatLng; segment: Segment; bearingDeg: number } {
  const target = Math.min(Math.max(meters, 0), routeLength(segments));
  const segment =
    segments.find((s) => target <= s.start_m + s.length_m) ?? segments[segments.length - 1];
  const coords = segment.coords;
  // Scale the segment's own point spacing to its recorded length.
  const legs = coords.slice(1).map((c, i) => distanceM(coords[i], c));
  const total = legs.reduce((sum, leg) => sum + leg, 0) || 1;
  let remaining = ((target - segment.start_m) / segment.length_m || 0) * total;
  for (let i = 0; i < legs.length; i++) {
    if (remaining <= legs[i] || i === legs.length - 1) {
      const t = legs[i] ? Math.min(remaining / legs[i], 1) : 0;
      const a = coords[i];
      const b = coords[i + 1];
      return {
        point: { lat: a.lat + (b.lat - a.lat) * t, lon: a.lon + (b.lon - a.lon) * t },
        segment,
        bearingDeg: bearingDeg(a, b),
      };
    }
    remaining -= legs[i];
  }
  return { point: coords[0], segment, bearingDeg: 0 };
}

export function sunMinutesUpTo(segments: Segment[], meters: number): number {
  const sunnyMeters = segments
    .filter((s) => s.in_sun)
    .reduce((sum, s) => sum + Math.max(0, Math.min(meters - s.start_m, s.length_m)), 0);
  return sunnyMeters / WALK_SPEED_MPS / 60;
}

export type Notice =
  | { kind: "amenity"; meters_ahead: number; name?: string; amenityKind: AmenityKind }
  | { kind: "no_shade_ahead"; meters_ahead: number };

export function nextNotice(route: Route, meters: number): Notice | null {
  const amenity = route.amenities.find(
    (a) => a.distance_along_m > meters && a.distance_along_m - meters <= AMENITY_LOOKAHEAD_M,
  );
  if (amenity) {
    return {
      kind: "amenity",
      meters_ahead: Math.round(amenity.distance_along_m - meters),
      name: amenity.amenity.name || undefined,
      amenityKind: amenity.amenity.kind,
    };
  }
  let sunAhead = 0;
  for (const s of route.segments) {
    const end = s.start_m + s.length_m;
    if (end <= meters) continue;
    if (!s.in_sun) break;
    sunAhead += end - Math.max(s.start_m, meters);
  }
  return sunAhead >= NO_SHADE_WARNING_M
    ? { kind: "no_shade_ahead", meters_ahead: Math.round(sunAhead) }
    : null;
}
