import pytest

from app.services import decisions, llm, structuring

TEXT = "W bibliotece wypożyczamy wiertarki na kartę, tak jak książki."


@pytest.fixture
def model_answers(monkeypatch):
    calls = []

    def decide(state, questions):
        calls.append(("tags", state, questions))
        return {
            "kind": {
                "choice": "organizacyjna",
                "confidence": 0.59,
                "probabilities": {"organizacyjna": 0.59, "procesowa": 0.41, "literowka": 1},
                "engine": "model-tagi",
            },
            "stage": {"choice": "niedozwolony", "confidence": 0.99},
            "domains": {
                "selected": ["kultura", "niedozwolony", "kultura", "jakosc_zycia"],
                "confidence": 0.43,
                "probabilities": {"kultura": 0.91, "jakosc_zycia": 0.62, "niedozwolony": 1},
            },
            "support_needs": {"selected": ["niedozwolony"], "confidence": 0.9},
            "is_innovation": {"noul": 0.87, "engine": "model-tagi"},
        }

    def chat(system, source, schema, **kwargs):
        calls.append(("text", source, schema))
        assert kwargs["temperature"] == 0
        return {
            "title": "Brak",
            "summary": "Biblioteka wypożycza narzędzia. " * 40,
            "problem": "  „BRAK.” ",
            "solution": "Wypożyczenie wiertarki na kartę biblioteczną.",
            "results": "Brak informacji o wynikach.",
            "keywords": ["n/d", "  narzędzia  ", "narzędzia", "biblioteka"],
            "questions": {
                "results": "Ile wiertarek wypożyczono na kartę w pierwszym miesiącu?",
                "problem": "Czy możesz coś więcej o tym powiedzieć?",
                "solution": "Jaką kartę musi pokazać osoba wypożyczająca narzędzia?",
            },
        }

    monkeypatch.setattr(decisions, "decide", decide)
    monkeypatch.setattr(llm, "chat_json", chat)
    return calls


def test_structure_validates_proposals_and_reports_missing(client, model_answers):
    response = client.post("/api/structure", json={"text": TEXT})
    assert response.status_code == 200
    body = response.get_json()
    card = body["card"]
    assert card["title"] == TEXT
    assert 1 < len(card["summary"]) <= 320
    assert card["problem"] == card["results"] == ""
    assert card["keywords"] == ["narzędzia", "biblioteka"]
    assert card["kind"] == "organizacyjna"
    assert card["stage"] is None
    assert card["domains"] == ["kultura", "jakosc_zycia"]
    assert card["support_needs"] == []
    assert set(body["missing"]) == {"title", "problem", "results", "stage", "support_needs"}
    assert body["questions"][0] == "Ile wiertarek wypożyczono na kartę w pierwszym miesiącu?"
    assert body["questions"][1].startswith("Do jakich prac mieszkańcy potrzebują narzędzi")
    assert len(body["questions"]) == 3
    assert all(q.endswith("?") for q in body["questions"])
    assert not any("pokazać" in q for q in body["questions"])
    assert body["tags"]["kind"] == {
        "value": "organizacyjna",
        "confidence": 0.59,
        "probabilities": {"organizacyjna": 0.59, "procesowa": 0.41},
    }
    assert body["tags"]["domains"]["probabilities"] == {"kultura": 0.91, "jakosc_zycia": 0.62}
    assert body["is_innovation"] == 0.87
    assert body["engine"]["tags"] == "model-tagi"
    assert body["engine"]["text"]
    assert [call[0] for call in model_answers] == ["tags", "text"]
    assert {key: q["type"] for key, q in model_answers[0][2].items()} == {
        "kind": "choice", "stage": "choice", "domains": "multi", "support_needs": "multi",
        "is_innovation": "noul",
    }


def test_long_text_fits_model_budget(app, model_answers):
    source = "żółć 🧩 " * 2000
    card = structuring.structure_text(source)["card"]
    tags_input = model_answers[0][1]
    assert 0 < len(tags_input.encode("utf-8")) < 3000
    assert source.startswith(tags_input) and tags_input == model_answers[1][1]
    assert card["title"]


@pytest.mark.parametrize("text", [None, 42, "  krótki tekst       ", " " * 200, "x" * 39])
def test_short_or_invalid_text_returns_400(client, text):
    response = client.post("/api/structure", json={"text": text})
    assert response.status_code == 400
    assert "40 znaków" in response.get_json()["error"]


def test_unavailable_decision_engine_returns_503(client):
    response = client.post("/api/structure", json={"text": TEXT})
    assert response.status_code == 503
    assert "ręcznie" in response.get_json()["error"]


def test_unavailable_text_engine_returns_503(client, monkeypatch):
    monkeypatch.setattr(decisions, "decide", lambda *_: {})
    response = client.post("/api/structure", json={"text": TEXT})
    assert response.status_code == 503
    assert "ręcznie" in response.get_json()["error"]


@pytest.mark.parametrize("repaired_summary", ["Wypożyczono 67000 wiertarek.", "Biblioteka wypożycza wiertarki."])
def test_number_missing_from_source_triggers_summary_repair(app, model_answers, monkeypatch, repaired_summary):
    def chat(system, source, schema, **kwargs):
        if schema["required"] == ["summary"]:
            assert not any(number in source for number in ("158", "67"))
            return {"summary": repaired_summary}
        return {"summary": "Wypożyczono 67,000 wiertarek.", "results": "Odnotowano 158 wypożyczeń."}

    monkeypatch.setattr(llm, "chat_json", chat)
    result = structuring.structure_text(TEXT + " Do tej pory odnotowaliśmy 158 wypożyczeń (67K).")
    expected = "" if "67000" in repaired_summary else repaired_summary
    assert result["card"]["summary"] == expected
    assert ("summary" in result["missing"]) == (not expected)
    assert result["card"]["results"] == "Odnotowano 158 wypożyczeń."


def test_multi_thresholds_follow_the_active_engine():
    def answer(calibrated):
        return {
            "domains": {
                "selected": ["kultura", "jakosc_zycia", "edukacja"],
                "probabilities": {"kultura": 0.95, "jakosc_zycia": 0.87, "edukacja": 0.62},
                "calibrated": calibrated,
            },
        }

    basal = structuring._extract_tags(answer(True))["domains"]
    fallback = structuring._extract_tags(answer(False))["domains"]
    assert basal["value"] == ["kultura", "jakosc_zycia", "edukacja"]
    assert basal["confidence"] == 0.62
    assert fallback["value"] == ["kultura", "jakosc_zycia"]
    assert fallback["confidence"] == 0.87
