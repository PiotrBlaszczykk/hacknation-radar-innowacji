import httpx
import pytest

from app.services import decisions
from app.services.llm import LLMUnavailable


@pytest.fixture()
def codes(app, monkeypatch):
    """Podmienia wywołanie modelu: zwraca zadane prawdopodobieństwa w kolejności opcji."""
    answers = []

    def fake(state, instructions, options, timeout):
        return answers.pop(0)

    monkeypatch.setattr(decisions, "_ask_codes", fake)
    return answers


def test_choice_and_score(codes):
    codes += [[0.2, 0.7, 0.1], [0.0, 0.5, 0.5]]
    out = decisions.decide(
        "tekst",
        {
            "kind": {"type": "choice", "instructions": "?", "criteria": {"a": "A", "b": "B", "c": "C"}},
            "level": {"type": "score", "instructions": "?", "criteria": ["nisko", "średnio", "wysoko"]},
        },
    )
    assert out["kind"]["choice"] == "b"
    assert out["kind"]["confidence"] == 0.7
    assert out["kind"]["calibrated"] is False
    assert out["level"]["score"] == pytest.approx(1.5)
    assert out["level"]["probabilities"] == {"0": 0.0, "1": 0.5, "2": 0.5}


def test_noul_and_multi(codes):
    codes += [[0.9, 0.1], [0.8, 0.2], [0.6, 0.4], [0.1, 0.9]]
    assert decisions.decide_one("tekst", {"type": "noul", "instructions": "?"})["noul"] == 0.9

    multi = decisions.decide_one(
        "tekst", {"type": "multi", "instructions": "?", "criteria": {"x": "X", "y": "Y", "z": "Z"}, "max": 1}
    )
    assert multi["selected"] == ["x"]
    assert multi["probabilities"] == {"x": 0.8, "y": 0.6, "z": 0.1}


def test_validation(app):
    with pytest.raises(ValueError):
        decisions.decide("tekst", {"q": {"type": "esej", "instructions": "?"}})
    with pytest.raises(ValueError):
        decisions.decide("tekst", {"q": {"type": "choice", "instructions": "?", "criteria": [str(i) for i in range(21)]}})


def test_basal_serve_used_when_configured(app, monkeypatch):
    app.config["BASAL_URL"] = "http://basal.test"
    seen = {}

    def fake_post(url, json, timeout):
        seen["url"], seen["body"] = url, json
        body = {"model": "basal-2.0-4.5B", "answers": {"q": {"type": "noul", "noul": 0.8, "confidence": 0.8}}}
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    answer = decisions.decide_one("tekst", {"type": "noul", "instructions": "?"})
    assert seen["url"] == "http://basal.test/v1/systemone"
    assert seen["body"]["state"] == "tekst"
    assert answer["engine"] == "basal-serve:basal-2.0-4.5B"
    assert answer["calibrated"] is True


def test_falls_back_when_basal_serve_is_down(app, monkeypatch):
    app.config["BASAL_URL"] = "http://basal.test"

    def down(*args, **kwargs):
        raise httpx.ConnectError("brak połączenia")

    monkeypatch.setattr(httpx, "post", down)
    with pytest.raises(LLMUnavailable):
        # Serwer nie działa, więc pytanie idzie do silnika zastępczego, a ten w teście też nie ma modelu.
        decisions.decide_one("tekst", {"type": "noul", "instructions": "?"})
