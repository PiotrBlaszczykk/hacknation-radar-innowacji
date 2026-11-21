import pytest
from sqlalchemy import update

from app.config import EMBED_DIM
from app.extensions import db
from app.models import Innovation, Match, Need, User
from app.opportunities.review import CONDITIONS_HEADER
from app.services import decisions, llm

NEAR = [1.0, 0.0] + [0.0] * (EMBED_DIM - 2)
FAR = [0.0, 1.0] + [0.0] * (EMBED_DIM - 2)
REQUIREMENT = "Napisy po polsku w ciągu trzech sekund."


@pytest.fixture()
def clean_catalog(app):
    db.session.execute(update(Need).values(status="zamkniete"))
    db.session.execute(update(Innovation).values(status="archiwum"))
    db.session.commit()


def need(title, author_id=4, *, embedding=NEAR, description="Napisy na żywo."):
    author = db.session.get(User, author_id)
    row = Need(
        title=title, description=description, author=author, organization=author.organization,
        embedding=embedding,
    )
    db.session.add(row)
    db.session.flush()
    return row


def card(title, *, embedding=NEAR, status="zgloszona", stage="pilotaz", solution="Działające napisy."):
    row = Innovation(title=title, embedding=embedding, status=status, stage=stage, solution=solution)
    db.session.add(row)
    db.session.flush()
    return row


def answer(value, confidence=0.99):
    return {"choice": value, "confidence": confidence, "engine": "test-basal", "calibrated": True}


def opportunities(client):
    response = client.get("/api/opportunities")
    assert response.status_code == 200
    return response.get_json()


def test_from_open_sources_to_covered_and_closed(client, clean_catalog, monkeypatch):
    conditions = CONDITIONS_HEADER + "- " + REQUIREMENT
    original = need("Napisy na posiedzeniu", description="Napisy w transmisji." + conditions)
    duplicate = need(original.title, description=original.description)
    second = need("Tekst na żywo w relacji", 1, description="Transkrypcja w przekazie." + conditions)
    third = need("Czytanie debaty w internecie", 2, description="Napisy do debaty online." + conditions)
    different = need("Cytaty z archiwum", 1, description="Wyszukiwanie cytatów z nagranych posiedzeń.")
    isolated = need("Odczyt temperatury w chłodni", embedding=FAR)
    partial = card("Napisy z opóźnieniem")
    unverified = card("Napisy bez podanego opóźnienia")
    card("Karta z archiwum", status="archiwum")
    match = Match(
        innovation=partial, need=original, organization=original.organization, role="uzytkownik",
        score=0.8, reason="Uzasadnienie istniejącego dopasowania", status="kontakt",
    )
    db.session.add(match)
    db.session.commit()

    calls = []

    def decide(state, questions, **_):
        calls.append(state)
        if "equivalence" in questions:
            return {"equivalence": answer("different" if "Cytaty" in state else "equivalent")}
        result = {"coverage": answer("different" if "Cytaty" in state else "fits")}
        if "condition_0" in questions:
            condition = (
                "unverified" if "bez podanego" in state else
                "missing" if "z opóźnieniem" in state else
                "supported"
            )
            result["condition_0"] = answer(condition)
        return result

    monkeypatch.setattr(decisions, "decide", decide)
    monkeypatch.setattr(llm, "embed", lambda texts, **_: [NEAR for _ in texts])

    initial = opportunities(client)
    first = initial["items"][0]
    assert first["id"] == original.id
    assert first["organization_count"] == 3
    assert [source["id"] for source in first["sources"]] == [original.id, duplicate.id, second.id, third.id]
    assert first["status"] == "partial"
    assert {item["id"] for item in first["alternatives"]} == {partial.id, unverified.id}
    checks = {item["id"]: item["reviews"][0]["conditions"] for item in first["alternatives"]}
    assert checks[partial.id] == [{"requirement": REQUIREMENT, "status": "missing"}]
    assert checks[unverified.id] == [{"requirement": REQUIREMENT, "status": "unverified"}]
    assert {item["id"]: item["status"] for item in initial["items"] if item["id"] != original.id} == {
        different.id: "no_solution", isolated.id: "no_solution",
    }
    previous_calls = len(calls)
    assert previous_calls > 0
    assert opportunities(client) == initial
    assert len(calls) == previous_calls

    response = client.post("/api/innovations", json={
        "title": "Symultaniczne podpisy wypowiedzi",
        "solution": "Transkrypcja po polsku w dwie sekundy.",
        "stage": "pilotaz",
    })
    assert response.status_code == 201
    updated = opportunities(client)["items"][0]
    assert updated["status"] == "fits"
    assert updated["alternatives"][0]["id"] == response.get_json()["id"]
    assert updated["organization_count"] == 3

    url = f"/api/needs/{original.id}"
    assert client.patch(url, json={"status": "zamkniete"}).status_code == 401
    assert client.patch(url, json={"status": "zamkniete"}, headers={"X-User-Id": "1"}).status_code == 403
    assert client.patch(url, json={"status": "zamkniete"}, headers={"X-User-Id": "4"}).status_code == 200
    assert client.get(url).get_json()["status"] == "zamkniete"
    remaining = opportunities(client)["items"][0]
    assert [source["id"] for source in remaining["sources"]] == [duplicate.id, second.id, third.id]
    assert remaining["organization_count"] == 3
    historical = client.get(url + "/matches").get_json()["items"]
    assert [(item["id"], item["status"]) for item in historical] == [(match.id, "kontakt")]
    assert db.session.get(Match, match.id).reason == "Uzasadnienie istniejącego dopasowania"


def test_missing_vectors_model_failure_and_thin_card(client, clean_catalog, monkeypatch):
    missing = need("Potrzeba bez wektora", embedding=None)
    similar = need("Napisy i transkrypcja na żywo")
    thin = card("Napisy zakupione", stage=None, solution=None)
    card("Karta oczekująca na embedding", embedding=None)
    another = need("Czytalna transmisja")
    db.session.commit()
    calls = []

    def unavailable(*args, **kwargs):
        calls.append(args)
        raise llm.LLMUnavailable("serwer przerwał pracę")

    monkeypatch.setattr(decisions, "decide", unavailable)
    result = opportunities(client)
    assert result["missing_need_embeddings"] == 1
    assert result["missing_card_embeddings"] == 1
    assert result["incomplete"]
    assert {item["id"] for item in result["items"]} == {missing.id, similar.id, another.id}
    assert all(item["status"] == "insufficient_data" for item in result["items"])
    assert result["items"][1]["alternatives"][0]["id"] == thin.id
    assert result["items"][1]["alternatives"][0]["reviews"][0]["reason"] == "missing_description"
    assert opportunities(client) == result
    assert len(calls) == 1


def test_groups_require_pairwise_agreement(client, clean_catalog, monkeypatch):
    a, b, c = (need(title) for title in ("Wariant A", "Wariant B", "Wariant C"))
    db.session.commit()

    def decide(state, questions, **_):
        assert set(questions) == {"equivalence"}
        return {"equivalence": answer("different" if "Wariant A" in state and "Wariant C" in state else "equivalent")}

    monkeypatch.setattr(decisions, "decide", decide)
    assert [[source["id"] for source in item["sources"]] for item in opportunities(client)["items"]] == [
        [a.id, b.id], [c.id],
    ]



def test_uncertain_positive_remains_unconfirmed(client, clean_catalog, monkeypatch):
    need("Wyszukiwanie cytatów", description="Znajdowanie nagranych wypowiedzi po tekście.")
    card("Napisy w transmisji")
    db.session.commit()
    monkeypatch.setattr(decisions, "decide", lambda *args, **kwargs: {"coverage": answer("fits", 0.61)})

    item = opportunities(client)["items"][0]
    assert item["status"] == "insufficient_data"
    assert item["incomplete"]
    assert item["alternatives"][0]["reviews"][0]["reason"] == "unconfirmed_coverage"
