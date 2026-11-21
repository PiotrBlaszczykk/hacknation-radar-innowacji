from copy import deepcopy

from sqlalchemy import select

from app.extensions import db
from app.models import Assessment, Innovation, User
from app.services import decisions, llm

SCORES = {"problem": 4, "nowosc": 2, "dowody": 5, "przenoszalnosc": 3, "wykonalnosc": 1, "wplyw": 4}


def stub_models(monkeypatch):
    calls = []

    def decide(state, questions):
        calls.append(("decisions", state))
        assert set(questions) == set(SCORES)
        assert all(q["type"] == "score" and len(q["criteria"]) == 6 for q in questions.values())
        answers = {}
        for key, score in SCORES.items():
            probabilities = dict.fromkeys(map(str, range(6)), 0.0)
            if score == 5:
                probabilities["5"] = 1.0
            else:
                probabilities[str(score)] = 0.8
                probabilities[str(score - 1)] = probabilities[str(score + 1)] = 0.1
            answers[key] = {
                "score": score,
                "confidence": max(probabilities.values()),
                "probabilities": probabilities,
                "engine": "test-engine",
                "calibrated": False,
            }
        return answers

    def explain(system, user, schema, *, temperature):
        calls.append(("llm", user))
        assert temperature == 0
        return {
            key: {
                "justification": "Fragment opisuje rozwiązanie.",
                "evidence": "Tanie czujniki jakości powietrza" if key == "problem" else "Wymyślony cytat",
            }
            for key in schema["required"]
        }

    monkeypatch.setattr(decisions, "decide", decide)
    monkeypatch.setattr(llm, "chat_json", explain)
    return calls


def test_criteria_weights_and_levels(client):
    response = client.get("/api/criteria")
    assert response.status_code == 200
    data = response.json
    assert data["version"]
    assert sum(c["weight"] for c in data["criteria"]) == 100
    assert {c["key"] for c in data["criteria"]} == set(SCORES)
    assert all(len(c["levels"]) == 6 and c["missing_question"] for c in data["criteria"])


def test_assessment_is_weighted_repeatable_and_saved(client, monkeypatch):
    calls = stub_models(monkeypatch)
    innovation = db.session.get(Innovation, 3)
    innovation.novelty = 0
    db.session.commit()

    assert client.get("/api/innovations/3/assessment").status_code == 404
    first = client.post("/api/innovations/3/assess")
    assert first.status_code == 200
    second = client.post("/api/innovations/3/assess").json
    assert first.json["total"] == second["total"] == 65
    assert first.json["id"] < second["id"]
    assert second["confidence"] == 0.84
    assert second["engine"] == "test-engine"
    assert second["calibrated"] is False
    assert client.get("/api/innovations/3/assessment").json == second
    assert [call[0] for call in calls] == ["decisions", "llm", "decisions", "llm"]
    assert "Świeżość wobec kart w Radarze: 0/100" in calls[0][1]
    assert second["items"][0]["evidence"] == "Tanie czujniki jakości powietrza"
    assert second["items"][1]["evidence"] is None

    updated = client.get("/api/innovations/3").json
    assert updated["score"] == 65
    assert updated["status"] == "oceniona"
    assert updated["events"][-1]["payload"]["assessment_id"] == second["id"]


def test_missing_results_are_neutral_and_lower_confidence(client, monkeypatch):
    stub_models(monkeypatch)
    created = client.post(
        "/api/innovations",
        json={"title": "Przykładowe zajęcia", "problem": "Mała frekwencja", "solution": "Praca w parach"},
    ).json
    assessment = client.post(f"/api/innovations/{created['id']}/assess").json
    evidence = next(item for item in assessment["items"] if item["key"] == "dowody")
    assert evidence["missing"] is True
    assert evidence["score"] == 2.5
    assert evidence["confidence"] == 0
    assert evidence["question"]
    assert assessment["total"] == 56.25
    assert assessment["confidence"] == 0.64


def test_empty_card_returns_neutral_total(client, monkeypatch):
    calls = stub_models(monkeypatch)
    created = client.post("/api/innovations", json={"title": "Przykładowa karta"}).json
    assessment = client.post(f"/api/innovations/{created['id']}/assess").json
    assert assessment["total"] == 50
    assert assessment["confidence"] == 0
    assert all(item["missing"] for item in assessment["items"])
    assert [call[0] for call in calls] == ["decisions"]


def test_broker_override_preserves_history_and_updates_total(client, monkeypatch):
    stub_models(monkeypatch)
    broker = db.session.scalar(select(User).where(User.role == "broker"))
    original = client.post("/api/innovations/3/assess").json
    original_items = deepcopy(original["items"])
    url = "/api/innovations/3/assessment/override"
    change = {"key": "problem", "score": 2.5, "justification": "Problem dotyczy jednego zastosowania."}
    assert client.post(url, json=change).status_code == 403

    headers = {"X-User-Id": str(broker.id)}
    assert client.post(url, json={**change, "score": True}, headers=headers).status_code == 400
    corrected = client.post(url, json=change, headers=headers)
    assert corrected.status_code == 200
    result = corrected.json
    assert result["id"] != original["id"]
    assert result["total"] == 59
    assert result["calibrated"] is False
    assert result["items"][0]["override"]["user_id"] == broker.id
    assert result["items"][0]["override"]["at"]
    assert result["items"][0]["justification"] == change["justification"]
    assert result["items"][0]["evidence"] is None
    assert result["items"][0]["confidence"] is None
    assert result["items"][1:] == original_items[1:]
    assert db.session.get(Assessment, original["id"]).items == original_items
    assert db.session.get(Assessment, result["id"]).assessor_id == broker.id
    innovation = client.get("/api/innovations/3").json
    assert innovation["score"] == 59
    event = innovation["events"][-1]
    assert event["type"] == "korekta_oceny"
    assert event["actor"] == broker.name
    assert event["payload"]["previous_assessment_id"] == original["id"]


def test_model_unavailability_returns_503_without_saving(client, monkeypatch):
    def unavailable(*args, **kwargs):
        raise llm.LLMUnavailable("test")

    for service, method in [(decisions, "decide"), (llm, "chat_json")]:
        stub_models(monkeypatch)
        monkeypatch.setattr(service, method, unavailable)
        response = client.post("/api/innovations/3/assess")
        assert response.status_code == 503
        assert "niedostępny" in response.json["error"]
        assert client.get("/api/innovations/3/assessment").status_code == 404
        assert client.get("/api/innovations/3").json["score"] is None


def test_cli_missing_saves_and_skips_already_assessed(app, client, monkeypatch):
    stub_models(monkeypatch)
    runner = app.test_cli_runner()
    first = runner.invoke(args=["assessments", "run", "--missing", "--limit", "1"])
    second = runner.invoke(args=["assessments", "run", "--missing", "--limit", "1"])
    assert first.exit_code == second.exit_code == 0
    assert "Innowacja 1 " in first.output
    assert "Innowacja 2 " in second.output
    assert client.get("/api/innovations/1/assessment").status_code == 200
    assert client.get("/api/innovations/2/assessment").status_code == 200
    assert client.get("/api/innovations/3/assessment").status_code == 404
