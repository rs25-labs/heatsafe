import type {
  ExposureLevel, LatLng, Preset, StopWithDepartures, TimelineSlot, TripRequest, TripResponse, Weather,
} from "./types";

export class ApiError extends Error {}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch {
    throw new ApiError("network");
  }
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const message =
      typeof body === "object" && body !== null && "error" in body
        ? String((body as { error: { message: string } }).error.message)
        : `Request failed (${response.status})`;
    throw new ApiError(message);
  }
  return (await response.json()) as T;
}

export interface Conditions {
  weather: Weather;
  shade_level: ExposureLevel;
  sun_level: ExposureLevel;
}

export function getConditions(at: string): Promise<Conditions> {
  const params = new URLSearchParams({ at });
  return request(`/api/conditions?${params}`);
}

export function planTrip(req: TripRequest): Promise<TripResponse> {
  return request("/api/trip", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

export function getTimeline(tripId: string, start: string, end: string): Promise<TimelineSlot[]> {
  const params = new URLSearchParams({ start, end });
  return request(`/api/trip/${tripId}/timeline?${params}`);
}

/** Wake the server and load its data while the visitor fills in the form. Errors don't matter here. */
export function warmServer(): Promise<void> {
  return fetch("/api/warm").then(() => undefined, () => undefined);
}

export function getPresets(): Promise<Preset[]> {
  return request("/api/presets");
}

export function getConfig(): Promise<{ demo_date: string | null }> {
  return request("/api/config");
}

export function getStopsNear(point: LatLng, at: string): Promise<StopWithDepartures[]> {
  const params = new URLSearchParams({ lat: String(point.lat), lon: String(point.lon), at, n: "5" });
  return request(`/api/stops/near?${params}`);
}
