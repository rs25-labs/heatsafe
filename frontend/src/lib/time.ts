const TZ = "America/Los_Angeles";

export function formatTime(iso: string, lang: string): string {
  return new Intl.DateTimeFormat(lang === "es" ? "es-US" : "en-US", {
    hour: "numeric", minute: "2-digit", timeZone: TZ,
  }).format(new Date(iso));
}

export function formatDate(isoDate: string, lang: string): string {
  return new Intl.DateTimeFormat(lang === "es" ? "es-US" : "en-US", {
    weekday: "short", month: "short", day: "numeric", timeZone: "UTC",
  }).format(new Date(`${isoDate}T00:00:00Z`));
}

/** Local Santa Ana wall-clock time, sent without an offset; the server reads it as Pacific time. */
export function localDateTime(date: string, time: string): string {
  return `${date}T${time}:00`;
}

/** `YYYY-MM-DDTHH:MM:SS±HH:MM` for a Santa Ana wall-clock time. */
export function santaAnaIso(date: string, time: string): string {
  const probe = new Date(`${date}T${time}:00Z`);
  const laWall = new Date(probe.toLocaleString("en-US", { timeZone: TZ }));
  // Machine zone cancels out: LA offset = parsed-wall minus probe, minus the
  // machine's own offset (getTimezoneOffset is UTC-minus-local, in minutes).
  const minutes = Math.round(
    (laWall.getTime() - probe.getTime()) / 60000 - probe.getTimezoneOffset(),
  );
  const sign = minutes <= 0 ? "-" : "+";
  const abs = Math.abs(minutes);
  const hh = String(Math.floor(abs / 60)).padStart(2, "0");
  const mm = String(abs % 60).padStart(2, "0");
  return `${date}T${time}:00${sign}${hh}:${mm}`;
}

export function todayInSantaAna(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(new Date());
}

/** "HH:MM" in Santa Ana time, for <input type="time">. */
export function clockTime(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: TZ,
  }).format(new Date(iso));
}
