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
            "questions": [
                "Ile wiertarek wypożyczono na kartę w pierwszym miesiącu?",
                "Czy możesz coś więcej powiedzieć o wiertarkach?",
                "Jak często jest to sprawdzane?",
                "ILE WIERTAREK WYPOŻYCZONO NA KARTĘ W PIERWSZYM MIESIĄCU?",
                "Kto odpowiada za naprawy wiertarek po zwrocie?",
            ],
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
    assert body["questions"] == [
        "Ile wiertarek wypożyczono na kartę w pierwszym miesiącu?",
        "Kto odpowiada za naprawy wiertarek po zwrocie?",
    ]
    assert model_answers[1][2]["properties"]["questions"]["type"] == "array"
    assert body["version"] == structuring.STRUCTURING_VERSION == "2"
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


def test_follow_up_repairs_empty_or_answered_questions(client, model_answers, monkeypatch):
    def chat(system, source, schema, **kwargs):
        if schema["required"] == ["question"]:
            return {"question": "Kto odpowiada za naprawy wiertarek po zwrocie?"}
        return {
            "solution": "Wypożyczamy wiertarki na kartę.",
            "questions": ["Czy wypożyczamy wiertarki na kartę?"],
        }

    monkeypatch.setattr(llm, "chat_json", chat)
    response = client.post("/api/structure", json={"text": TEXT})
    assert response.status_code == 200
    assert response.get_json()["questions"] == ["Kto odpowiada za naprawy wiertarek po zwrocie?"]


@pytest.mark.parametrize("draft_claim", [
    "Liczba pism spadła o 1/3, a sprawy załatwiamy średnio o cztery dni szybciej.",
    "Liczba pism wzrosła o 84%, a sprawy załatwiamy średnio o 4 godziny wolniej.",
    "Liczba pism wzrosła o połowę, a sprawy załatwiamy o 4 dni wolniej.",
])
def test_changed_or_unsupported_numbers_are_recovered_from_source(client, model_answers, monkeypatch, draft_claim):
    mechanism = "W urzędzie gminy wprowadziliśmy dyżur telefoniczny dla sołtysów."
    problem = "Wcześniej każde zgłoszenie wymagało osobnego pisma."
    observed = "Po wdrożeniu liczba pism spadła o jedną trzecią, a sprawy załatwiamy średnio o 4 dni szybciej."
    monkeypatch.setattr(llm, "chat_json", lambda *args, **kwargs: {
        "summary": f"{mechanism} {draft_claim}",
        "solution": mechanism,
        "results": draft_claim,
        "questions": ["Przez jaki okres porównywano liczbę pism i czas obsługi sołtysów?"],
    })

    response = client.post("/api/structure", json={"text": f"{mechanism} {problem} {observed}"})
    assert response.status_code == 200
    result = response.get_json()
    assert result["card"]["problem"] == problem
    assert result["card"]["results"] == observed
    assert result["card"]["summary"] == f"{mechanism} {observed}"
    assert not {"summary", "problem", "results"}.intersection(result["missing"])
    assert len(result["questions"]) == 1


@pytest.mark.parametrize(("source", "results_draft", "expected"), [
    ("W godzinach pracy czas oczekiwania nie zmienił się i wynosi 12 min.",
     "Czas oczekiwania zmalał do 12 min.",
     "W godzinach pracy czas oczekiwania nie zmienił się i wynosi 12 min."),
    ("W pomiarze błąd zmalał o 0,8 punktu procentowego, a zespół planuje skrócić kalibrację do 2 minut.",
     "Błąd zmalał o 0.8%, a kalibracja trwa 2 minuty.",
     "W pomiarze błąd zmalał o 0,8 punktu procentowego"),
    ("Naszym celem jest skrócenie kalibracji do 2 minut. Nie zebrano jeszcze wyników.",
     "Skrócenie kalibracji do 2 minut.", ""),
    ("Cel projektu:\nSkrócenie kalibracji do 2 minut.",
     "Skrócenie kalibracji do 2 minut.", ""),
    ("Do tej pory odnotowaliśmy 158 wypożyczeń (67K odsłon strony).",
     "Odnotowano 67000 wypożyczeń.",
     "Do tej pory odnotowaliśmy 158 wypożyczeń (67K odsłon strony)."),
])
def test_results_preserve_units_and_exclude_goals(app, model_answers, monkeypatch, source, results_draft, expected):
    monkeypatch.setattr(llm, "chat_json", lambda *args, **kwargs: {"results": results_draft})
    result = structuring.structure_text(f"{TEXT} {source}")
    assert result["card"]["results"] == expected
    assert ("results" in result["missing"]) == (not expected)
    assert result["questions"] == []


def test_planned_target_is_retained_alongside_measured_outcome(app, model_answers, monkeypatch):
    measured = "W teście błąd pomiaru zmalał o 0,8 punktu procentowego."
    planned = "Zespół planuje skrócić kalibrację do 2 minut."
    monkeypatch.setattr(llm, "chat_json", lambda *args, **kwargs: {
        "results": "Błąd zmniejszył się o 0.8%, a kalibracja trwa 2 minuty."
    })
    result = structuring.structure_text(
        f"Czujnik optyczny koryguje pomiar wilgotności. {measured} {planned}"
    )
    assert result["card"]["results"] == measured
    assert planned in result["card"]["solution"]


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


def test_library_keeps_explicit_waiting_problem_and_observed_result(client, model_answers, monkeypatch):
    problem = "W bibliotece gminnej czytelnicy długo czekali na odbiór rezerwacji."
    result = "W ciągu sześciu tygodni czas oczekiwania spadł z 18 do 7 minut."
    source = (
        f"{problem} Uruchomiliśmy samoobsługową półkę z kodami odbioru. {result} "
        "W następnym kwartale chcemy objąć pilotażem jeszcze 3 filie."
    )
    monkeypatch.setattr(llm, "chat_json", lambda *args, **kwargs: {"problem": "", "results": "Oszczędność 11 minut."})
    response = client.post("/api/structure", json={"text": source})
    assert response.status_code == 200
    assert response.json["card"]["problem"] == problem
    assert response.json["card"]["results"] == result


def test_structure_distinguishes_missing_signal_from_zero(client, monkeypatch):
    monkeypatch.setattr(decisions, "decide", lambda *args: {})
    monkeypatch.setattr(llm, "chat_json", lambda *args, **kwargs: {})
    response = client.post("/api/structure", json={"text": TEXT})
    assert response.status_code == 200
    assert response.json["is_innovation"] is None
