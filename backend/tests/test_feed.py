from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.config import EMBED_DIM
from app.extensions import db
from app.feed import rules
from app.models import Innovation, Interaction, User
from app.services import llm


def headers(persona_id):
    return {"X-User-Id": str(persona_id)}


def feed(client, tab="dla_ciebie", user_id=None, **params):
    response = client.get(
        "/api/feed", query_string={"tab": tab, **params}, headers=headers(user_id) if user_id else {},
    )
    assert response.status_code == 200
    return response.get_json()


def vector(text):
    # Wspólny temat daje wspólny wektor, pozostałe teksty są ortogonalne.
    if "zespołu" in text.casefold():
        return [1.0, 0.0] + [0.0] * (EMBED_DIM - 2)
    return [0.0, 1.0] + [0.0] * (EMBED_DIM - 2)


def test_personal_factors_and_reasons(client, monkeypatch):
    monkeypatch.setattr(llm, "embed", lambda texts, **_: [vector(text) for text in texts])
    user = db.session.get(User, 6)
    user.about = "Dołączę do zespołu"
    user.embedding = llm.embed([user.embedding_text()])[0]
    team = Innovation(
        title="Nabór do zespołu", domains=["cyfryzacja_ict"], support_needs=["zespol"],
        kind="technologiczna", stage="prototyp", score=80,
    )
    own = Innovation(title="Projekt własnego zespołu", organization=user.organization, domains=["cyfryzacja_ict"])
    other = Innovation(title="Inny projekt", domains=["cyfryzacja_ict"], score=80)
    for innovation in (team, own, other):
        innovation.embedding = llm.embed([innovation.embedding_text()])[0]
    db.session.add_all([team, own, other])
    db.session.commit()

    result = feed(client, user_id=user.id)
    assert result["items"][0]["id"] == team.id
    assert "Treść pasuje do opisu w Twoim profilu." in result["items"][0]["why"]
    assert "Twórcy szukają ludzi do zespołu." in result["items"][0]["why"]
    assert result["items"][-1]["id"] == own.id

    team.embedding = None
    db.session.commit()
    result = feed(client, user_id=user.id)
    assert result["items"][0]["id"] == team.id
    assert "Twórcy szukają ludzi do zespołu." in result["items"][0]["why"]
    assert "cyfryzacja i ICT" in result["items"][0]["why"]
    assert "Treść pasuje" not in result["items"][0]["why"]


def test_investor_and_municipality_use_different_stages(client):
    prototypes = feed(client, user_id=5)
    assert prototypes["items"][0]["stage"] in {"pilotaz", "prototyp"}
    assert "finansowania" in prototypes["items"][0]["why"]

    municipal = feed(client, user_id=4)
    assert municipal["items"][0]["stage"] == "wdrozona"
    assert [item["id"] for item in prototypes["items"]] != [item["id"] for item in municipal["items"]]


def test_semantic_search_finds_card_without_shared_words(client, monkeypatch):
    embedding = [1.0] + [0.0] * (EMBED_DIM - 1)
    db.session.get(Innovation, 3).embedding = embedding
    db.session.commit()
    monkeypatch.setattr(llm, "embed", lambda texts, **_: [embedding] * len(texts))
    smog = feed(client, user_id=4, q="sposób na smog w małej gminie")
    assert smog["total"] == 1
    assert smog["items"][0]["id"] == 3
    assert "Temat pasuje do Twojego opisu." in smog["items"][0]["why"]


def test_description_search_and_filters(client):
    seniors = feed(client, user_id=4, q="seniorzy", origin="radar", domain="zdrowie")
    assert seniors["total"] == 1
    assert "Telefon zaufania" in seniors["items"][0]["title"]
    assert feed(client, user_id=4, q="seniorzy", kind="edukacyjna")["total"] == 0


def test_search_uses_words_when_embeddings_are_unavailable(client, monkeypatch):
    def offline(*args, **kwargs):
        raise llm.LLMUnavailable("offline")

    monkeypatch.setattr(llm, "embed", offline)
    result = feed(client, user_id=4, q="wiertarek i drabinek")
    assert "Tymczasowo" in result["notice"]
    assert result["items"][0]["id"] == 5
    assert "Słownictwo pasuje do Twojego opisu." in result["items"][0]["why"]
    assert feed(client, user_id=4, q="seniorzy")["items"][0]["id"] == 6
    assert feed(client, user_id=4, q="smog")["total"] == 0
    assert feed(client, user_id=4, q="wiertarki, narciarstwo, gokarty")["total"] == 0


def test_bump_changes_popular_order_and_counters(client):
    innovation_id = 3
    db.session.add(Interaction(innovation_id=1, user_id=2, type="zainteresowany"))
    db.session.commit()
    url = f"/api/innovations/{innovation_id}/bump"
    assert [item["id"] for item in feed(client, "popularne")["items"]] == [1]

    assert client.post(url, headers=headers(4)).get_json() == {"bumps": 1, "bumped": True}
    items = feed(client, "popularne", user_id=4)["items"]
    assert [item["id"] for item in items] == [innovation_id, 1]
    assert items[0]["bumped"] is True
    assert items[0]["bumps"] == 1
    assert items[1]["interest_count"] == 1
    assert feed(client, "popularne", user_id=5)["items"][0]["bumped"] is False

    assert client.post(url, headers=headers(4)).get_json() == {"bumps": 0, "bumped": False}
    assert [item["id"] for item in feed(client, "popularne")["items"]] == [1]


def test_popularity_decay_window_and_weights(client):
    now = datetime.now(UTC).replace(tzinfo=None)
    db.session.add_all([
        Interaction(innovation_id=1, user_id=1, type="podbicie", created_at=now - timedelta(days=8)),
        Interaction(innovation_id=2, user_id=2, type="komentarz", created_at=now),
        Interaction(innovation_id=3, user_id=3, type="podbicie", created_at=now - timedelta(days=15)),
        Interaction(innovation_id=4, user_id=4, type="obserwuje", created_at=now),
        Interaction(innovation_id=5, user_id=5, type="kontakt", created_at=now),
    ])
    db.session.commit()
    items = feed(client, "popularne")["items"]
    assert [item["id"] for item in items] == [2, 1, 4]
    assert items[0]["comments_count"] == 1
    newest = feed(client, "najnowsze")["items"]
    assert next(item for item in newest if item["id"] == 3)["bumps"] == 1


def test_gems_with_and_without_scores(client):
    empty = feed(client, "perelki")
    assert empty["total"] == 0
    assert "oceny potencjału" in empty["message"]

    scores = {1: 83, 2: 84, 3: rules.GEM_SCORE_THRESHOLD, 6: 81}
    for innovation_id, score in scores.items():
        db.session.get(Innovation, innovation_id).score = score
    for user_id in (1, 2, 3):
        db.session.add(Interaction(innovation_id=2, user_id=user_id, type="obserwuje"))
    db.session.commit()

    result = feed(client, "perelki")
    assert [item["id"] for item in result["items"]] == [6, 1]
    assert "81/100" in result["items"][0]["why"]
    assert "żadnych interakcji" in result["items"][0]["why"]
    empty_filter = feed(client, "perelki", domain="administracja")
    assert empty_filter["total"] == 0
    assert "message" not in empty_filter


def test_without_persona_and_pagination(client):
    newest = feed(client, "najnowsze", limit=2, offset=2)
    assert feed(client, limit=2, offset=2) == newest
    assert newest["total"] == 6
    assert len(newest["items"]) == 2
    past_end = feed(client, "najnowsze", limit=2, offset=6)
    assert past_end["total"] == 6
    assert past_end["items"] == []
    assert client.post("/api/innovations/3/bump").status_code == 401
    assert client.get("/api/me").status_code == 401
    assert client.patch("/api/me", json={}).status_code == 401
    assert client.post("/api/innovations/999/bump", headers=headers(4)).status_code == 404


def test_profile_recomputes_embedding_and_changes_feed(client, monkeypatch):
    monkeypatch.setattr(llm, "embed", lambda texts, **_: [vector(text) for text in texts])
    user = db.session.get(User, 2)
    team = Innovation(title="Projekt szuka zespołu", embedding=vector("zespołu"))
    db.session.execute(update(Innovation).values(embedding=vector("pozostałe")))
    db.session.add(team)
    user.embedding = vector(user.embedding_text())
    db.session.commit()

    before = feed(client, user_id=user.id)["items"][0]["id"]
    response = client.patch(
        "/api/me", headers=headers(user.id), json={"about": "  Szukam zespołu  ", "interests": ["kultura", "kultura"]},
    )
    assert response.status_code == 200
    profile = client.get("/api/me", headers=headers(user.id)).get_json()
    assert profile["about"] == "Szukam zespołu"
    assert profile["interests"] == ["kultura"]
    assert profile["name"] == user.name
    vector_in_db = db.session.scalar(select(User.embedding).where(User.id == user.id))
    assert list(vector_in_db) == vector(user.embedding_text())
    assert before != team.id
    assert feed(client, user_id=user.id)["items"][0]["id"] == team.id
    assert client.patch("/api/me", headers=headers(user.id), json={"interests": [{}]}).status_code == 400


def test_profile_save_is_atomic_if_model_unavailable(client, monkeypatch):
    user_id = 4
    profile = client.get("/api/me", headers=headers(user_id)).get_json()

    def offline(*args, **kwargs):
        raise llm.LLMUnavailable("offline")

    monkeypatch.setattr(llm, "embed", offline)
    response = client.patch("/api/me", headers=headers(user_id), json={"about": "Nowy opis", "interests": ["kultura"]})
    assert response.status_code == 503
    assert client.get("/api/me", headers=headers(user_id)).get_json() == profile


def test_explain_exposes_ranking_rules(client):
    explain = client.get("/api/feed/explain").get_json()
    titles = {section["title"] for section in explain["sections"]}
    assert titles >= {"Dla Ciebie", "Popularne", "Ukryte perełki", "Rola i potrzeby twórców"}
