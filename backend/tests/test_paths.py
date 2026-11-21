from datetime import date

import pytest
from sqlalchemy import func, select

from app.extensions import db
from app.models import Assessment, Event, Innovation, Organization, Recommendation, User
from app.paths import ACCEPTED
from app.paths.plans import plan_for
from app.services import decisions


def _generate(client, innovation_id):
    response = client.post(f"/api/innovations/{innovation_id}/recommend")
    assert response.status_code == 200
    return response.json


@pytest.mark.parametrize(("innovation_id", "path"), [
    (1, "wdrozenie"), (2, "wdrozenie"), (3, "transfer"),
    (4, "wdrozenie"), (5, "wdrozenie"), (6, "rozwoj"),
])
def test_seed_paths_without_assessment_or_models(client, innovation_id, path):
    assert client.get(f"/api/innovations/{innovation_id}/recommendation").status_code == 404
    result = _generate(client, innovation_id)

    assert result["path"] == db.session.get(Innovation, innovation_id).path == path
    assert result["engine"] == "reguly"
    assert result["reasons"]
    assert result["alternative"]["path"] != path
    assert result["alternative"]["reason"]
    assert 3 <= len(result["steps"]) <= 5
    assert 2 <= len(result["metrics"]) <= 4
    assert client.get(f"/api/innovations/{innovation_id}/recommendation").json == result
    event = db.session.scalar(select(Event).where(
        Event.innovation_id == innovation_id, Event.type == "rekomendacja",
    ))
    assert event.payload["reasons"] == result["reasons"]


def test_idea_without_results_and_mature_business_technology(client):
    company = db.session.scalar(select(Organization).where(Organization.kind == "firma"))
    idea = Innovation(title="Pomysł", kind="spoleczna", stage="pomysl")
    product = Innovation(
        title="Produkt firmy", kind="technologiczna", stage="wdrozona",
        organization=company, results="Przetestowano u 5 klientów.",
    )
    db.session.add_all([idea, product])
    db.session.commit()

    assert _generate(client, idea.id)["path"] == "rozwoj"
    result = _generate(client, product.id)
    assert result["path"] == "komercjalizacja"
    assert any("PARP" in (step["instrument"] or "") for step in result["steps"])


def test_latest_assessment_uses_criteria_and_ignores_missing(client):
    db.session.add_all([
        Assessment(
            innovation_id=1, engine="czlowiek", criteria_version="test", total=25,
            items=[{"key": "dowody", "score": 1}],
        ),
        Assessment(
            innovation_id=1, engine="czlowiek", criteria_version="test", total=80,
            items=[{"key": "dowody", "score": 4}, {"key": "przenoszalnosc", "score": 5, "missing": True}],
        ),
    ])
    db.session.commit()

    messages = [reason["message"] for reason in _generate(client, 1)["reasons"]]
    assert any("Ocena dowodów działania wynosi co najmniej 4" in msg for msg in messages)
    assert not any("słabe dowody" in msg or "przenoszalności" in msg for msg in messages)


def test_close_scores_fall_back_then_store_model_choice(client, monkeypatch):
    company = db.session.scalar(select(Organization).where(Organization.kind == "firma"))
    prototype = Innovation(
        title="Prototyp", kind="technologiczna", stage="prototyp",
        organization=company, results="Przetestowano na stanowisku.",
    )
    db.session.add(prototype)
    db.session.commit()

    first = _generate(client, prototype.id)
    assert first["path"] == "rozwoj"
    assert first["engine"] == "reguly"

    def choose(state, question, **_):
        assert "Przetestowano na stanowisku." in state
        assert question["type"] == "choice"
        assert set(question["criteria"]) == {"rozwoj", "komercjalizacja"}
        return {
            "choice": "komercjalizacja", "probabilities": {"rozwoj": 0.2, "komercjalizacja": 0.8},
            "engine": "test-model", "confidence": 0.8, "calibrated": False,
        }

    monkeypatch.setattr(decisions, "decide_one", choose)
    result = _generate(client, prototype.id)
    assert result["id"] > first["id"]
    assert result["path"] == "komercjalizacja"
    assert result["alternative"]["path"] == "rozwoj"
    assert result["engine"] == "test-model"
    assert result["reasons"][-1]["probabilities"] == {"rozwoj": 0.2, "komercjalizacja": 0.8}


def test_catalog_and_instrument_fit(client):
    catalog = client.get("/api/instruments").json
    assert 10 <= catalog["total"] == len(catalog["items"]) <= 15
    assert len({item["id"] for item in catalog["items"]}) == catalog["total"]
    for item in catalog["items"]:
        assert item["url"].startswith("https://")
        assert type(item["verified"]) is bool
        assert date.fromisoformat(item["checked_at"])
        assert all(item[field] for field in (
            "name", "provider", "audience", "description", "paths", "organization_kinds", "innovation_kinds", "stages",
        ))
    school_steps = _generate(client, 1)["steps"]
    standard_steps = [
        "Opisz rozwiązanie do powtórzenia", "Znajdź pierwszą organizację", "Przeprowadź wspólny pilotaż",
    ]
    assert [step["title"] for step in school_steps if not step["instrument"]] == standard_steps
    assert any("ORE" in (step["instrument"] or "") for step in school_steps)
    assert any("dyrekcją szkoły" in step["title"] for step in school_steps)
    assert all("SMART" not in (step["instrument"] or "") for step in school_steps)

    transfer_steps = _generate(client, 3)["steps"]
    assert transfer_steps[0]["instrument"] == "Centrum transferu technologii macierzystej uczelni"
    assert any("UPRP" in (step["url"] or "").upper() for step in transfer_steps)

    other = Innovation(title="Bez katalogu", kind="organizacyjna", stage="wdrozona")
    steps, _ = plan_for(other, "wdrozenie")
    assert [step["title"] for step in steps] == standard_steps
    assert all(step["instrument"] is None and step["url"] is None for step in steps)

    local = Organization(name="Szkoła", kind="szkola", region="podkarpackie")
    distant = Organization(name="Szkoła", kind="szkola", region="pomorskie")
    for org, expected in [(local, True), (distant, False)]:
        idea = Innovation(title="Pomysł", kind="technologiczna", stage="pomysl", organization=org)
        steps, _ = plan_for(idea, "rozwoj")
        assert any("ProtoLab" in (step["instrument"] or "") for step in steps) is expected


def _broker():
    return db.session.scalar(select(User).where(User.role == "broker"))


def test_only_broker_approves_and_history_keeps_actor(client):
    proposed = _generate(client, 1)
    url = "/api/innovations/1/recommendation/accept"
    assert client.post(url).status_code == 403
    assert client.post(url, headers={"X-User-Id": "1"}).status_code == 403
    assert db.session.get(Innovation, 1).status == "zgloszona"

    broker = _broker()
    headers = {"X-User-Id": str(broker.id)}
    assert client.post(url, headers=headers, json={"path": []}).status_code == 400
    assert client.post("/api/innovations/2/recommendation/accept", headers=headers).status_code == 404
    accepted = client.post(url, headers=headers)
    assert accepted.status_code == 200
    assert accepted.json["id"] == proposed["id"]
    assert accepted.json["approval"]["actor"] == broker.name
    assert accepted.json["approval"]["created_at"]
    assert db.session.get(Innovation, 1).status == "skierowana"

    assert client.post(url, headers=headers).json == accepted.json
    event = db.session.scalars(select(Event).where(Event.innovation_id == 1, Event.type == ACCEPTED)).one()
    assert event.actor_id == broker.id
    assert event.payload["recommendation_id"] == proposed["id"]
    assert event.payload["to"] == "skierowana"


def test_broker_override_rebuilds_plan_and_preserves_proposal(client):
    original = _generate(client, 3)
    response = client.post(
        "/api/innovations/3/recommendation/accept",
        headers={"X-User-Id": str(_broker().id)},
        json={"path": "komercjalizacja"},
    )
    assert response.status_code == 200
    result = response.json
    assert result["id"] != original["id"]
    assert result["path"] == "komercjalizacja"
    assert result["engine"] == "czlowiek"
    assert result["steps"] != original["steps"]
    assert result["metrics"] != original["metrics"]
    assert result["alternative"]["path"] == original["path"]
    assert result["approval"]["actor_id"] == _broker().id
    assert db.session.get(Recommendation, original["id"]).path == "transfer"
    assert db.session.get(Innovation, 3).status == "skierowana"
    assert client.get("/api/innovations/3/recommendation").json == result


def test_cli_runs_only_missing_up_to_limit(app):
    runner = app.test_cli_runner()

    for expected in (2, 4):
        result = runner.invoke(args=["paths", "run", "--missing", "--limit", "2"])
        assert result.exit_code == 0, result.output
        assert db.session.scalar(select(func.count()).select_from(Recommendation)) == expected
        assert db.session.scalar(select(func.count(func.distinct(Recommendation.innovation_id)))) == expected
