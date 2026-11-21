from copy import deepcopy

from sqlalchemy import select

from app.extensions import db
from app.models import Assessment, Innovation, User
from app.scoring import CRITERIA, LEGACY_REVIEW_THRESHOLD
from app.services import decisions, llm

EVIDENCE = "Zmierzono poprawę w 20 organizacjach względem grupy porównawczej."
SCORES = {"problem": 4, "nowosc": 2, "dowody": 5, "przenoszalnosc": 3, "wykonalnosc": 1, "wplyw": 4}


def stub_models(monkeypatch):
    calls = []

    def decide(state, questions):
        if questions.keys() <= SCORES.keys():
            calls.append(("passages", state))
            return {
                key: {"choice": "none" if key == "dowody" else "1", "engine": "test-engine", "calibrated": False}
                for key in questions
            }
        calls.append(("decisions", state))
        criterion = next(c for c in CRITERIA["criteria"] if questions.keys() == {p["key"] for p in c["checks"]})
        assert all(q["type"] == "choice" and len(q["criteria"]) == 3 for q in questions.values())
        target = SCORES[criterion["key"]]
        confirmed = {
            1: [0], 2: [1], 3: [0, 1], 4: [1, 2], 5: [0, 1, 2],
        }[target]
        answers = {}
        for index, key in enumerate(questions):
            status = "confirmed" if index in confirmed else "denied"
            probabilities = dict.fromkeys(("confirmed", "denied", "unknown"), 0.05)
            probabilities[status] = 0.9
            answers[key] = {
                "choice": status,
                "confidence": 0.9,
                "probabilities": probabilities,
                "engine": "test-engine",
                "calibrated": False,
            }
        return answers

    innovation = db.session.get(Innovation, 3)
    innovation.problem = innovation.solution = innovation.results = EVIDENCE
    db.session.commit()
    monkeypatch.setattr(decisions, "decide", decide)
    return calls


def test_criteria_weights_and_checks(client):
    response = client.get("/api/criteria")
    assert response.status_code == 200
    data = response.json
    assert data["version"]
    assert sum(c["weight"] for c in data["criteria"]) == 100
    assert {c["key"] for c in data["criteria"]} == set(SCORES)
    assert all(sum(p["points"] for p in c["checks"]) == 5 and c["missing_question"] for c in data["criteria"])


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
    assert second["confidence"] == 0.9
    assert second["engine"] == "test-engine"
    assert second["calibrated"] is False
    assert client.get("/api/innovations/3/assessment").json == second
    assert [call[0] for call in calls] == ["decisions"] * 12
    assert second["items"][0]["evidence"] == innovation.problem
    assert second["items"][0]["checks"][0]["status"] == "denied"
    assert second["items"][0]["checks"][1]["status"] == "confirmed"

    updated = client.get("/api/innovations/3").json
    assert updated["score"] == 65
    assert updated["status"] == "oceniona"
    assert updated["events"][-1]["payload"]["assessment_id"] == second["id"]


def test_missing_results_are_neutral_and_lower_confidence(client, monkeypatch):
    stub_models(monkeypatch)
    created = client.post(
        "/api/innovations",
        json={"title": "Przykładowe zajęcia", "problem": EVIDENCE, "solution": EVIDENCE},
    ).json
    assessment = client.post(f"/api/innovations/{created['id']}/assess").json
    evidence = next(item for item in assessment["items"] if item["key"] == "dowody")
    assert evidence["missing"] is True
    assert evidence["score"] == 2.5
    assert evidence["confidence"] == 0
    assert evidence["question"]
    assert assessment["total"] == 56.25
    assert assessment["confidence"] == 0.72
    assert assessment["scored_weight"] == 80
    assert assessment["needs_review"] is True


def test_empty_card_returns_neutral_total(client, monkeypatch):
    calls = stub_models(monkeypatch)
    created = client.post("/api/innovations", json={"title": "Przykładowa karta"}).json
    assessment = client.post(f"/api/innovations/{created['id']}/assess").json
    assert assessment["total"] == 50
    assert assessment["confidence"] == 0
    assert all(item["missing"] for item in assessment["items"])
    assert calls == []
    assert assessment["has_score"] is False
    assert client.get(f"/api/innovations/{created['id']}").json["score"] is None


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
    assert "checks" not in result["items"][0]
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

    monkeypatch.setattr(decisions, "decide", unavailable)
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


def test_unmatched_candidate_cannot_confirm_a_check(client, monkeypatch):
    calls = []

    def select_passage(state, questions):
        calls.append("passages")
        assert len(questions) == 6
        return {
            key: {"choice": "brak-takiej-opcji", "engine": "test-engine", "calibrated": False}
            for key in questions
        }

    monkeypatch.setattr(decisions, "decide", select_passage)
    innovation = db.session.get(Innovation, 3)
    innovation.origin = "radar"
    innovation.claimed = False
    db.session.commit()
    response = client.post("/api/innovations/3/assess")
    assert response.status_code == 200
    assert calls == ["passages"]
    assert all(p["status"] == "unknown" for item in response.json["items"] for p in item["checks"])


def test_legacy_assessment_can_still_be_corrected(client):
    item = {"key": "problem", "label": "Waga problemu", "weight": 20, "score": 3.25,
            "missing": False, "confidence": 0.5}
    db.session.add(Assessment(
        innovation_id=3, criteria_version="1.1", engine="test-old", items=[item],
        total=65, confidence=0.5,
    ))
    db.session.commit()
    url = "/api/innovations/3/assessment"
    assert client.get(url).json["review_threshold"] == LEGACY_REVIEW_THRESHOLD
    broker = db.session.scalar(select(User).where(User.role == "broker"))
    result = client.post(f"{url}/override", headers={"X-User-Id": str(broker.id)},
                         json={"key": "problem", "score": 4, "justification": "Udokumentowany zasięg."})
    assert result.status_code == 200
    assert result.json["criteria_version"] == "1.1"
    assert result.json["total"] == 80


def test_numbers_and_comparison_in_a_plan_do_not_count_as_results(client, monkeypatch):
    stub_models(monkeypatch)
    innovation = db.session.get(Innovation, 3)
    innovation.results = "Planujemy test w 20 instytucjach i pomiar zmiany względem grupy porównawczej."
    db.session.commit()

    result = client.post("/api/innovations/3/assess").json
    proof = next(item for item in result["items"] if item["key"] == "dowody")
    assert proof["missing"] is True
    assert all(check["status"] == "unknown" for check in proof["checks"])
    assert all(check["evidence"] is None for check in proof["checks"])
