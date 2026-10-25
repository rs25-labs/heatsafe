"""Run 10 real trips (demo pair + 4 other pairs, en + es) and report AI vs fallback outcomes.

Uses the full in-process API stack: real Open-Meteo weather and the real configured
model via default_client(). The LLM client is wrapped in an observer that records the
raw AI reply, and ai_fallback log lines are captured, so each row shows the chosen
route, the source, the fallback reason, and the AI text when one was rejected.

Run from backend/: uv run python scripts/ai_check.py [--repeat N] [--demo-only]
(no server needed).
"""

import argparse
import logging
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from heatsafe.api import app, llm_client
from heatsafe.config import PRESETS, get_settings
from heatsafe.recommend import default_client

PAIRS = [
    ("demo OCSA->station", PRESETS["ocsa"], PRESETS["sartc"],
     "Carrying a cello, need the 3:52 train"),
    ("high school->OCSA", {"lat": 33.7490, "lon": -117.8729}, PRESETS["ocsa"],
     "Carrying groceries, can't walk more than 35 minutes"),
    ("station->Santiago Park", PRESETS["sartc"], {"lat": 33.7519, "lon": -117.8480},
     ""),
    ("Standard Ave->4th & Main", {"lat": 33.7350, "lon": -117.8600},
     {"lat": 33.7457, "lon": -117.8674}, "Tengo asma, prefiero la sombra"),
    ("Santa Ana College->OCSA", {"lat": 33.7589, "lon": -117.8828}, PRESETS["ocsa"],
     "Walking with a stroller, need the least sun"),
]


class SpyClient:
    """Wraps the real client and records its raw reply (or error) per call."""

    def __init__(self, inner: object) -> None:
        self.inner = inner
        self.last_raw: object = None

    def choose(self, payload: dict, lang: str) -> dict:
        try:
            raw = self.inner.choose(payload, lang)  # type: ignore[union-attr]
        except Exception as exc:
            self.last_raw = f"<{type(exc).__name__}: {exc}>"
            raise
        self.last_raw = raw
        return raw


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure AI vs fallback outcomes on real trips.")
    parser.add_argument("--repeat", type=int, default=1, help="Repeat the trip set N times.")
    parser.add_argument("--demo-only", action="store_true",
                        help="Only the English demo trip (for extra reliability runs).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()
    if settings.demo_date is None:
        print("Set HEATSAFE_DEMO_DATE in .env to the demo day (YYYY-MM-DD).")
        return 1
    if default_client() is None:
        print("No AI key configured (OPENROUTER_API_KEY and HEATSAFE_MODEL).")
        return 1
    depart = f"{settings.demo_date.isoformat()}T15:30:00-07:00"

    log_records: list[logging.LogRecord] = []

    class Cap(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            log_records.append(record)

    rec_logger = logging.getLogger("heatsafe.recommend")
    rec_logger.setLevel(logging.INFO)
    rec_logger.addHandler(Cap())

    spy = SpyClient(default_client())
    app.dependency_overrides[llm_client] = lambda: spy
    ai_count = 0
    trip_count = 0
    latencies: list[float] = []
    try:
        with TestClient(app) as client:
            print(f"demo_day={settings.demo_date.isoformat()} depart=15:30 model_set=True")
            for _ in range(args.repeat):
                for i, (name, start, end, note_en) in enumerate(PAIRS, start=1):
                    if args.demo_only and i > 1:
                        continue
                    langs = ("en",) if args.demo_only else ("en", "es")
                    for lang in langs:
                        trip_count += 1
                        note = note_en if lang == "en" else (("(es) " + note_en) if note_en else "")
                        log_records.clear()
                        spy.last_raw = None
                        started = time.perf_counter()
                        try:
                            response = client.post("/api/trip", json={
                                "start": {"lat": start["lat"], "lon": start["lon"]},
                                "end": {"lat": end["lat"], "lon": end["lon"]},
                                "depart_at": depart, "note": note, "lang": lang,
                            })
                        except Exception as exc:  # noqa: BLE001
                            print(f"{trip_count}. {name} [{lang}] ERROR {type(exc).__name__}")
                            continue
                        elapsed = time.perf_counter() - started
                        latencies.append(elapsed)
                        if response.status_code != 200:
                            print(f"{trip_count}. {name} [{lang}] HTTP {response.status_code}: "
                                  f"{response.text[:160]}")
                            continue
                        data = response.json()
                        rec = data["recommendation"]
                        source = rec["source"]
                        ai_count += source == "ai"
                        reason = "-"
                        for record in reversed(log_records):
                            if record.getMessage().startswith("ai_fallback"):
                                reason = record.getMessage()
                                break
                        print(f"{trip_count}. {name} [{lang}] route={rec['route_id']} "
                              f"source={source} reason={reason} t={elapsed:.1f}s")
                        if source != "ai":
                            print(f"   ai_raw={str(spy.last_raw)[:400]}")
    finally:
        app.dependency_overrides.clear()
    print(f"AI_USE_RATE: {ai_count}/{trip_count}")
    if latencies:
        print(f"LATENCY_S: median={statistics.median(latencies):.1f} "
              f"max={max(latencies):.1f} n={len(latencies)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
