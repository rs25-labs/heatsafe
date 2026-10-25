import type { ExposureLevel } from "../types";

// NWS heat-index bands plus the +15°F full-sun allowance used in scoring.
// Mirrors backend/heatsafe/heat.py exposure_level: change both together.
export interface ExposureBand {
  level: ExposureLevel;
  /** Inclusive lower bound, or null for the bottom band. */
  minF: number | null;
  /** Exclusive upper bound, or null for the top band. */
  maxF: number | null;
}

export const EXPOSURE_BANDS: ExposureBand[] = [
  { level: "low", minF: null, maxF: 90 },
  { level: "moderate", minF: 90, maxF: 103 },
  { level: "high", minF: 103, maxF: 115 },
  { level: "extreme", minF: 115, maxF: null },
];
