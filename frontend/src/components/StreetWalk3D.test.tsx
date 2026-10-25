import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LangProvider } from "../i18n";
import type { Route } from "../types";
import StreetWalk3D from "./StreetWalk3D";

const ROUTE: Route = {
  id: "r0", label: "fastest", distance_m: 100, duration_min: 1.3, sun_minutes: 1.3,
  shade_pct: 0, effective_heat_index_f: 110, exposure: "high",
  segments: [{ coords: [{ lat: 33.75, lon: -117.86 }, { lat: 33.751, lon: -117.86 }], length_m: 100, in_sun: true, start_m: 0 }],
  amenities: [], arrives_in_time: null, minutes_to_spare: null,
};

describe("StreetWalk3D", () => {
  it("renders_unavailable_notice_without_key", () => {
    render(
      <LangProvider>
        <StreetWalk3D route={ROUTE} meters={0} when="2026-09-09T15:30:00-07:00" apiKey="" />
      </LangProvider>,
    );
    expect(screen.getByText(/3D street view is unavailable/i)).toBeTruthy();
  });
});
