"""Pick a route and explain it in plain words.

The AI only chooses among routes we already scored, and its explanation is checked:
every number it writes must appear in the data we gave it. If anything goes wrong
(no key, slow, unknown route, invented number), a simple rule picks the route instead.
"""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Protocol

import httpx
from pydantic import BaseModel

from heatsafe.config import get_settings
from heatsafe.heat import ExposureLevel
from heatsafe.models import Lang, Recommendation, Route, Weather

TIMEOUT_S = 15.0
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
RETRY_RESERVE_S = 6.0
logger = logging.getLogger(__name__)
NUMBER = re.compile(r"\d+(?:[.:]\d+)?")
# In the AI's text, a decimal comma ("17,5" in Spanish) is read as a decimal point.
TEXT_NUMBER = re.compile(r"\d+(?:[.:,]\d+)?")
EXPOSURE_ORDER = list(ExposureLevel)

SYSTEM_PROMPT = """You help someone in Santa Ana, California choose a walking route on a hot day.
You get routes that were already measured: walking time, minutes in direct sun, percent shaded,
an estimated "feels like" temperature, an exposure rating, and places along the way.

Choose the one route that best protects the person from heat while respecting their note
(for example a train they must catch, something heavy they carry, or a health condition).
A route marked arrives_in_time=false misses their departure; avoid it if another route makes it.

Then explain the choice in 2 or 3 short, plain sentences, the way a friend would, and give
the same explanation in the other language as "translation".
Only use numbers that appear in the data. Do not invent facts, places, or advice.
Refer to routes by their label (fastest, shadiest, balanced, alternate), not by id."""

LANGUAGES = {"en": "English", "es": "Spanish (natural, everyday Spanish)"}


def language_instruction(lang: Lang) -> str:
    other = "es" if lang == "en" else "en"
    return f"Write the explanation in {LANGUAGES[lang]} and the translation in {LANGUAGES[other]}."


LABELS = {
    "en": {"fastest": "The fastest route", "shadiest": "The shadiest route",
           "balanced": "The balanced route", "alternate": "The alternate route"},
    "es": {"fastest": "La ruta más rápida", "shadiest": "La ruta con más sombra",
           "balanced": "La ruta equilibrada", "alternate": "La ruta alternativa"},
}
EXPOSURE_WORDS = {
    "en": {"low": "Low", "moderate": "Moderate", "high": "High", "extreme": "Extreme"},
    "es": {"low": "Baja", "moderate": "Moderada", "high": "Alta", "extreme": "Extrema"},
}
TEMPLATES = {
    "en": "{label} keeps you in shade for {shade_pct}% of the walk, with {sun_minutes} minutes "
          "in direct sun. Estimated heat exposure: {exposure}.",
    "es": "{label} te mantiene en la sombra el {shade_pct}% del camino, con {sun_minutes} "
          "minutos bajo el sol directo. Exposición al calor estimada: {exposure}.",
}


class Choice(BaseModel):
    route_id: str
    explanation: str
    translation: str


class LLMClient(Protocol):
    def choose(self, payload: dict, lang: Lang) -> dict: ...


class OpenRouterClient:
    def __init__(self, api_key: str, model: str, transport: httpx.BaseTransport | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self.transport = transport
        self.extras: dict = {"response_format": {"type": "json_object"}, "reasoning": {"effort": "low"}}

    def _body(self, payload: dict, language: str) -> dict:
        return {
            "model": self.model,
            # No default on OpenRouter: reserve enough for the answer or the credit
            # check rejects the request.
            "max_tokens": 2000,
            **self.extras,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"{language}\n\n"
                    'Reply with only JSON of the form '
                    '{"route_id": ..., "explanation": ..., "translation": ...}.\n\n'
                    f"{json.dumps(payload, ensure_ascii=False)}",
                },
            ],
        }

    def _drop_rejected_param(self, exc: httpx.HTTPStatusError) -> bool:
        """Drop a request param the model rejected (HTTP 400); True if one was dropped."""
        try:
            message = json.dumps(exc.response.json().get("error", ""))
        except ValueError:
            return False
        dropped = False
        for param in ("response_format", "reasoning"):
            if param in message and param in self.extras:
                del self.extras[param]
                dropped = True
        return dropped

    def _attempt(self, http: httpx.Client, payload: dict, language: str) -> dict:
        response = http.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=self._body(payload, language),
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400 and self._drop_rejected_param(exc):
                return self._attempt(http, payload, language)
            raise
        content = response.json()["choices"][0]["message"]["content"]
        return json.loads(content)

    def choose(self, payload: dict, lang: Lang) -> dict:
        language = language_instruction(lang)
        with httpx.Client(transport=self.transport, timeout=TIMEOUT_S) as http:
            started = time.monotonic()
            try:
                return self._attempt(http, payload, language)
            except json.JSONDecodeError:
                if time.monotonic() - started > TIMEOUT_S - RETRY_RESERVE_S:
                    raise
                return self._attempt(http, payload, language)


def build_payload(routes: list[Route], weather: Weather, note: str | None) -> dict:
    return {
        "note": note or "",
        "weather": {
            "temperature_f": weather.temp_f,
            "humidity_pct": weather.rel_humidity,
            "heat_index_f": round(weather.heat_index_f, 1),
            "time": weather.valid_at.strftime("%-I:%M %p"),
        },
        "routes": [
            {
                "id": r.id, "label": r.label, "walk_minutes": r.duration_min,
                "distance_m": r.distance_m, "sun_minutes": r.sun_minutes,
                "shade_pct": r.shade_pct, "feels_like_f": r.effective_heat_index_f,
                "exposure": r.exposure.value, "arrives_in_time": r.arrives_in_time,
                "minutes_to_spare": r.minutes_to_spare,
                "places_along_the_way": [
                    {"kind": a.amenity.kind, "name": a.amenity.name,
                     "meters_from_start": a.distance_along_m}
                    for a in r.amenities
                ],
            }
            for r in routes
        ],
    }


def allowed_numbers(value: object, found: set[str]) -> set[str]:
    if isinstance(value, bool) or value is None:
        return found
    if isinstance(value, (int, float)):
        found.update({str(value), str(round(value)), f"{value:.1f}", f"{value:.0f}"})
    elif isinstance(value, str):
        found.update(NUMBER.findall(value))
    elif isinstance(value, dict):
        for item in value.values():
            allowed_numbers(item, found)
    elif isinstance(value, list):
        for item in value:
            allowed_numbers(item, found)
    return found


def text_numbers(text: str) -> list[str]:
    return [token.replace(",", ".") for token in TEXT_NUMBER.findall(text)]


def ungrounded_tokens(text: str, payload: dict) -> list[str]:
    """Number tokens in the text that appear nowhere in the payload data."""
    allowed = allowed_numbers(payload, set())
    seen: list[str] = []
    for token in text_numbers(text):
        if token not in allowed and token not in seen:
            seen.append(token)
    return seen


def numbers_are_grounded(text: str, payload: dict) -> bool:
    allowed = allowed_numbers(payload, set())
    return all(token in allowed for token in text_numbers(text))


def fallback(routes: list[Route], lang: Lang) -> Recommendation:
    candidates = [r for r in routes if r.arrives_in_time is not False] or routes
    best = min(
        candidates,
        key=lambda r: (EXPOSURE_ORDER.index(r.exposure), r.sun_minutes, r.distance_m),
    )
    explanations: dict[Lang, str] = {
        language: TEMPLATES[language].format(
            label=LABELS[language][best.label], shade_pct=best.shade_pct,
            sun_minutes=best.sun_minutes, exposure=EXPOSURE_WORDS[language][best.exposure.value],
        )
        for language in ("en", "es")
    }
    return Recommendation(
        route_id=best.id, explanation=explanations[lang], lang=lang, source="fallback",
        explanations=explanations,
    )


def default_client() -> LLMClient | None:
    settings = get_settings()
    if settings.openrouter_api_key:
        if not settings.model:
            logger.warning(
                "OPENROUTER_API_KEY is set but HEATSAFE_MODEL is missing; using rule-based pick"
            )
            return None
        return OpenRouterClient(settings.openrouter_api_key, settings.model)
    return None


def recommend(
    routes: list[Route], weather: Weather, note: str | None, lang: Lang,
    client: LLMClient | None,
    timeout_s: float = TIMEOUT_S,
) -> Recommendation:
    if client is None:
        logger.info("ai_fallback reason=%s lang=%s", "no_client", lang)
        return fallback(routes, lang)
    payload = build_payload(routes, weather, note)
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        choice = pool.submit(client.choose, payload, lang).result(timeout=timeout_s)
    except FuturesTimeoutError:
        logger.info("ai_fallback reason=%s lang=%s", "timeout", lang)
        return fallback(routes, lang)
    except Exception:  # noqa: BLE001 - any AI failure falls back to the rule-based pick
        logger.info("ai_fallback reason=%s lang=%s", "error", lang)
        return fallback(routes, lang)
    finally:
        pool.shutdown(wait=False)
    valid_ids = {r.id for r in routes}
    explanation = str(choice.get("explanation", "")).strip()
    translation = str(choice.get("translation", "")).strip()
    both = f"{explanation} {translation}"
    if choice.get("route_id") not in valid_ids:
        reason = "unknown_route"
    elif not explanation or not translation:
        reason = "empty"
    elif not numbers_are_grounded(both, payload):
        reason = "ungrounded tokens=" + ",".join(ungrounded_tokens(both, payload))
    else:
        other: Lang = "es" if lang == "en" else "en"
        return Recommendation(
            route_id=choice["route_id"], explanation=explanation, lang=lang, source="ai",
            explanations={lang: explanation, other: translation},
        )
    logger.info("ai_fallback reason=%s lang=%s", reason, lang)
    return fallback(routes, lang)
