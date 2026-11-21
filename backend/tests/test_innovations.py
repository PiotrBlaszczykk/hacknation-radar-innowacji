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

    updated = client.patch(f"/api/innovations/{created['id']}", json={"status": "oceniona"}).get_json()
    assert updated["status"] == "oceniona"
    assert updated["events"][-1]["payload"] == {"from": "zgloszona", "to": "oceniona"}


def test_validation(client):
    assert client.post("/api/innovations", json={"title": ""}).status_code == 400
    assert client.post("/api/innovations", json={"title": "x", "kind": "magiczna"}).status_code == 400
    assert client.get("/api/innovations/999999").status_code == 404
