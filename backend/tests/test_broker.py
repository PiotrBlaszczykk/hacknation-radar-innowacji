from datetime import timedelta

from sqlalchemy import select

from app.api.broker import LOW_CONFIDENCE
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

    card = client.get("/api/broker/board").get_json()["columns"][0]["items"][0]
    assert card["needs_review"]
    assert not card["has_path"]
    assert card["interest_count"] == 2
    assert card["matches_count"] == 1
    assert card["organization"]["name"] == innovation.organization.name

    db.session.add(Assessment(
        innovation_id=innovation.id, criteria_version="1", engine="test", total=81,
        confidence=LOW_CONFIDENCE, items=[{"missing": True}],
    ))
    db.session.commit()
    assert client.get("/api/broker/board").get_json()["columns"][0]["items"][0]["needs_review"]
    assert client.get("/api/broker/summary").get_json()["assessments"] == {
        "total": 1, "average_score": 81, "low_confidence": 0,
    }
    assert "low_confidence" not in {item["type"] for item in client.get("/api/broker/queue").get_json()["items"]}


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
