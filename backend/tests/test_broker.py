from datetime import timedelta

from sqlalchemy import select

from app.scoring import CRITERIA_VERSION, LEGACY_REVIEW_THRESHOLD, REVIEW_THRESHOLD
from app.domain import STATUSES
from app.extensions import db
from app.models import Assessment, Event, Innovation, Interaction, Match, Recommendation, User


def test_summary_with_seed_and_empty_tables(client):
    response = client.get("/api/broker/summary")
    assert response.status_code == 200
    data = response.get_json()
    assert data["innovations"]["total"] == 6
    assert data["innovations"]["by_origin"] == {"radar": 1, "zgloszenie": 5}
    assert data["innovations"]["by_kind"]["edukacyjna"] == 2
    assert data["innovations"]["by_status"]["wykryta"] == 1
    assert data["innovations"]["radar_claimed"] == 0
    assert data["assessments"] == {"total": 0, "average_score": None, "low_confidence": 0}
    assert data["paths"]["total"] == data["matches"]["innovations_with_contact"] == 0
    assert data["median_days"] == {"to_assessment": None, "to_contact": None}
    assert data["organizations"]["total"] == 6
    assert data["organizations"]["by_kind"]["szkola"] == 2
    assert client.get("/api/broker/queue").get_json() == {"items": [], "total": 0}


def test_board_groups_radar_data_and_returns_only_top_twenty(client, app):
    db.session.add_all(
        Innovation(title=f"Projekt radaru {score}", status="wykryta", origin="radar", claimed=False, score=score)
        for score in range(24)
    )
    db.session.add(Innovation(title="Pozycja archiwalna", status="archiwum", score=100))
    db.session.commit()

    response = client.get("/api/broker/board")
    assert response.status_code == 200
    columns = response.get_json()["columns"]
    assert [column["status"] for column in columns] == list(STATUSES)[:-1]
    radar, submitted, assessed, *_ = columns
    assert radar["total"] == 25
    assert [item["score"] for item in radar["items"]] == list(range(23, 3, -1))
    assert submitted["total"] == len(submitted["items"]) == 5
    assert assessed == {"status": "oceniona", "total": 0, "items": []}
    summary = client.get("/api/broker/summary").get_json()
    assert summary["innovations"]["by_origin"]["radar"] == 25
    assert summary["innovations"]["by_status"]["archiwum"] == 1


def test_queue_and_flags_from_latest_assessment_and_interest(client, app):
    innovation = db.session.scalar(select(Innovation).where(Innovation.origin == "radar"))
    innovation.score = 81
    user = db.session.scalar(select(User).where(User.role == "poszukujacy"))
    proposal = Recommendation(innovation_id=innovation.id, engine="test", path="rozwoj")
    match = Match(innovation_id=innovation.id, organization_id=user.organization_id, status="zainteresowanie", score=0.9)
    db.session.add_all([
        Assessment(innovation_id=innovation.id, criteria_version="1", engine="test", total=40, confidence=0.9),
        Assessment(innovation_id=innovation.id, criteria_version="1", engine="test", total=81, confidence=0.2),
        proposal,
        match,
        Interaction(innovation_id=innovation.id, user_id=user.id, type="zainteresowany"),
    ])
    db.session.commit()

    queue = client.get("/api/broker/queue").get_json()
    assert queue["total"] == 4
    assert {item["type"] for item in queue["items"]} == {
        "low_confidence", "path_approval", "match_interest", "unclaimed_profile",
    }
    assert all(item["innovation_id"] == innovation.id and item["description"] for item in queue["items"])
    assert next(item for item in queue["items"] if item["type"] == "match_interest")["match_id"] == match.id
    first = client.get("/api/broker/queue?limit=1").json
    assert first["items"][0]["match_id"] == match.id and first["total"] == 4
    interests = client.get("/api/broker/queue?type=match_interest").json
    assert interests["items"][0]["match_id"] == match.id and interests["total"] == 1

    card = client.get("/api/broker/board").get_json()["columns"][0]["items"][0]
    assert card["needs_review"]
    assert not card["has_path"]
    assert card["interest_count"] == 2
    assert card["matches_count"] == 1
    assert card["organization"]["name"] == innovation.organization.name

    db.session.add(Assessment(
        innovation_id=innovation.id, criteria_version="1", engine="test", total=81,
        confidence=LEGACY_REVIEW_THRESHOLD, items=[{"missing": True}],
    ))
    db.session.commit()
    assert client.get("/api/broker/board").get_json()["columns"][0]["items"][0]["needs_review"]
    assert client.get("/api/broker/summary").get_json()["assessments"] == {
        "total": 1, "average_score": 81, "low_confidence": 0,
    }
    missing = next(item for item in client.get("/api/broker/queue").json["items"] if item["type"] == "low_confidence")
    assert "brakuje danych" in missing["description"]


def test_approval_and_event_medians(client, app):
    radar = db.session.scalar(select(Innovation).where(Innovation.origin == "radar"))
    submitted = db.session.scalar(select(Innovation).where(Innovation.origin == "zgloszenie"))
    radar.claimed = True
    radar.status = "w_kontakcie"
    proposal = Recommendation(innovation_id=radar.id, engine="test", path="transfer")
    db.session.add_all([
        proposal,
        Match(innovation_id=radar.id, status="kontakt", score=0.7),
        Match(innovation_id=radar.id, status="kontakt", score=0.9),
        Match(innovation_id=submitted.id, status="odrzucone", score=0.3),
    ])
    db.session.flush()
    for innovation, assessment_days in ((radar, 1), (submitted, 5)):
        start = innovation.events[0].created_at
        db.session.add_all([
            Event(innovation_id=innovation.id, type="oceniona", created_at=start + timedelta(days=assessment_days)),
            Event(innovation_id=innovation.id, type="oceniona", created_at=start + timedelta(days=20)),
            Event(innovation_id=innovation.id, type="kontakt", created_at=start + timedelta(hours=2)),
        ])
    start = radar.events[0].created_at
    db.session.add_all([
        Event(innovation_id=radar.id, type="rekomendacja_zatwierdzona",
              payload={"path": "transfer", "recommendation_id": proposal.id}),
        Event(innovation_id=radar.id, type="dopasowanie", payload={"to": "kontakt"},
              created_at=start + timedelta(days=3)),
    ])
    db.session.commit()

    data = client.get("/api/broker/summary").get_json()
    assert data["innovations"]["radar_claimed"] == 1
    assert data["paths"]["total"] == data["paths"]["by_path"]["transfer"] == 1
    assert data["matches"]["by_status"]["kontakt"] == 2
    assert data["matches"]["innovations_with_contact"] == data["matches"]["radar_innovations_matched"] == 1
    assert data["median_days"] == {"to_assessment": 3, "to_contact": 3}
    assert client.get("/api/broker/queue").get_json()["total"] == 0
    columns = client.get("/api/broker/board").get_json()["columns"]
    assert next(column for column in columns if column["status"] == "w_kontakcie")["items"][0]["has_path"]

    db.session.add(Recommendation(innovation_id=radar.id, engine="test", path="rozwoj"))
    db.session.commit()
    assert client.get("/api/broker/queue").get_json()["items"][0]["type"] == "path_approval"
    assert client.get("/api/broker/summary").get_json()["paths"]["by_path"]["transfer"] == 1


def test_move_updates_column_summary_and_history(client, app):
    innovation = db.session.scalar(select(Innovation).where(Innovation.origin == "radar"))
    broker = db.session.scalar(select(User).where(User.role == "broker"))
    response = client.patch(
        f"/api/innovations/{innovation.id}", json={"status": "oceniona"}, headers={"X-User-Id": str(broker.id)},
    )
    assert response.status_code == 200
    event = response.get_json()["events"][-1]
    assert event["type"] == "status"
    assert event["actor"] == broker.name
    assert event["payload"] == {"from": "wykryta", "to": "oceniona"}
    columns = {column["status"]: column for column in client.get("/api/broker/board").get_json()["columns"]}
    assert columns["wykryta"]["total"] == 0
    assert [item["id"] for item in columns["oceniona"]["items"]] == [innovation.id]
    data = client.get("/api/broker/summary").get_json()
    assert data["innovations"]["by_status"]["oceniona"] == 1
    assert data["innovations"]["by_origin"]["radar"] == 1
    assert data["median_days"]["to_assessment"] is None


def test_current_review_threshold_is_shared_by_assessment_and_broker(client):
    innovation = db.session.get(Innovation, 1)
    db.session.add(Assessment(
        innovation_id=1, criteria_version=CRITERIA_VERSION, engine="test", total=80,
        confidence=REVIEW_THRESHOLD - 0.01, items=[{"missing": False, "weight": 20}],
    ))
    db.session.commit()
    assessment = client.get("/api/innovations/1/assessment").json
    assert assessment["needs_review"] and assessment["has_score"]
    assert not assessment["ranked"]
    assert client.get("/api/broker/summary").json["assessments"]["low_confidence"] == 1
    assert client.get("/api/broker/queue").json["items"][0]["innovation_id"] == innovation.id


def test_queue_pages_count_all_filtered_cases_and_use_latest_assessment(client):
    innovations = db.session.scalars(select(Innovation).order_by(Innovation.id).limit(5)).all()
    broker = db.session.scalar(select(User).where(User.role == "broker"))
    headers = {"X-User-Id": str(broker.id)}
    missing = {
        "key": "dowody", "label": "Dowody skuteczności", "score": 2.5, "weight": 20,
        "missing": True, "question": "Jaki efekt zmierzono?",
    }
    for innovation in innovations:
        innovation.score = 50
        db.session.add(Assessment(
            innovation_id=innovation.id, criteria_version=CRITERIA_VERSION, engine="test",
            total=50, confidence=0.1, items=[missing],
        ))
    db.session.flush()
    confident_enough_to_score = {
        "key": "wplyw", "label": "Wpływ", "score": 3, "weight": 10, "confidence": 0.1, "missing": False,
    }
    db.session.add(Assessment(
        innovation_id=innovations[-1].id, criteria_version=CRITERIA_VERSION, engine="test",
        total=60, confidence=0.1, items=[confident_enough_to_score],
    ))
    db.session.commit()

    endpoint = "/api/broker/queue?type=missing_evidence&limit=2"
    first = client.get(endpoint).json
    second = client.get(endpoint + "&offset=2").json
    empty = client.get(endpoint + "&offset=100").json
    assert [page["total"] for page in (first, second, empty)] == [4, 4, 4]
    assert [item["innovation_id"] for item in first["items"] + second["items"]] == [i.id for i in innovations[:4]]
    assert first["overall"] == 5 and second["offset"] == 2 and empty["items"] == []
    assert first["items"][0]["next_step"] == "Zapytaj twórców: Jaki efekt zmierzono?"
    assert client.get("/api/broker/queue?type=low_confidence").json["items"][0]["description"] == (
        "Najmniej pewne kryterium to „Wpływ”."
    )
    assert client.get("/api/broker/queue?type=inny").status_code == 400
    assert client.get("/api/broker/queue?limit=500").json["limit"] == 50
    assert {item["type"] for item in client.get("/api/broker/queue").json["items"]} == {"low_confidence"}

    correction = client.post(
        f"/api/innovations/{innovations[0].id}/assessment/override", headers=headers,
        json={"key": "dowody", "score": 3, "justification": "Udokumentowana próba."},
    )
    assert correction.status_code == 200
    assert client.get(endpoint).json["total"] == 3
    assert client.get("/api/broker/queue?type=low_confidence").json["total"] == 1


def test_contact_queue_respects_persona_and_existing_match_decision(client):
    innovation = db.session.get(Innovation, 2)
    requester = db.session.scalar(select(User).where(User.role == "poszukujacy"))
    broker = db.session.scalar(select(User).where(User.role == "broker"))
    match = Match(innovation_id=innovation.id, organization_id=requester.organization_id, score=0.7)
    db.session.add_all([match, Interaction(
        innovation_id=innovation.id, user_id=requester.id, type="kontakt", body="Prywatna wiadomość do twórców",
    )])
    db.session.commit()
    endpoint = "/api/broker/queue?type=contact_request"
    broker_headers = {"X-User-Id": str(broker.id)}
    other_headers = {"X-User-Id": str(requester.id)}

    response = client.get(endpoint, headers=broker_headers)
    assert response.cache_control.no_store
    assert response.json["total"] == 1
    assert response.json["items"][0]["match_id"] == match.id
    assert "Prywatna wiadomość" not in response.get_data(as_text=True)
    assert client.get(endpoint, headers=other_headers).json["total"] == 0
    assert client.get(endpoint).json["overall"] == 0
    social = f"/api/innovations/{innovation.id}/interactions"
    assert client.get(social, headers=broker_headers).json["contact_requests"]
    assert not client.get(social, headers=other_headers).json["contact_requests"]

    url = f"/api/matches/{match.id}"
    assert client.patch(url, headers=other_headers, json={"status": "kontakt"}).status_code == 403
    assert client.get(endpoint, headers=broker_headers).json["total"] == 1
    assert client.patch(url, headers=broker_headers, json={"status": "kontakt"}).status_code == 200
    assert client.get(endpoint, headers=broker_headers).json["total"] == 0
    assert client.get(social, headers=broker_headers).json["contact_requests"]
