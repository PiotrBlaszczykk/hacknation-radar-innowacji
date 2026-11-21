import json
import sys
from collections import Counter
from types import ModuleType

import httpx
import pytest
from sqlalchemy import func, select

from app.extensions import db
from app.models import Innovation, Organization
from app.radar import radon
from app.radar.importer import run
from app.radar.selection import select_project

LEADER = "11111111-2222-4333-8444-555555555555"
PARTNER = "33333333-2222-4333-8444-555555555555"
INSTITUTIONS = {
    LEADER: {
        "institutionUuid": LEADER,
        "name": "Politechnika Testowa",
        "iKindName": "Uczelnia publiczna",
        "voivodeship": "Podkarpackie",
        "city": "Rzeszów",
        "www": "pt.example.org",
        "managerSurname": "Dane-osobowe",
    },
    PARTNER: {
        "institutionUuid": PARTNER,
        "name": "Instytut Testowy",
        "iKindName": "Instytut badawczy",
        "voivodeship": "mazowieckie",
    },
}
DESCRIPTION = (
    "Zespół zaprojektował czujnik pomiaru wilgotności gleby, który ogranicza zużycie wody. "
    "Czujnik zasilany jest baterią i przesyła pomiary do sterownika nawadniania. "
    "W ramach prac zespół będzie testował odporność obudowy na niekorzystne warunki pogodowe "
    "oraz porówna wskazania urządzenia z wynikami uzyskanymi przy użyciu aparatury laboratoryjnej."
)


def project(ref="radon-1", *, region=True, **updates):
    leader, partner = (LEADER, PARTNER) if region else (PARTNER, LEADER)
    return {
        "projectUuid": ref,
        "projectTitlePl": f"Czujnik wilgotności {ref}",
        "projectAbstractPl": DESCRIPTION,
        "keywords": "woda, czujniki; woda",
        "projectStartDate": "2020-06-03",
        "projectEndDate": "2024-01-31",
        "projectClassification": "LIDER",
        "financingInstitutions": [
            {
                "financingInstitutionName": "Narodowe Centrum Badań i Rozwoju",
                "email": "kierownik@example.org",
            }
        ],
        "implementingInstitutions": [
            {"leader": "Nie", "institutionUuid": partner, "nameOfContact": "Dane-osobowe"},
            {"leader": "Tak", "institutionUuid": leader},
        ],
        "projectManagers": [{"firstName": "Joanna", "lastName": "Dane-osobowe"}],
        "totalFunds": "123456.78",
        **updates,
    }


@pytest.fixture
def cached_radon(app, monkeypatch, tmp_path):
    app.config["RADON_CACHE_DIR"] = tmp_path
    requests = []

    def response(request: httpx.Request):
        endpoint = request.url.path.rsplit("/", 1)[-1]
        token = request.url.params.get("token")
        requests.append((endpoint, token))
        assert request.url.params["resultNumbers"] == "100"
        if endpoint == "institutions":
            rows, total, next_token = list(INSTITUTIONS.values()), 2, "token-final"
        else:
            assert request.url.params["projectStartDate"] == "2019-01-01"
            if token is None:
                rows = [project("outside", region=False), project("region-1")]
                next_token = "kolejna+strona="
            else:
                assert token == "kolejna+strona="
                rows = [project("region-2"), project("demo", region=False)]
                next_token = "token-final"
            total = 4
        return httpx.Response(200, json={"results": rows, "pagination": {"maxCount": total, "token": next_token}})

    monkeypatch.setattr(
        "app.radar.importer.http_client",
        lambda: httpx.Client(transport=httpx.MockTransport(response)),
    )
    monkeypatch.setattr("app.radar.radon.time.sleep", lambda _: None)
    return tmp_path, requests


@pytest.mark.parametrize("changes", [
    {"projectAbstractPl": "zbyt krótki"},
    {"projectStartDate": "2018-12-31"},
    {"projectStartDate": "2021-99-01"},
    {"projectTitlePl": ""},
    {"projectClassification": "OPUS", "financingInstitutions": []},
])
def test_reject_project(changes):
    assert select_project(project(**changes), INSTITUTIONS, Counter()) is None


def test_ncbr_matches_even_without_program():
    candidate = select_project(project(projectClassification=None), INSTITUTIONS, Counter())
    assert candidate
    assert candidate.raw["financing_institutions"] == ["Narodowe Centrum Badań i Rozwoju"]


def test_mapping_priority_privacy_and_idempotence(cached_radon):
    directory, requests = cached_radon
    result = run(directory, 1)
    assert result["created"] == 2
    assert result["selection"]["selected_regional"] == 2
    assert result["selection"]["eligible"] == 4
    assert result["missing_embeddings"] == 0
    assert requests == [("institutions", None), ("projects", None), ("projects", "kolejna+strona=")]

    records = db.session.scalars(select(Innovation).where(Innovation.source_name == radon.SOURCE)).all()
    assert {item.source_ref for item in records} == {"region-1", "region-2"}
    record = records[0]
    assert record.title.startswith("Czujnik wilgotności")
    assert record.summary == ". ".join(DESCRIPTION.split(". ")[:2]) + "."
    assert record.description == DESCRIPTION
    assert record.keywords == ["woda", "czujniki"]
    assert record.source_url == f"https://radon.nauka.gov.pl/dane/profil/{record.source_ref}"
    assert record.origin == "radar" and record.status == "wykryta"
    assert record.claimed is False and record.structured_by is None
    assert record.embedding is not None
    assert [event.type for event in record.events] == ["wykryta"]
    assert record.organization.name == "Politechnika Testowa"
    assert record.organization.kind == "uczelnia"
    assert record.organization.city == "Rzeszów"
    assert record.organization.region == "podkarpackie"
    assert record.organization.website == "https://pt.example.org"
    assert record.organization.external_ids == {"radon": LEADER}
    assert record.raw["total_funds"] == "123456.78"
    assert record.raw["program"] == ["LIDER"]
    assert record.raw["partners"][0]["name"] == "Instytut Testowy"

    for body in [json.dumps(record.raw), *(file.read_text() for file in directory.glob("*.json"))]:
        assert "Dane-osobowe" not in body
        assert "projectManagers" not in body
        assert "kierownik@example" not in body
    replay = run(directory, 1)
    assert (replay["fetched"], replay["created"], replay["skipped"]) == (2, 0, 2)
    assert len(requests) == 3
    assert db.session.scalar(select(func.count()).select_from(Organization).where(
        Organization.external_ids["radon"].astext == LEADER,
    )) == 1


def test_radar_api_and_cli(app, client, cached_radon):
    original_total = client.get("/api/innovations?origin=radar&limit=3").get_json()["total"]
    first = app.test_cli_runner().invoke(args=["radar", "run", "--source", radon.SOURCE, "--limit", "2"])
    assert first.exit_code == 0, first.output
    assert "dodano 2" in first.output

    assert client.post("/api/radar/run", json={"source": "nieznane"}).status_code == 400
    assert client.post("/api/radar/run", json={"source": radon.SOURCE, "limit": True}).status_code == 400
    result = client.post("/api/radar/run", json={"source": radon.SOURCE, "limit": 1}).get_json()
    assert (result["fetched"], result["created"], result["skipped"]) == (1, 1, 0)
    item = result["created_items"][0]
    assert client.get(f'/api/innovations/{item["id"]}').get_json()["title"] == item["title"]
    assert client.get("/api/innovations?origin=radar&limit=3").get_json()["total"] == original_total + 3
    sources = client.get("/api/radar/sources").get_json()["items"]
    active = sources[0]
    assert active["count"] == 3 and active["rules"]
    assert active["last_run"]["created"] == 1 and active["last_run"]["finished_at"]
    assert all(item["status"] == "aktywne" for item in sources if item["name"] in {radon.SOURCE, "strony_instytucji"})


def test_enrich_commits_each_record_and_reuses_existing_raw(app, cached_radon, monkeypatch):
    directory, _ = cached_radon
    run(directory, 2)
    module = ModuleType("app.services.structuring")
    module.structure_text = lambda _: {
        "card": {
            "summary": "Czujnik do oszczędzania wody.", "problem": "Zużycie wody",
            "solution": "Sterowanie nawadnianiem", "kind": "technologiczna",
            "stage": "prototyp", "domains": ["energia_srodowisko", "nieznany"],
        },
        "engine": {"tags": "tagger", "text": "writer"},
        "is_innovation": 0.87,
    }
    monkeypatch.setitem(sys.modules, module.__name__, module)
    runner = app.test_cli_runner()
    result = runner.invoke(args=["radar", "enrich", "--limit", "1"])
    assert result.exit_code == 0, result.output
    rows = db.session.scalars(select(Innovation).where(
        Innovation.source_name == radon.SOURCE,
    ).order_by(Innovation.id)).all()
    enriched, pending = rows
    assert enriched.structured_by == "tagger + writer"
    assert enriched.stage == "prototyp"
    assert enriched.domains == ["energia_srodowisko"]
    assert enriched.raw["total_funds"] == "123456.78"
    assert enriched.raw["is_innovation"] == 0.87
    assert pending.structured_by is None
    assert runner.invoke(args=["radar", "enrich", "--limit", "1"]).exit_code == 0
    assert pending.structured_by == "tagger + writer"



def test_cache_only_handles_an_incomplete_snapshot(cached_radon):
    directory, requests = cached_radon
    assert run(directory, 1)["created"] == 2
    last_page = next(
        path for path in directory.glob("projects-*.json")
        if json.loads(path.read_bytes())["pagination"]["token"] == "token-final"
    )
    last_page.unlink()
    result = run(directory, 2, cached_only=True)
    assert not result["selection"]["complete_scan"]
    assert result["selection"]["scanned"] == 2
    assert result["created"] == 0
    assert len(requests) == 3
