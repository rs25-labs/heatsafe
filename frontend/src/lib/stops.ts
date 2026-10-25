import { translate } from "../i18n";
import { formatTime } from "./time";
import type { Departure, Lang, Stop } from "../types";

export function agencyName(agency: Stop["agency"], lang: Lang): string {
  return translate(lang, agency === "metrolink" ? "stop.metrolink" : "stop.octa");
}

/** "MAIN-WASHINGTON (OCTA, to Anaheim)": the name plus the next departure's direction. */
export function stopName(stop: Stop, departures: Departure[], lang: Lang): string {
  const headsign = departures[0]?.headsign;
  const direction = headsign ? `, ${translate(lang, "stop.direction", { headsign })}` : "";
  return `${stop.name} (${agencyName(stop.agency, lang)}${direction})`;
}

/** stopName plus the next departure's route and time, for the place dropdowns. */
export function stopLabel(stop: Stop, departures: Departure[], lang: Lang): string {
  const next = departures[0];
  const when = next ? ` · ${next.route_name} ${formatTime(next.departs_at, lang)}` : "";
  return `${stopName(stop, departures, lang)}${when}`;
}
