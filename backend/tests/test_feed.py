from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.config import EMBED_DIM
from app.extensions import db
from app.feed import rules
from app.models import Assessment, Innovation, Interaction, User
from app.scoring import CRITERIA_VERSION
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


def add_gem(title, *, quote="Użyto rozwiązania podczas pilotażu.", version=CRITERIA_VERSION, **changes):
    fields = dict(
        score=35, results=quote, source_url="https://example.org/raport", domains=["edukacja"],
        created_at=datetime(2025, 1, 1),
    )
    card = Innovation(title=title, **(fields | changes))
    db.session.add(card)
    db.session.flush()
    if version:
        db.session.add(Assessment(
            innovation_id=card.id, criteria_version=version, engine="test", total=card.score or 0,
            items=[
                {"key": "dowody", "weight": 20, "checks": [{"key": "proba", "status": "confirmed", "evidence": quote}]},
                {"key": "problem", "weight": 20}, {"key": "wplyw", "weight": 10},
            ],
        ))
    return card.id


def test_gems_need_a_comparable_corpus_even_with_underlying_scores(client):
    empty = feed(client, "perelki")
    assert empty["total"] == 0
    assert "co najmniej 3 udokumentowanych kart" in empty["message"]
    first = add_gem("Opis użycia")
    second = add_gem("Próba w prototypie", domains=["kultura"])
    add_gem("Wyższy wynik, ale starsza skala", score=90, version="1.1")
    add_gem("Brak wyniku rankingu", score=None)
    add_gem("Wynik bez oceny", score=90, version=None)
    add_gem("Przykładowe dane", source_name="przyklad_dane", score=85)
    add_gem("Zarchiwizowany", status="archiwum", score=90)
    db.session.commit()

    assert feed(client, "perelki")["total"] == 0
    verified = add_gem(
        "Wynik opisany przez instytucję", origin="radar", source_name="strony_instytucji",
        raw={"evidence": "Dzieci przeprowadziły zajęcia w szkolnym ogródku."},
        results="Dzieci przeprowadziły zajęcia w szkolnym ogródku.", quote=None,
    )
    db.session.commit()
    result = feed(client, "perelki")
    assert [item["id"] for item in result["items"]] == [verified, second, first]
    assert result["items"][0]["why"] == "Źródło dokumentuje użycie lub wynik zaobserwowany w praktyce, a liczba publicznych interakcji przy karcie to 0."
    assert [item["id"] for item in feed(client, "perelki", domain="kultura")["items"]] == [second]
    assert feed(client, "perelki", domain="administracja")["message"] == rules.GEM_EMPTY_IN_SCOPE


def test_gems_require_documented_use_and_exclude_popular_cards(client):
    first = add_gem("Mniej uwagi", score=24)
    more = add_gem("Aktywność", score=50)
    popular = add_gem("Popularny wpis", score=80)
    add_gem("Plan, który model zaliczył do prób", score=80, quote="Prototyp zostanie wdrożony.", results=None)
    add_gem("Cytat z innego miejsca", score=80, results="Nie podano wyniku.")
    add_gem("Brak źródła", score=99, source_url=None)
    db.session.add_all([
        *[Interaction(innovation_id=popular, user_id=user, type="obserwuje") for user in (1, 2, 3)],
        Interaction(innovation_id=first, user_id=1, type="kontakt"),
        Interaction(innovation_id=more, user_id=1, type="obserwuje"),
        Interaction(innovation_id=more, user_id=2, type="podbicie"),
    ])
    db.session.commit()

    result = feed(client, "perelki")
    assert [item["id"] for item in result["items"]] == [first, more]
    assert result["items"][0]["why"].endswith("interakcji przy karcie to 0.")
    assert result["items"][1]["why"].endswith("interakcji przy karcie to 2.")


def test_gems_ties_keep_the_same_order_across_pages(client):
    tied = [add_gem(f"Karta {index}") for index in range(12)]
    newer = add_gem("Nowsza karta z taką samą oceną", created_at=datetime(2025, 2, 1))
    db.session.commit()

    expected = [newer, *reversed(tied)]
    for limit in (3, 5):
        ids = []
        for offset in range(0, len(expected), limit):
            page = feed(client, "perelki", limit=limit, offset=offset)
            assert page["total"] == len(expected)
            ids.extend(item["id"] for item in page["items"])
        assert ids == expected
    past_end = feed(client, "perelki", limit=2, offset=50)
    assert past_end["total"] == len(expected) and past_end["items"] == []


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
    assert titles >= {"Dla Ciebie · rekomendacje z profilu (100%)", "Dla Ciebie · po wpisaniu zapytania (100%)", "Popularne", "Ukryte perełki", "Rola i potrzeby twórców"}


def test_network_demo_reactions_and_privacy(client):
    from app.seed.social_demo import install

    viewer = install()
    assert install() == viewer
    timeline = lambda: feed(client, tab="obserwowani", user_id=viewer)["items"]
    item = next(post for post in timeline() if post["id"] == 3)
    assert item["repost_by"] and item["comments"] and item["follows_author"]
    path = "/api/innovations/3/interactions"
    assert client.post(path, headers=headers(viewer), json={"type": "serce"}).status_code == 201
    assert next(post for post in timeline() if post["id"] == 3)["liked"]
    client.post(path, headers=headers(viewer), json={"type": "komentarz", "body": "Otwarty komentarz"})
    client.post(path, headers=headers(viewer), json={"type": "kontakt", "body": "Prywatna prośba"})
    post = next(post for post in timeline() if post["id"] == 3)
    assert post["comments"][0]["body"] == "Otwarty komentarz"
    assert "Prywatna prośba" not in str(timeline())
    for active in (False, True):
        result = client.put("/api/following/person/2", headers=headers(viewer), json={"active": active})
        assert result.get_json()["active"] == active
        assert next(post for post in timeline() if post["id"] == 3)["follows_author"] == active
