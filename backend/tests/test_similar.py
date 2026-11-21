import json

import pytest

from app.config import EMBED_DIM
from app.extensions import db
from app.models import Innovation
from app.services import decisions, llm, novelty

IDEA = "Uczniowie pomagają pierwszakom w matematyce na cotygodniowych zajęciach w parach."


def _answer(relation, **probabilities):
    return {"choice": relation, "probabilities": probabilities or {relation: 1.0}, "engine": "test"}


def _card(title, *, description=IDEA, vector=None, organization_id=2):
    card = Innovation(
        title=title,
        summary=description,
        embedding=vector if vector is not None else llm.embed([IDEA])[0],
        organization_id=organization_id,
        domains=["edukacja"],
        keywords=["zajęcia w parach"],
        raw={"source": "fixture"},
    )
    db.session.add(card)
    db.session.commit()
    return card


def _vector(x, y):
    return [x, y] + [0.0] * (EMBED_DIM - 2)


def test_freshness_scale():
    assert novelty.freshness([]) == 100
    assert novelty.freshness([1.0, 0.52]) == 0
    assert novelty.freshness([0.52] * 3) == 41
    assert novelty.freshness([0.22]) == 78
    assert novelty.freshness([0.0] * 3) == 100


def test_semantic_rank_and_shared_features(client, monkeypatch):
    monkeypatch.setattr(llm, "embed", lambda texts, **kwargs: [_vector(1, 0)])
    different = _card("Inna forma pomocy w matematyce")
    same = _card("Tutoring rówieśniczy", vector=_vector(0.8, 0.6))
    _card("Niezwiązane rozwiązanie poniżej progu", vector=_vector(0, 1))
    calls = []

    def decide(state, question, **kwargs):
        calls.append(state)
        assert question["type"] == "choice"
        assert set(question["criteria"]) == set(novelty.RELATION_WEIGHTS)
        assert json.loads(state)["A"] == IDEA
        if "Tutoring" in json.loads(state)["B"]:
            return _answer("to_samo", to_samo=0.8, ten_sam_problem=0.2)
        return _answer("ten_sam_problem")

    monkeypatch.setattr(decisions, "decide_one", decide)
    response = client.post("/api/novelty", json={"text": IDEA})
    assert response.status_code == 200
    body = response.json
    assert body["compared"] == len(calls) == 2
    assert [item["innovation"]["id"] for item in body["nearest"]] == [same.id, different.id]
    first = body["nearest"][0]
    assert first["similarity"] == pytest.approx(0.8)
    assert first["overlap"] == pytest.approx(0.8 + 0.2 * novelty.RELATION_WEIGHTS["ten_sam_problem"])
    assert first["relation"] == "to_samo"
    assert first["shared"]["domains"] == ["edukacja"]
    assert body["novelty"] < 20


def test_similar_excludes_self_persists_and_refreshes(client, monkeypatch):
    source = _card("Oceniana innowacja")
    other = _card("Bliźniacze zajęcia w parach", vector=llm.embed([novelty.card_text(source)])[0])
    calls = []

    def decide(state, question, **kwargs):
        calls.append(state)
        assert "Oceniana innowacja" not in json.loads(state)["B"]
        return _answer("to_samo")

    monkeypatch.setattr(decisions, "decide_one", decide)
    source_id, other_id = source.id, other.id
    path = f"/api/innovations/{source_id}/similar?limit=1"
    first = client.get(path)
    assert first.status_code == 200
    assert first.json["novelty"] == 0
    assert [item["innovation"]["id"] for item in first.json["nearest"]] == [other_id]
    assert first.json["nearest"][0]["same_organization"] is True
    assert first.json["nearest"][0]["shared"]["keywords"] == ["zajęcia w parach"]
    assert db.session.get(Innovation, source_id).novelty == 0
    assert db.session.get(Innovation, source_id).raw["source"] == "fixture"
    assert client.get(path).json == first.json
    assert len(calls) == 1
    refreshed = client.post(f"/api/innovations/{source_id}/novelty")
    assert refreshed.status_code == 200
    assert refreshed.json == first.json
    assert len(calls) == 2


@pytest.mark.parametrize("payload", [{"text": "zbyt krótki"}, {"text": " " * 50}, {"text": 123}, {}])
def test_rejects_short_or_missing_text(client, payload):
    assert client.post("/api/novelty", json=payload).status_code == 400


def test_vector_fallback_and_unavailable_embeddings(client, monkeypatch):
    _card("Bliski opis")

    def unavailable(*args, **kwargs):
        raise llm.LLMUnavailable("model niedostępny")

    monkeypatch.setattr(decisions, "decide_one", unavailable)
    response = client.post("/api/novelty", json={"text": IDEA})
    assert response.status_code == 200
    assert response.json["engine"].startswith("embeddings:")
    assert response.json["novelty"] == 0
    match = response.json["nearest"][0]
    assert match["similarity"] == pytest.approx(1.0)
    assert match["relation"] is None and match["probabilities"] == {}

    monkeypatch.setattr(llm, "embed", unavailable)
    assert client.post("/api/novelty", json={"text": IDEA}).status_code == 503


def test_duplicate_scan_only_reads_saved_cross_organization_pairs(app, client, monkeypatch):
    first = _card("Zajęcia w pierwszej szkole", organization_id=2)
    second = _card("Zajęcia w drugiej szkole", organization_id=3)
    same_org = _card("Inna metoda w pierwszej szkole", organization_id=2)
    calls = []
    interrupted = True

    def decide(state, question, **kwargs):
        calls.append(state)
        if "Inna metoda" in state:
            if interrupted:
                raise llm.LLMUnavailable("model niedostępny w połowie skanu")
            return _answer("ten_sam_problem")
        return _answer("to_samo")

    monkeypatch.setattr(decisions, "decide_one", decide)
    assert client.get("/api/duplicates").json == {"items": [], "total": 0}
    assert not calls

    runner = app.test_cli_runner()
    scan = runner.invoke(args=["similar", "scan"])
    assert scan.exit_code == 1
    assert "wznowieniu" in scan.output
    partial = client.get("/api/duplicates").json
    assert partial["total"] == 1
    assert partial["items"][0]["relation"] == "to_samo"

    interrupted = False
    resumed = runner.invoke(args=["similar", "scan"])
    assert resumed.exit_code == 0, resumed.exception
    assert "wznowiono 1" in resumed.output

    response = client.get("/api/duplicates?limit=1")
    assert response.status_code == 200
    assert response.json["total"] == 2
    pair = response.json["items"][0]
    assert pair["left"]["id"] == first.id
    assert pair["right"]["id"] == second.id
    assert pair["relation"] == "to_samo"
    assert db.session.get(Innovation, same_org.id).raw["source"] == "fixture"
    assert len(calls) == 3

    resumed = runner.invoke(args=["similar", "scan"])
    assert resumed.exit_code == 0, resumed.exception
    assert "wznowiono 2" in resumed.output
    assert len(calls) == 3
