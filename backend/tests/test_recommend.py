from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from heatsafe.heat import ExposureLevel
from heatsafe.models import Route, Weather
from heatsafe.recommend import fallback, numbers_are_grounded, recommend

LA = ZoneInfo("America/Los_Angeles")
WEATHER = Weather(
    temp_f=105.7, rel_humidity=24, heat_index_f=108.1,
    valid_at=datetime(2026, 9, 9, 16, 0, tzinfo=LA), source="Open-Meteo",
    source_url="https://open-meteo.com/",
)


def make_route(route_id: str, label: str, shade: int, sun: float, exposure: ExposureLevel,
               on_time: bool | None = None) -> Route:
    return Route(
        id=route_id, label=label, distance_m=1348.1, duration_min=17.3, sun_minutes=sun,
        shade_pct=shade, effective_heat_index_f=119.2, exposure=exposure, segments=[],
        amenities=[], arrives_in_time=on_time, minutes_to_spare=None,
    )


FASTEST = make_route("r0", "fastest", 26, 12.8, ExposureLevel.extreme)
SHADIEST = make_route("r1", "shadiest", 44, 10.0, ExposureLevel.high)
ROUTES = [FASTEST, SHADIEST]


class FakeClient:
    def __init__(self, reply: dict | None = None, error: Exception | None = None) -> None:
        self.reply, self.error = reply, error

    def choose(self, payload: dict, lang: str) -> dict:
        if self.error:
            raise self.error
        return self.reply


def test_valid_ai_choice_passes_through() -> None:
    client = FakeClient({"route_id": "r1", "explanation": "Route r1 keeps you in shade for 44% of the walk.",
                         "translation": "La ruta r1 te mantiene en la sombra el 44% del camino."})
    result = recommend(ROUTES, WEATHER, None, "en", client)
    assert result.route_id == "r1"
    assert result.source == "ai"


def test_unknown_route_id_falls_back() -> None:
    client = FakeClient({"route_id": "r9", "explanation": "Take r9."})
    assert recommend(ROUTES, WEATHER, None, "en", client).source == "fallback"


def test_ungrounded_number_falls_back() -> None:
    client = FakeClient({"route_id": "r1", "explanation": "It is 82% shaded."})
    assert recommend(ROUTES, WEATHER, None, "en", client).source == "fallback"


def test_client_exception_falls_back() -> None:
    client = FakeClient(error=TimeoutError("slow"))
    result = recommend(ROUTES, WEATHER, None, "en", client)
    assert result.source == "fallback"
    assert result.route_id == "r1"


def test_fallback_prefers_on_time_route() -> None:
    late_shady = make_route("r1", "shadiest", 44, 10.0, ExposureLevel.high, on_time=False)
    on_time_fast = make_route("r0", "fastest", 26, 12.8, ExposureLevel.extreme, on_time=True)
    assert fallback([on_time_fast, late_shady], "en").route_id == "r0"


def test_fallback_spanish_template() -> None:
    result = fallback(ROUTES, "es")
    assert result.lang == "es"
    assert "sombra" in result.explanation


def test_times_from_note_count_as_grounded() -> None:
    assert numbers_are_grounded("You will make the 3:52 train.", {"note": "need the 3:52 train"})


def test_slow_client_falls_back_within_deadline() -> None:
    import time

    class SlowClient:
        def choose(self, payload: dict, lang: str) -> dict:
            time.sleep(2)
            return {"route_id": "r1", "explanation": "ok"}

    started = time.monotonic()
    result = recommend(ROUTES, WEATHER, None, "en", SlowClient(), timeout_s=0.2)
    assert result.source == "fallback"
    assert time.monotonic() - started < 1.0


def openrouter_transport(content: str, status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://openrouter.ai/api/v1/chat/completions"
        return httpx.Response(status, json={
            "id": "gen-recorded-shape",
            "choices": [{
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }],
        })

    return httpx.MockTransport(handler)


def test_openrouter_valid_choice() -> None:
    from heatsafe.recommend import OpenRouterClient

    body = ('{"route_id": "r1", "explanation": "The shadiest route keeps you in shade for 44% of the walk.", '
            '"translation": "La ruta con más sombra te mantiene en la sombra el 44% del camino."}')
    client = OpenRouterClient("test-key", "test-model", openrouter_transport(body))
    result = recommend(ROUTES, WEATHER, None, "en", client)
    assert result.source == "ai"
    assert result.route_id == "r1"


def test_openrouter_malformed_json_falls_back() -> None:
    from heatsafe.recommend import OpenRouterClient

    client = OpenRouterClient("test-key", "test-model", openrouter_transport("not json{{{"))
    assert recommend(ROUTES, WEATHER, None, "en", client).source == "fallback"


def test_openrouter_http_error_falls_back() -> None:
    from heatsafe.recommend import OpenRouterClient

    client = OpenRouterClient("test-key", "test-model", openrouter_transport("{}", status=401))
    assert recommend(ROUTES, WEATHER, None, "en", client).source == "fallback"


def test_default_client_uses_openrouter(monkeypatch) -> None:
    from heatsafe import recommend as recommend_module
    from heatsafe.config import Settings
    from heatsafe.recommend import OpenRouterClient, default_client

    monkeypatch.setattr(
        recommend_module, "get_settings",
        lambda: Settings(openrouter_api_key="openrouter-key", model="test-model"),
    )
    assert isinstance(default_client(), OpenRouterClient)


def test_openrouter_without_model_uses_rule(monkeypatch, caplog) -> None:
    from heatsafe import recommend as recommend_module
    from heatsafe.config import Settings
    from heatsafe.recommend import default_client

    monkeypatch.setattr(
        recommend_module, "get_settings",
        lambda: Settings(openrouter_api_key="openrouter-key", model=""),
    )
    with caplog.at_level("WARNING"):
        assert default_client() is None
    assert "HEATSAFE_MODEL" in caplog.text


def test_fallback_reason_is_logged(caplog) -> None:
    bad = FakeClient({"route_id": "r1", "explanation": "It is 82% shaded.", "translation": "Tiene 82% de sombra."})
    with caplog.at_level("INFO", logger="heatsafe.recommend"):
        assert recommend(ROUTES, WEATHER, None, "en", bad).source == "fallback"
    assert "ai_fallback reason=ungrounded" in caplog.text
    assert "82" in caplog.text
    assert "lang=en" in caplog.text


def test_other_fallback_reasons_are_logged(caplog) -> None:
    import time

    class SlowClient:
        def choose(self, payload: dict, lang: str) -> dict:
            time.sleep(2)
            return {"route_id": "r1", "explanation": "ok"}

    cases = [
        (FakeClient({"route_id": "r9", "explanation": "Take r9."}), "unknown_route"),
        (FakeClient({"route_id": "r1", "explanation": "   "}), "empty"),
        (FakeClient(error=ValueError("boom")), "error"),
    ]
    with caplog.at_level("INFO", logger="heatsafe.recommend"):
        for client, reason in cases:
            caplog.clear()
            assert recommend(ROUTES, WEATHER, None, "es", client).source == "fallback"
            assert f"ai_fallback reason={reason} lang=es" in caplog.text
        caplog.clear()
        result = recommend(ROUTES, WEATHER, None, "en", SlowClient(), timeout_s=0.2)
        assert result.source == "fallback"
        assert "ai_fallback reason=timeout lang=en" in caplog.text


def test_openrouter_requires_explicit_model(monkeypatch, caplog) -> None:
    from heatsafe import recommend as recommend_module
    from heatsafe.config import Settings
    from heatsafe.recommend import default_client

    monkeypatch.delenv("HEATSAFE_MODEL", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-key")
    monkeypatch.setattr(recommend_module, "get_settings", lambda: Settings(_env_file=None))
    with caplog.at_level("WARNING", logger="heatsafe.recommend"):
        assert default_client() is None
    assert "HEATSAFE_MODEL" in caplog.text


def test_no_client_logs_no_client_reason(caplog) -> None:
    with caplog.at_level("INFO", logger="heatsafe.recommend"):
        assert recommend(ROUTES, WEATHER, None, "en", None).source == "fallback"
    assert "ai_fallback reason=no_client lang=en" in caplog.text


VALID_BODY = '{"route_id": "r1", "explanation": "The shadiest route keeps you in shade for 44% of the walk."}'


def test_openrouter_requests_json_mode() -> None:
    import json as jsonlib

    from heatsafe.recommend import OpenRouterClient

    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(jsonlib.loads(request.content.decode()))
        return httpx.Response(200, json={"choices": [{"message": {
            "role": "assistant", "content": VALID_BODY}}]})

    client = OpenRouterClient("test-key", "test-model", httpx.MockTransport(handler))
    assert client.choose({"routes": []}, "en") == jsonlib.loads(VALID_BODY)
    assert seen[0]["response_format"] == {"type": "json_object"}
    assert seen[0]["reasoning"] == {"effort": "low"}


def test_openrouter_retries_once_on_truncated_json() -> None:
    from heatsafe.recommend import OpenRouterClient

    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        content = VALID_BODY if len(calls) > 1 else '{"route_id": "r1", "explan'
        return httpx.Response(200, json={"choices": [{"message": {
            "role": "assistant", "content": content}}]})

    client = OpenRouterClient("test-key", "test-model", httpx.MockTransport(handler))
    result = client.choose({"routes": []}, "en")
    assert result["route_id"] == "r1"
    assert len(calls) == 2


def test_openrouter_no_retry_on_http_error() -> None:
    from heatsafe.recommend import OpenRouterClient

    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(500, json={"error": {"message": "busy"}})

    client = OpenRouterClient("test-key", "test-model", httpx.MockTransport(handler))
    try:
        client.choose({"routes": []}, "en")
    except httpx.HTTPStatusError:
        pass
    else:
        raise AssertionError("expected HTTPStatusError")
    assert len(calls) == 1


def test_ai_reason_comes_in_both_languages() -> None:
    client = FakeClient({"route_id": "r1", "explanation": "La ruta con más sombra tiene 44% de sombra.",
                         "translation": "The shadiest route is 44% shaded."})
    result = recommend(ROUTES, WEATHER, None, "es", client)
    assert result.source == "ai"
    assert result.explanation == "La ruta con más sombra tiene 44% de sombra."
    assert result.explanations == {"es": "La ruta con más sombra tiene 44% de sombra.",
                                   "en": "The shadiest route is 44% shaded."}


def test_missing_translation_falls_back() -> None:
    client = FakeClient({"route_id": "r1", "explanation": "The shadiest route is 44% shaded."})
    assert recommend(ROUTES, WEATHER, None, "en", client).source == "fallback"


def test_translation_with_made_up_number_falls_back() -> None:
    client = FakeClient({"route_id": "r1", "explanation": "The shadiest route is 44% shaded.",
                         "translation": "La ruta con más sombra tiene 82% de sombra."})
    assert recommend(ROUTES, WEATHER, None, "en", client).source == "fallback"


def test_rule_pick_comes_in_both_languages() -> None:
    result = fallback(ROUTES, "en")
    assert "shade" in result.explanations["en"]
    assert "sombra" in result.explanations["es"]
    assert result.explanation == result.explanations["en"]


def test_spanish_decimal_comma_counts_as_grounded() -> None:
    payload = {"routes": [{"walk_minutes": 17.5, "shade_pct": 48}]}
    assert numbers_are_grounded("Tarda 17,5 minutos con 48% de sombra.", payload)
    assert not numbers_are_grounded("Tarda 17,9 minutos.", payload)
