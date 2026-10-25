import { describe, expect, it } from "vitest";
import type { Route, Segment } from "../types";
import { nextNotice, pointAtDistance, sunMinutesUpTo } from "./routeGeometry";

// Two segments heading due north from (33.75, -117.86): 100 m in sun, then 200 m in shade.
const north = (meters: number) => ({ lat: 33.75 + meters / 111_000, lon: -117.86 });
const SEGMENTS: Segment[] = [
  { coords: [north(0), north(100)], length_m: 100, in_sun: true, start_m: 0 },
  { coords: [north(100), north(300)], length_m: 200, in_sun: false, start_m: 100 },
];

function route(segments: Segment[], amenityAt?: number): Route {
  return {
    id: "r0", label: "fastest", distance_m: 300, duration_min: 3.8, sun_minutes: 1.3,
    shade_pct: 67, effective_heat_index_f: 110, exposure: "high", segments,
    amenities: amenityAt === undefined ? [] : [{
      amenity: { kind: "drinking_water", name: "Fountain", location: north(amenityAt), source: "OSM" },
      distance_along_m: amenityAt,
    }],
    arrives_in_time: null, minutes_to_spare: null,
  };
}

describe("pointAtDistance", () => {
  it("starts at the first coordinate", () => {
    const at = pointAtDistance(SEGMENTS, 0);
    expect(at.point.lat).toBeCloseTo(north(0).lat, 6);
    expect(at.segment).toBe(SEGMENTS[0]);
  });

  it("interpolates inside a segment and reports a northward bearing", () => {
    const at = pointAtDistance(SEGMENTS, 150);
    expect(at.point.lat).toBeCloseTo(north(150).lat, 5);
    expect(at.segment).toBe(SEGMENTS[1]);
    expect(at.bearingDeg).toBeCloseTo(0, 0);
  });

  it("clamps to the end of the route", () => {
    const at = pointAtDistance(SEGMENTS, 999);
    expect(at.point.lat).toBeCloseTo(north(300).lat, 6);
  });
});

describe("sunMinutesUpTo", () => {
  it("counts only sunny meters walked so far", () => {
    expect(sunMinutesUpTo(SEGMENTS, 50)).toBeCloseTo(50 / 1.3 / 60, 3);
    expect(sunMinutesUpTo(SEGMENTS, 300)).toBeCloseTo(100 / 1.3 / 60, 3);
  });
});

describe("nextNotice", () => {
  it("announces an amenity 120 m ahead", () => {
    expect(nextNotice(route(SEGMENTS, 170), 50)).toEqual({ kind: "amenity", meters_ahead: 120, name: "Fountain", amenityKind: "drinking_water" });
  });

  it("warns when the next 150 m or more is all sun", () => {
    const sunny: Segment[] = [{ coords: [north(0), north(200)], length_m: 200, in_sun: true, start_m: 0 }];
    expect(nextNotice(route(sunny), 0)).toEqual({ kind: "no_shade_ahead", meters_ahead: 200 });
  });

  it("is quiet when nothing is ahead", () => {
    expect(nextNotice(route(SEGMENTS), 250)).toBeNull();
  });
});
