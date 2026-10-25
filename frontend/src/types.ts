export type Lang = "en" | "es";
export type ExposureLevel = "low" | "moderate" | "high" | "extreme";
export type RouteLabel = "fastest" | "shadiest" | "balanced" | "alternate";
export type AmenityKind =
  | "drinking_water"
  | "library"
  | "cooling_center"
  | "store"
  | "pharmacy"
  | "park";

export interface LatLng {
  lat: number;
  lon: number;
}

export interface Segment {
  coords: LatLng[];
  length_m: number;
  in_sun: boolean;
  start_m: number;
}

export interface Amenity {
  kind: AmenityKind;
  name: string;
  location: LatLng;
  source: string;
}

export interface AmenityOnRoute {
  amenity: Amenity;
  distance_along_m: number;
}

export interface Route {
  id: string;
  label: RouteLabel;
  distance_m: number;
  duration_min: number;
  sun_minutes: number;
  shade_pct: number;
  effective_heat_index_f: number;
  exposure: ExposureLevel;
  segments: Segment[];
  amenities: AmenityOnRoute[];
  arrives_in_time: boolean | null;
  minutes_to_spare: number | null;
}

export interface Weather {
  temp_f: number;
  rel_humidity: number;
  heat_index_f: number;
  valid_at: string;
  source: string;
  source_url: string;
}

export interface Recommendation {
  route_id: string;
  explanation: string;
  lang: Lang;
  source: "ai" | "fallback";
  explanations: Record<Lang, string>;
}

export interface TractContext {
  tract_id: string;
  ces_version: string;
  fields: Record<string, number | null>;
  source_url: string;
}

export interface Stop {
  stop_id: string;
  name: string;
  agency: "octa" | "metrolink";
  location: LatLng;
  distance_m: number;
}

export interface Departure {
  route_name: string;
  headsign: string;
  departs_at: string;
}

export interface StopWithDepartures {
  stop: Stop;
  departures: Departure[];
}

export interface SafetyAlternatives {
  best_slot: string | null;
  cool_places: AmenityOnRoute[];
  stops: StopWithDepartures[];
}

export interface TripRequest {
  start: LatLng;
  end: LatLng;
  depart_at: string;
  catch_at?: string | null;
  note?: string | null;
  lang: Lang;
}

export interface TripResponse {
  trip_id: string;
  depart_at: string;
  routes: Route[];
  weather: Weather;
  recommendation: Recommendation;
  tract: TractContext | null;
  all_extreme: boolean;
  alternatives: SafetyAlternatives | null;
}

export interface RouteAtTime {
  route_id: string;
  shade_pct: number;
  sun_minutes: number;
  effective_heat_index_f: number;
  exposure: ExposureLevel;
  segments: Segment[];
  arrives_in_time: boolean | null;
  minutes_to_spare: number | null;
}

export interface TimelineSlot {
  at: string;
  weather: Weather;
  routes: RouteAtTime[];
}

export interface Preset {
  id: string;
  name: string;
  location: LatLng;
}
