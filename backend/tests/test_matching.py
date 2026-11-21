import pytest

from app.extensions import db
from app.matching import score_match
from app.models import Innovation, Match, Need, Organization
from app.services import llm


def headers(user_id):
    return {"X-User-Id": str(user_id)}


def test_score_explains_text_areas_offers_and_stage():
    town = Organization(kind="jst", interests=["energia_srodowisko"])
    innovation = Innovation(
        stage="prototyp", domains=["energia_srodowisko", "cyfryzacja_ict"],
        support_needs=["pierwszy_uzytkownik", "finansowanie"],
    )
    need = Need(
        title="Pomiar powietrza", domains=["energia_srodowisko"], offers=["pierwszy_uzytkownik"],
    )
    score, role, reason, factors = score_match(innovation, town, need, 0.66)
    assert role == "uzytkownik"
    assert factors["similarity"] == pytest.approx(0.26 / 0.60)
    assert factors["domains"] == 1
    assert factors["offers"] == 0.5
    assert factors["stage"] == 0.45
    assert score == pytest.approx(0.32 * 0.26 / 0.60 + 0.33 + 0.22 * 0.5 + 0.13 * 0.45, abs=0.00005)
    assert "Pomiar powietrza" in reason and "pierwszy użytkownik" in reason
    assert score_match(innovation, town, need, 0.40)[3]["similarity"] == 0
    assert score_match(innovation, town, need)[3]["similarity"] is None

    investor = Organization(kind="inwestor", interests=["energia_srodowisko"])
    org_score, org_role, _, org_factors = score_match(innovation, investor)
    assert org_role == "inwestor"
    assert org_factors["similarity"] is None and org_factors["offers"] is None
    assert org_factors["stage"] == 1
    assert org_score == pytest.approx(0.70 * 0.5 + 0.30)


def test_seed_rankings_and_self_exclusion(client):
    # Wektory z conftest nie niosą znaczenia: ranking korzysta tutaj z jawnych danych.
    town = client.get("/api/needs/1/matches").get_json()["items"]
    assert town[0]["innovation"]["id"] == 3
    fund = client.get("/api/needs/2/matches").get_json()["items"]
    assert fund[0]["innovation"]["id"] == 3
    assert fund[0]["factors"]["stage"] == 1
    assert all(match["innovation"]["id"] != 2 for match in fund)

    results = client.get("/api/innovations/6/matches").get_json()["items"]
    assert any(match["need"] is None for match in results)
    assert all(match["score"] >= 0.35 for match in results)


def test_excludes_own_organization_with_and_without_a_need(client):
    tutoring = client.get("/api/innovations/2").get_json()
    matches = client.get("/api/innovations/2/matches").get_json()["items"]
    assert all(match["organization"]["id"] != tutoring["organization"]["id"] for match in matches)

    response = client.post(
        "/api/needs", headers=headers(1),
        json={
            "title": "Pracownia druku 3D", "description": "Szukamy pracowni druku części zamiennych.",
            "domains": ["edukacja"], "offers": ["partner_wdrozeniowy", "finansowanie"],
        },
    )
    assert response.status_code == 201
    matches = client.get(f"/api/needs/{response.get_json()['id']}/matches").get_json()["items"]
    assert all(match["innovation_id"] != 1 for match in matches)


def test_create_need_uses_persona_and_matches_without_embeddings(client, app, monkeypatch):
    def unavailable(*args, **kwargs):
        raise llm.LLMUnavailable("Model wyłączony")

    monkeypatch.setattr(llm, "embed", unavailable)
    response = client.post(
        "/api/needs",
        headers=headers(4),
        json={
            "title": "Pilotaż pomiarów", "description": "Szukamy czujnika jakości powietrza.",
            "domains": ["energia_srodowisko"], "offers": ["pierwszy_uzytkownik"],
            "organization_id": 9, "author_id": 5,
        },
    )
    assert response.status_code == 201
    need = response.get_json()
    assert need["organization"]["id"] == 5 and need["author"]["id"] == 4
    need_id = need["id"]
    with app.app_context():
        stored = db.session.scalar(db.select(Match).filter_by(need_id=need_id, innovation_id=3))
        assert stored is not None
        assert stored.factors["similarity"] is None

    assert client.get(f"/api/needs/{need_id}").get_json() == need
    filtered = client.get("/api/needs?status=otwarte&domain=energia_srodowisko&organization_id=5").get_json()
    assert [row["id"] for row in filtered["items"]] == [need_id, 1]
    assert client.get("/api/needs?status=zamkniete").get_json()["items"] == []

    partial = client.get(f"/api/needs/{need_id}/matches").get_json()["items"]
    assert partial[0]["innovation"]["id"] == 3
    full = client.get("/api/innovations/3/matches").get_json()["items"]
    assert {match["need"]["id"] for match in full if match["need"]} == {1, 2, need_id}
    assert any(match["need"] is None for match in full)


def test_match_actions_record_history_and_survive_refresh(client):
    url = "/api/innovations/3/matches"
    initial = client.get(url).get_json()["items"]
    assert [match["score"] for match in initial] == sorted(
        (match["score"] for match in initial), reverse=True,
    )
    match = next(match for match in initial if match["need"] and match["need"]["id"] == 1)
    assert match["role"] == "uzytkownik"
    decision = f"/api/matches/{match['id']}"
    assert client.patch(decision, json={"status": "zainteresowanie"}, headers=headers(5)).status_code == 403
    assert client.patch(decision, json={"status": "kontakt"}, headers=headers(4)).status_code == 403
    for _ in range(2):
        assert client.patch(decision, json={"status": "zainteresowanie"}, headers=headers(4)).status_code == 200
    refreshed = client.post(f"{url}/refresh").get_json()["items"]
    assert [item["id"] for item in refreshed] == [item["id"] for item in initial]
    assert next(item for item in refreshed if item["id"] == match["id"])["status"] == "zainteresowanie"

    assert client.patch(decision, json={"status": "kontakt"}, headers=headers(3)).status_code == 200
    innovation = client.get("/api/innovations/3").get_json()
    assert innovation["status"] == "w_kontakcie"
    events = [event for event in innovation["events"] if event["type"] == "dopasowanie"]
    assert [event["payload"]["to"] for event in events] == ["zainteresowanie", "kontakt"]
    assert [event["payload"]["actor_organization_id"] for event in events] == [5, 1]
    assert [event["actor"] for event in events] == ["Tomasz Zieliński", "Katarzyna Nowak"]
    assert events[-1]["payload"]["innovation_status"]["to"] == "w_kontakcie"

    fund = next(item for item in refreshed if item["need"] and item["need"]["id"] == 2)
    assert client.patch("/api/innovations/3", json={"status": "wdrazana"}, headers=headers(3)).status_code == 200
    response = client.patch(f"/api/matches/{fund['id']}", json={"status": "kontakt"}, headers=headers(3))
    assert response.status_code == 200
    assert client.get("/api/innovations/3").get_json()["status"] == "wdrazana"


def test_refresh_hides_stale_match_and_preserves_decision_when_it_returns(client):
    url = "/api/innovations/3/matches"
    initial = client.get(url).get_json()["items"]
    match = next(item for item in initial if item["need"] and item["need"]["id"] == 1)
    assert client.patch(
        f"/api/matches/{match['id']}", json={"status": "odrzucone"}, headers=headers(3),
    ).status_code == 200
    innovation = db.session.get(Innovation, 3)
    previous = (innovation.domains, innovation.support_needs)
    innovation.domains = []
    innovation.support_needs = []
    db.session.commit()
    assert match["id"] not in [item["id"] for item in client.post(f"{url}/refresh").get_json()["items"]]
    innovation.domains, innovation.support_needs = previous
    db.session.commit()
    restored = client.post(f"{url}/refresh").get_json()["items"]
    assert next(item for item in restored if item["id"] == match["id"])["status"] == "odrzucone"


def test_needs_and_match_errors(client):
    assert client.post("/api/needs", json={}).status_code == 401
    response = client.post(
        "/api/needs", json={"title": "Test", "description": "Opis", "domains": [{}]}, headers=headers(4),
    )
    assert response.status_code == 400
    assert client.patch("/api/matches/1", json={"status": "proponowane"}, headers=headers(4)).status_code == 400
    assert client.get("/api/needs/99999/matches").status_code == 404
    assert client.get("/api/innovations/99999/matches").status_code == 404
