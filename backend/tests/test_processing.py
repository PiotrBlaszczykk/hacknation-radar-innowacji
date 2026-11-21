import json
from collections import Counter

import pytest
from sqlalchemy import delete, func, select, text

from app import matching, paths, processing, scoring
from app.extensions import db
from app.models import Assessment, Event, Innovation, Interaction, Match, Recommendation
from app.processing import review
from app.services import decisions, llm, novelty, structuring

HEADERS = {"X-User-Id": "3"}
EVIDENCE = "W pierwszym półroczu 2026 r. urzędnik odwiedził 190 mieszkańców."
TABLES = (Event, Assessment, Recommendation, Match)


def counts():
    return tuple(db.session.scalar(select(func.count()).select_from(table)) for table in TABLES)


def add_card(title, **kwargs):
    values = dict(
        origin="radar", status="wykryta", claimed=False, source_name="test", source_ref=title,
        description=f"{title}. Opis konkretnego celu i przebiegu projektu.",
    )
    db.session.add(card := Innovation(title=title, **(values | kwargs)))
    db.session.commit()
    return card


def cli(app, *options, expected=0):
    response = app.test_cli_runner().invoke(args=["processing", "run", *options])
    assert response.exit_code == expected, response.output
    line = next(line for line in response.output.splitlines() if line.startswith("{"))
    return json.loads(line)


@pytest.fixture
def models(app, monkeypatch):
    db.session.execute(delete(Innovation))
    db.session.commit()
    calls = Counter()

    def structure(source):
        calls["structure"] += 1
        probability = 0.9
        if source.startswith(("Badania", "Potwierdzona", "Broker")):
            probability = 0.1
        elif source.startswith("Brak sygnału"):
            probability = None
        return {
            "card": {
                "title": "Propozycja tytułu", "summary": "Streszczenie.", "problem": "Problem.",
                "solution": "Rozwiązanie.", "results": "Wynik.", "domains": [], "kind": "procesowa",
                "stage": "prototyp", "keywords": ["projekt"], "support_needs": ["zespol"],
            },
            "engine": {"tags": "basal-serve:test", "text": "test"},
            "version": structuring.STRUCTURING_VERSION,
            "is_innovation": probability,
        }

    def classify(title, description):
        calls["review"] += 1
        return {
            "classification": "badania", "probability": 0.85, "quote": description, "calibrated": True,
            "practical_use": "naukowe", "scientific_probability": 0.7,
        }

    def similar(source, *, exclude_id, limit, where, strict):
        calls["novelty"] += 1
        assert strict
        corpus = set(db.session.scalars(select(Innovation.id).where(where)))
        assert db.session.get(Innovation, exclude_id).embedding is not None
        assert all(db.session.get(Innovation, cid).status != "archiwum" for cid in corpus)
        return {"novelty": 100, "verdict": "Brak podobnych", "nearest": [], "compared": len(corpus) - 1, "engine": "test"}

    def decide(source, questions, **kwargs):
        if "potrzeba" in questions or "proba" in questions:
            calls["ocena"] += 1
        result = {}
        for name, question in questions.items():
            if "none" in question["criteria"]:
                choice = "none"
            elif "unknown" in question["criteria"]:
                choice = "confirmed" if name == "proba" and source == EVIDENCE else "unknown"
            else:
                choice = next(iter(question["criteria"]))
            result[name] = {"choice": choice, "probabilities": {choice: 0.9}, "engine": "test", "calibrated": True}
        return result

    monkeypatch.setattr(structuring, "structure_text", structure)
    monkeypatch.setattr(review, "research_evidence", classify)
    monkeypatch.setattr(novelty, "check_novelty", similar)
    monkeypatch.setattr(decisions, "decide", decide)
    return calls


def test_dry_run_limit_interrupt_resume_and_identical_rerun(app, models):
    first = add_card("Zastosowanie")
    second = add_card("Kolejne zastosowanie")
    preview = cli(app, "--dry-run", "--limit", "1")
    assert preview["kroki"] == {}
    assert not models and not first.raw

    def interrupt(message):
        if message.startswith(f"I · karta {first.id} "):
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        processing.run(interrupt, limit=1)
    assert first.raw["processing"]["embedding"]["result"] == "zapisany"
    assert "novelty" not in first.raw["processing"]
    assert not second.raw

    limited = cli(app, "--limit", "1")
    assert limited["kroki"] == dict(structure=1, review=1, embedding=1, novelty=1, assessment=1, path=1, matches=1)
    assert "matches" not in second.raw["processing"]
    assert cli(app)["kroki"] == dict(novelty=1, assessment=1, path=1, matches=1)
    assert models["structure"] == models["novelty"] == 2
    assert first.results == "Wynik." and first.raw["structured_title"] == "Propozycja tytułu"
    assert first.keywords == ["projekt"] and first.support_needs == ["zespol"]
    assert first.raw["processing"]["matches"]["count"] == 0
    assert first.raw[matching.INNOVATION_CACHE_KEY]
    snapshot = models.copy(), counts()
    assert cli(app)["kroki"] == {}
    assert (models, counts()) == snapshot

    # Zmiana zbioru przelicza świeżość wcześniej przygotowanych kart bez nowych ocen i ścieżek.
    add_card("Nowe źródło", source_name="inne")
    incremental = cli(app)
    assert incremental["kroki"]["novelty"] == 3
    assert incremental["kroki"]["assessment"] == incremental["kroki"]["path"] == 1


def test_outage_preserves_structure_and_transient_failure_rolls_back(app, models, monkeypatch):
    first = add_card("Zastosowanie")
    second = add_card("Drugi kandydat")
    real_embed = llm.embed

    def offline(*args, **kwargs):
        raise llm.LLMUnavailable("Brak embeddingów")

    monkeypatch.setattr(llm, "embed", offline)
    interrupted = cli(app, expected=1)
    assert interrupted["kroki"] == {"structure": 1, "review": 1}
    assert interrupted["bledy"][0] | {"at": None} == {
        "id": first.id, "step": "embedding", "reason": "Brak embeddingów", "model_unavailable": True, "at": None,
    }
    assert first.results == "Wynik."
    assert "embedding" not in first.raw["processing"]
    assert not second.raw and models["structure"] == 1
    monkeypatch.setattr(llm, "embed", real_embed)

    real_score = processing.HANDLERS["assessment"]

    def broken_assess(card):
        if card.id == first.id:
            real_score(card)
            raise ValueError("Błąd zapisu oceny")
        return real_score(card)

    with monkeypatch.context() as scoped:
        scoped.setitem(processing.HANDLERS, "assessment", broken_assess)
        retry = cli(app, expected=1)
    assert retry["bledy"][0]["step"] == "assessment"
    assert "assessment" not in first.raw["processing"]
    assert db.session.scalar(select(Assessment).where(Assessment.innovation_id == first.id)) is None
    assert "matches" in second.raw["processing"]
    assert models["structure"] == 2
    assert cli(app)["kroki"] == dict(assessment=1, path=1, matches=1)


def test_archive_requires_evidence_and_is_absent_from_all_feed_tabs(app, client, models):
    archived = add_card("Badania podstawowe", score=95)
    archived_id = archived.id
    missing = add_card("Brak sygnału")
    confirmed = add_card("Potwierdzona", claimed=True, raw={"is_innovation": 0.03})
    db.session.add(Interaction(innovation_id=archived_id, user_id=3, type="podbicie"))
    db.session.commit()
    result = cli(app)
    assert result["zrodla"]["test"]["archiwalne"] == 1
    assert archived.raw["radar_review"]["decision"] == "odrzucona"
    assert archived.raw["radar_review"]["signal"]["research"]["quote"] == archived.description
    assert archived.embedding is None and "novelty" not in archived.raw["processing"]
    assert missing.raw["radar_review"]["decision"] == "przeglad"
    assert confirmed.raw["radar_review"]["decision"] == "chroniona"
    for tab in ("dla_ciebie", "popularne", "perelki", "najnowsze"):
        response = client.get("/api/feed", query_string={"tab": tab, "limit": 50}, headers=HEADERS)
        assert response.status_code == 200
        assert archived_id not in {row["id"] for row in response.json["items"]}
    assert client.get(f"/api/innovations/{archived_id}").json["status"] == "archiwum"


def test_broker_work_and_institutional_evidence_are_preserved(app, client, models):
    broker = add_card("Broker", status="w_kontakcie", score=81, path="wdrozenie", results="Korekta brokera.")
    draft = Assessment(
        innovation_id=broker.id, criteria_version="1.1", total=81, confidence=None, assessor_id=3,
        items=[{"weight": 20, "score": 4.05}], engine="basal-serve:test",
    )
    recommendation = Recommendation(innovation_id=broker.id, path="wdrozenie", engine="reguly")
    contact = Match(innovation_id=broker.id, organization_id=5, score=0.8, status="kontakt")
    db.session.add_all((draft, recommendation, contact))
    db.session.flush()
    db.session.add(Event(
        innovation_id=broker.id, type=paths.ACCEPTED, actor_id=3, payload={"recommendation_id": recommendation.id},
    ))
    institution = add_card(
        "Mobilny Urzędnik", description=f"Urzędnik dojeżdża do mieszkańców. {EVIDENCE}",
        source_name="strony_instytucji", results=EVIDENCE, structured_by="basal-serve:test",
        raw={"evidence": EVIDENCE, "is_innovation": 0.2, "structuring_version": structuring.STRUCTURING_VERSION},
    )
    db.session.commit()

    cli(app)
    assert broker.status == "w_kontakcie" and broker.path == "wdrozenie" and broker.score == 81
    assert broker.results == "Korekta brokera."
    assert broker.raw["processing"]["assessment"]["id"] == draft.id
    assert paths.latest_recommendation(broker.id).id == recommendation.id
    assert contact.status == "kontakt"
    assert institution.raw["evidence"] == institution.results == EVIDENCE
    assessment = client.get(f"/api/innovations/{institution.id}/assessment").json
    evidence = next(item for item in assessment["items"] if item["key"] == "dowody")
    assert [(check["key"], check["status"]) for check in evidence["checks"]] == [
        ("proba", "confirmed"), ("efekt", "unknown"), ("odniesienie", "unknown"),
    ]
    assert evidence["checks"][0]["evidence"] == EVIDENCE
    assert assessment["needs_review"] and not assessment["ranked"]
    assert institution.score is None and "assessment" in institution.raw["processing"]


def test_concurrent_run_is_rejected(app, models):
    add_card("Projekt")
    with db.engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": processing.LOCK})
        response = app.test_cli_runner().invoke(args=["processing", "run"])
        assert response.exit_code == 1 and "już działa" in response.output
    assert not models


def test_reopened_archive_and_explicit_manual_edits_are_respected(app, client, models):
    archived = add_card("Badania do decyzji brokera")
    kept = add_card("Zastosowanie")
    assert client.patch(f"/api/innovations/{kept.id}", json={"problem": "Opis człowieka."}).status_code == 200
    cli(app)
    assert kept.problem == "Opis człowieka."
    assert kept.raw["manual_fields"] == ["problem"]
    assert archived.status == "archiwum"

    response = client.patch(f"/api/innovations/{archived.id}", headers=HEADERS, json={"status": "wykryta"})
    assert response.status_code == 200
    cli(app)
    assert archived.status != "archiwum"
    assert archived.raw["radar_review"]["decision"] == "chroniona"
    assert "matches" in archived.raw["processing"]


def test_updated_filter_revisits_only_automatic_archives(app, client, models, monkeypatch):
    auto = add_card("Badania z próbą")
    manual = add_card("Badania z inną decyzją")
    cli(app)
    assert auto.status == manual.status == "archiwum"
    for status in ("wykryta", "archiwum"):
        assert client.patch(f"/api/innovations/{manual.id}", headers=HEADERS, json={"status": status}).status_code == 200

    classify = review.research_evidence
    monkeypatch.setattr(review, "VERSION", "review-updated")
    monkeypatch.setattr(review, "research_evidence", lambda title, description: {
        **classify(title, description), "practical_use": "praktyczne",
    })
    assert cli(app)["kroki"] == dict(review=1, embedding=1, novelty=1, assessment=1, path=1, matches=1)
    assert auto.raw["radar_review"]["decision"] == "przeglad"
    assert auto.status != "archiwum" and manual.status == "archiwum"
    assert cli(app)["kroki"] == {}
