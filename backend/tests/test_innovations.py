import pytest


def test_health_and_meta(client):
    health = client.get("/api/health").get_json()
    assert health["status"] == "ok", health["broken_modules"]
    assert health["counts"]["innovations"] == 6

    meta = client.get("/api/meta").get_json()
    assert {"key": "pilotaz", "label": "Pilotaż"} in meta["stages"]


def test_list_filters(client):
    data = client.get("/api/innovations?kind=edukacyjna").get_json()
    assert data["total"] == 2
    assert all(i["kind"] == "edukacyjna" for i in data["items"])

    assert client.get("/api/innovations?q=czujnik").get_json()["total"] == 1
    assert client.get("/api/innovations?domain=administracja").get_json()["total"] == 1
    assert client.get("/api/innovations?origin=radar").get_json()["items"][0]["claimed"] is False


def test_create_and_update(client):
    users = client.get("/api/users").get_json()["items"]
    teacher = next(u for u in users if u["role"] == "tworca")
    broker = next(u for u in users if u["role"] == "broker")

    response = client.post(
        "/api/innovations",
        json={"title": "Test", "kind": "procesowa", "domains": ["edukacja"]},
        headers={"X-User-Id": str(teacher["id"])},
    )
    assert response.status_code == 201
    created = response.get_json()
    assert created["status"] == "zgloszona"
    assert created["organization"]["id"] == teacher["organization"]["id"]
    assert created["events"][0]["type"] == "zgloszona"

    url = f"/api/innovations/{created['id']}"
    response = client.patch(
        url, json={"status": "oceniona", "description": "Uzupełniony opis"},
        headers={"X-User-Id": str(broker["id"])},
    )
    assert response.status_code == 200
    updated = response.get_json()
    assert updated["status"] == "oceniona"
    assert updated["description"] == "Uzupełniony opis"
    assert updated["events"][:-1] == created["events"]
    assert updated["events"][-1]["type"] == "status"
    assert updated["events"][-1]["actor"] == broker["name"]
    assert updated["events"][-1]["payload"] == {"from": "zgloszona", "to": "oceniona"}
    repeated = client.patch(url, json={"status": "oceniona"}, headers={"X-User-Id": str(broker["id"])})
    assert repeated.status_code == 200
    assert repeated.get_json()["events"] == updated["events"]


@pytest.mark.parametrize("role", ["tworca", None])
def test_only_broker_can_update_status(client, role):
    users = client.get("/api/users").get_json()["items"]
    broker = next(u for u in users if u["role"] == "broker")
    headers = {"X-User-Id": str(next(u["id"] for u in users if u["role"] == role))} if role else {}
    broker_headers = {"X-User-Id": str(broker["id"])}
    url = "/api/innovations/1"
    original = client.get(url, headers=broker_headers).get_json()

    for payload in ({"status": "oceniona"}, {"status": "oceniona", "description": "Uzupełniony opis"}):
        assert client.patch(url, json=payload, headers=headers).status_code == 403
        assert client.get(url, headers=broker_headers).get_json() == original

    ordinary_edit = client.patch(url, json={"description": "Uzupełniony opis"}, headers=headers)
    assert ordinary_edit.status_code == 200
    assert ordinary_edit.get_json()["description"] == "Uzupełniony opis"
    assert ordinary_edit.get_json()["status"] == original["status"]
    assert ordinary_edit.get_json()["events"] == original["events"]


def test_validation(client):
    assert client.post("/api/innovations", json={"title": ""}).status_code == 400
    assert client.post("/api/innovations", json={"title": "x", "kind": "magiczna"}).status_code == 400
    assert client.get("/api/innovations/999999").status_code == 404
