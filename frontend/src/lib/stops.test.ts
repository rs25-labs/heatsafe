import { describe, expect, it } from "vitest";
import { stopLabel, stopName } from "./stops";
import type { Departure, Stop } from "../types";

function stop(name: string, stopId: string): Stop {
  return {
    stop_id: stopId, name, agency: "octa",
    location: { lat: 33.75, lon: -117.86 }, distance_m: 100,
  };
}

function departure(headsign: string): Departure {
  return { route_name: "53", headsign, departs_at: "2026-09-09T15:34:00-07:00" };
}

describe("stopName", () => {
  it("tells apart stops with the same name by headsign", () => {
    const a = stopName(stop("MAIN-WASHINGTON", "s1"), [departure("Anaheim")], "en");
    const b = stopName(stop("MAIN-WASHINGTON", "s2"), [departure("Costa Mesa")], "en");
    expect(a).not.toBe(b);
    expect(a).toContain("Anaheim");
    expect(b).toContain("Costa Mesa");
  });

  it("omits the direction when there are no departures", () => {
    expect(stopName(stop("MAIN-WASHINGTON", "s1"), [], "en")).toBe("MAIN-WASHINGTON (OCTA)");
  });

  it("uses Spanish direction wording", () => {
    expect(stopName(stop("MAIN-WASHINGTON", "s1"), [departure("Anaheim")], "es")).toContain("hacia Anaheim");
  });
});

describe("stopLabel", () => {
  it("appends the next departure after the direction", () => {
    const label = stopLabel(stop("MAIN-WASHINGTON", "s1"), [departure("Anaheim")], "en");
    expect(label).toContain("MAIN-WASHINGTON (OCTA, to Anaheim)");
    expect(label).toContain("53");
  });
});
