import pytest

from app.extensions import db
from app.models import Innovation


@pytest.fixture()
def people(client):
    users = client.get("/api/users").get_json()["items"]
    return {
        role: next(user for user in users if user["title"] == title)
        for role, title in {
            "creator": "Adiunkt, Katedra Metrologii",
            "broker": "Brokerka innowacji",
            "secretary": "Sekretarz gminy",
            "investor": "Menedżerka inwestycyjna",
        }.items()
    }


def as_user(user):
    return {"X-User-Id": str(user["id"])}


def innovation_url(client, title):
    items = client.get("/api/innovations", query_string={"q": title}).get_json()["items"]
    return f"/api/innovations/{next(item['id'] for item in items if item['title'] == title)}"


@pytest.fixture()
def sensor_url(client):
    return innovation_url(client, "Tani czujnik pyłów zawieszonych z autokalibracją")


@pytest.mark.parametrize(("kind", "activity_key"), [("obserwuje", "following"), ("zainteresowany", "interested")])
def test_toggle_is_personal_and_updates_activity(client, people, sensor_url, kind, activity_key):
    url = f"{sensor_url}/interactions"
    secretary = as_user(people["secretary"])
    investor = as_user(people["investor"])

    assert client.post(url, json={"type": kind}, headers=secretary).get_json()["active"] is True
    own = client.get(url, headers=secretary).get_json()
    assert own["counts"][kind] == 1
    assert own["mine"] == [kind]
    other = client.get(url, headers=investor).get_json()
    assert other["counts"][kind] == 1
    assert other["mine"] == []
    activity = client.get("/api/me/activity", headers=secretary).get_json()
    assert [item["id"] for item in activity[activity_key]] == [int(sensor_url.rsplit("/", 1)[-1])]

    assert client.post(url, json={"type": kind}, headers=secretary).get_json()["active"] is False
    own = client.get(url, headers=secretary).get_json()
    assert own["counts"][kind] == 0
    assert own["mine"] == []
    assert client.get("/api/me/activity", headers=secretary).get_json()[activity_key] == []
    events = client.get(sensor_url).get_json()["events"]
    interest_events = [event for event in events if event["type"] == "zainteresowany"]
    if kind == "zainteresowany":
        assert len(interest_events) == 1
        assert people["secretary"]["organization"]["name"] in interest_events[0]["message"]
    else:
        assert not interest_events


@pytest.mark.parametrize("kind", ["komentarz", "kontakt"])
@pytest.mark.parametrize("body", [None, "  ", 123])
def test_messages_require_text(client, people, sensor_url, kind, body):
    response = client.post(f"{sensor_url}/interactions", json={"type": kind, "body": body},
                           headers=as_user(people["secretary"]))
    assert response.status_code == 400


def test_authentication_required_for_writes_and_personal_activity(client, sensor_url):
    assert client.post(f"{sensor_url}/interactions", json={"type": "obserwuje"}).status_code == 401
    assert client.post(f"{sensor_url}/claim").status_code == 401
    assert client.get("/api/me/activity").status_code == 401
    assert client.get(f"{sensor_url}/interactions").status_code == 200


def test_contact_details_and_history_visible_only_to_recipient_org_and_broker(client, people, sensor_url):
    url = f"{sensor_url}/interactions"
    secretary = people["secretary"]
    assert client.post(url, json={"type": "kontakt", "body": "  Prosimy o pilotaż. "},
                       headers=as_user(secretary)).status_code == 201
    assert client.post(url, json={"type": "komentarz", "body": "Wyniki są obiecujące."},
                       headers=as_user(secretary)).status_code == 201

    for role in ("creator", "broker"):
        headers = as_user(people[role])
        data = client.get(url, headers=headers).get_json()
        assert data["can_read_contacts"] is True
        assert data["counts"]["kontakt"] == 1
        contact, = data["contact_requests"]
        assert contact["body"] == "Prosimy o pilotaż."
        assert contact["user"]["id"] == secretary["id"]
        assert contact["user"]["organization"]["id"] == secretary["organization"]["id"]
        events = client.get(sensor_url, headers=headers).get_json()["events"]
        event, = [event for event in events if event["type"] == "kontakt"]
        assert secretary["organization"]["name"] in event["message"]

    for headers in ({}, as_user(people["investor"]), as_user(secretary)):
        data = client.get(url, headers=headers).get_json()
        assert data["can_read_contacts"] is False
        assert data["counts"]["kontakt"] == 1
        assert data["contact_requests"] == []
        assert data["comments"][0]["body"] == "Wyniki są obiecujące."
        assert all(event["type"] != "kontakt" for event in client.get(sensor_url, headers=headers).get_json()["events"])

    inbox = client.get("/api/me/activity", headers=as_user(people["creator"])).get_json()["contact_requests"]
    assert inbox[0]["innovation"]["id"] == int(sensor_url.rsplit("/", 1)[-1])
    for role in ("broker", "investor", "secretary"):
        assert client.get("/api/me/activity", headers=as_user(people[role])).get_json()["contact_requests"] == []
    patched = client.patch(sensor_url, json={}, headers=as_user(people["investor"])).get_json()
    assert all(event["type"] != "kontakt" for event in patched["events"])


@pytest.mark.parametrize("role", ["secretary", "investor"])
def test_claim_updates_author_listing_and_history_only_once(client, people, role):
    url = innovation_url(client, "Telefon zaufania sąsiedzkiego dla seniorów")
    before = client.get(url).get_json()
    assert before["claimed"] is False

    claimant = people[role]
    response = client.post(f"{url}/claim", headers=as_user(claimant))
    assert response.status_code == 200
    assert response.get_json()["claimed"] is True
    assert response.get_json()["author"]["id"] == claimant["id"]
    assert client.post(f"{url}/claim", headers=as_user(people["creator"])).status_code == 409
    detail = client.get(url).get_json()
    claim_events = [event for event in detail["events"] if event["type"] == "potwierdzona"]
    assert len(claim_events) == 1
    assert claim_events[0]["payload"]["organization_mismatch"] is (role == "investor")
    if role == "investor":
        assert "spoza organizacji" in claim_events[0]["message"]
    assert detail["organization"] == before["organization"]
    listing = client.get("/api/innovations?origin=radar").get_json()["items"]
    listed = next(item for item in listing if item["id"] == detail["id"])
    assert listed["claimed"] is True
    assert listed["author"]["id"] == claimant["id"]


def test_organization_profile_and_paginated_list(client, people):
    organization = people["secretary"]["organization"]
    org_id = organization["id"]
    db.session.add_all([
        Innovation(title="Projekt pilotażowy", organization_id=org_id, status="w_kontakcie", score=0),
        Innovation(title="Projekt wdrażany", organization_id=org_id, status="wdrazana", score=80),
    ])
    db.session.commit()

    profile = client.get(f"/api/organizations/{org_id}").get_json()
    assert profile["name"] == organization["name"]
    assert profile["people_count"] == 1
    assert {item["title"] for item in profile["innovations"]} == {
        "Telefon zaufania sąsiedzkiego dla seniorów", "Projekt pilotażowy", "Projekt wdrażany",
    }
    assert all("description" not in item for item in profile["innovations"])
    assert [need["title"] for need in profile["needs"]] == ["Wiarygodny pomiar jakości powietrza w sołectwach"]
    assert profile["stats"] == {
        "innovation_count": 3, "assessed_count": 2, "average_score": 40, "in_contact_or_implementing_count": 2,
    }

    filtered = client.get("/api/organizations", query_string={"q": organization["name"], "limit": 1}).get_json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["innovation_count"] == 3
    page = client.get("/api/organizations?limit=1").get_json()
    second = client.get("/api/organizations?limit=1&offset=1").get_json()
    assert page["total"] == second["total"] > 1
    assert page["items"][0]["id"] != second["items"][0]["id"]
    assert second["limit"] == second["offset"] == 1
