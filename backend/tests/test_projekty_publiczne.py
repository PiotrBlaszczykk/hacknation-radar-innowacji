from datetime import date
from io import BytesIO
from types import SimpleNamespace

from openpyxl import Workbook
from sqlalchemy import select

from app.extensions import db
from app.models import Innovation, Organization
from app.radar import importer, projekty_publiczne, radon
from app.radar.instytucje.fetch import Page
from app.radar.selection import Candidate
from app.radar.projekty_publiczne.collect import (
    NCBR_URL, PublicSourceError, ncbr, workbook_projects, workbook_url,
)


def test_interreg_finds_latest_attachment_and_reads_columns_by_header():
    page = Page('''
        <a href="/wp-content/uploads/2026/11/Wykaz_projektow_Interreg_2021-2027_art_49_CPR_20261116.xlsx">Lista</a>
        <a href="/wp-content/uploads/2026/07/Wykaz_projektow_Interreg_2021-2027_art_49_CPR_20260701.xlsx">Archiwum</a>
        <a href="https://example.net/wp-content/uploads/2027/01/Wykaz_projektow_Interreg_20270101.xlsx">Obcy</a>
    ''')
    assert workbook_url(page).endswith("20261116.xlsx")
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Projekty"
    sheet.append(["Wykaz projektów Interreg"])
    sheet.append([
        "Nazwa partnera wiodącego i partnerów / Lead partner and partners name",
        "Tytul projektu / Project title", "Numer projektu / Project no.", "Opis projektu / Project description",
        "Nazwa partnera wiodącego / Lead partner name", "Województwo / Voivodeship or region",
        "Miejscowość / City", "Program / Programme",
    ])
    sheet.append(["Gmina B | Gmina A", "Most danych", "A-123/26", "Mapa dla urzędu", "Gmina A", "POMORSKIE", "Hel", "PL–SK"])
    payload = BytesIO()
    workbook.save(payload)
    [project] = workbook_projects(payload.getvalue())
    assert (project["ref"], project["lead"], project["partners"], project["sheet"], project["row"]) == (
        "A-123/26", "Gmina A", "Gmina B | Gmina A", "Projekty", 3,
    )


def test_ncbr_uses_article_beneficiary_and_checks_use_evidence():
    article = '''
        <nav>Szkoły to odbiorca</nav>
        <article id="main-content">
            <h3>Tytuł projektu</h3><p>Narzędzie programu</p>
            <h3>Nazwa Beneficjenta/Beneficjentów</h3><p>Uniwersytet A</p>
            <h3>Odbiorcy</h3><p>Uczniowie czterech szkół brali udział.</p>
        </article>
    '''
    index = '<details><a href="/web/ncbr/projekt">Dowiedz się więcej</a></details>'
    reader = SimpleNamespace(html=lambda url: (index, Page(index)) if url == NCBR_URL else (article, Page(article)))
    [candidate], stats = ncbr(reader, {"projekt": {"match": "uczniowie czterech szkół brali udział"}})
    assert candidate["organization"] == "Uniwersytet A"
    assert candidate["source_title"] == "Narzędzie programu"
    assert stats["eligible"] == 1
    rows, stats = ncbr(reader, {"projekt": {"match": "szkoły to odbiorca"}})
    assert rows == [] and stats["unavailable"]


def project(ref, title="Projekt pomiarowy"):
    return {
        "ref": ref, "title": f"Mapa jakości powietrza {ref}", "source_title": title,
        "url": f"https://www.gov.pl/web/ncbr/{ref}", "organization": "Publiczny Instytut A",
        "organization_kind": "instytucja_publiczna", "evidence": "Urząd uruchomił publiczną mapę.",
        "problem": "Brak informacji o pomiarach.", "solution": "Mapa pomiarowa.",
        "recipients": "Mieszkańcy", "kind": "technologiczna", "stage": "wdrozona",
        "domains": ["energia_srodowisko"], "locator": {"publisher": "NCBR"},
    }


def observations(rows):
    return {
        "rows": rows,
        "selection": {"scanned": len(rows), "eligible": len(rows), "complete_scan": True, "unavailable": []},
        "observed_at": "2026-11-21T00:00:00+00:00",
    }


def test_import_limit_dedup_and_source_counts(app, client, monkeypatch, tmp_path):
    app.config["PUBLIC_PROJECTS_CACHE_DIR"] = tmp_path
    db.session.add(Innovation(
        title="Projekt-Pomiarowy", source_name=radon.SOURCE, source_ref="original",
        origin="radar", organization=Organization(name="Publiczny Instytut A", kind="instytucja_publiczna"),
    ))
    db.session.commit()
    source_rows = [project("duplikat"), project("oryginal", "Projekt inny")]
    monkeypatch.setattr(projekty_publiczne, "collect", lambda *_: observations(source_rows))

    first = client.post("/api/radar/run", json={"source": "ncbr", "limit": 1}).get_json()
    assert (first["fetched"], first["created"], first["selection"]["cross_source_duplicates"]) == (1, 0, 1)
    assert db.session.scalar(select(Innovation).where(Innovation.source_ref == "original")).raw == {
        "related_public_projects": {"ncbr": {"ref": "duplikat", "url": "https://www.gov.pl/web/ncbr/duplikat"}},
    }
    result = client.post("/api/radar/run", json={"source": "ncbr", "limit": 2}).get_json()
    assert (result["fetched"], result["created"], result["skipped"]) == (1, 1, 0)
    item = client.get(f"/api/innovations/{result['created_items'][0]['id']}").get_json()
    assert item["organization"]["name"] == "Publiczny Instytut A" and item["results"]

    def no_network(*_):
        raise AssertionError("Tryb offline nie powinien uruchamiać pobierania")

    monkeypatch.setattr(projekty_publiczne, "collect", no_network)
    replay = projekty_publiczne.run("ncbr", tmp_path, 3, cached_only=True)
    assert (replay["created"], replay["skipped"]) == (0, 2)
    sources = {item["name"]: item for item in client.get("/api/radar/sources").get_json()["items"]}
    assert sources["ncbr"]["count"] == 1 and sources["ncbr"]["last_run"]["skipped"] == 2
    assert sources["interreg"]["count"] == 0
    assert set(sources) == {"radon_projekty", "strony_instytucji", "ncbr", "interreg", "crossref", "uprp_bup", "epo_eps"}


def test_crossref_links_visible_evidence_and_replays_offline(app, client, monkeypatch, tmp_path):
    app.config["PUBLIC_PROJECTS_CACHE_DIR"] = tmp_path
    publication = {
        "project_ref": "airly", "doi": "10.3390/atmos16101201", "title": "Badanie jakości powietrza",
        "publisher": "MDPI AG", "evidence": "Badanie wykorzystało pomiary i API Airly.",
        "metadata_source": "crossref", "relationship": "verified_use",
        "metadata_url": "https://api.crossref.org/works/10.3390/atmos16101201",
    }
    monkeypatch.setattr(projekty_publiczne, "collect", lambda *_: observations([publication]))
    absent = client.post("/api/radar/run", json={"source": "crossref"}).get_json()
    assert absent["updated"] == 0 and absent["selection"]["without_card"] == 1
    innovation = Innovation(origin="radar", title="Airly", source_name="ncbr", source_ref="airly")
    db.session.add(innovation)
    db.session.commit()

    result = client.post("/api/radar/run", json={"source": "crossref", "cached_only": True}).get_json()
    assert result["created"] == 0 and result["updated_items"] == [{"id": innovation.id, "title": "Airly"}]
    assert innovation.raw["publications"][0]["doi"] == publication["doi"]
    card = client.get(f"/api/innovations/{innovation.id}").get_json()
    assert publication["doi"] in card["description"] and publication["evidence"] in card["description"]
    assert client.post("/api/radar/run", json={"source": "crossref", "cached_only": True}).get_json()["updated"] == 0
    sources = {item["name"]: item for item in client.get("/api/radar/sources").get_json()["items"]}
    assert sources["crossref"]["count"] == 1


def test_unavailable_source_and_patent_dispatch(app, client, monkeypatch, tmp_path):
    app.config["PUBLIC_PROJECTS_CACHE_DIR"] = tmp_path
    failure = client.post("/api/radar/run", json={"source": "interreg", "cached_only": True})
    assert failure.status_code == 503 and "Interreg" in failure.get_json()["error"]
    assert client.post("/api/radar/run", json={"source": "ncbr", "refresh": True, "cached_only": True}).status_code == 400

    calls = []

    def patent_run(source, limit, **options):
        calls.append((source, limit, options))
        if source == "epo_eps":
            raise PublicSourceError("EPS chwilowo niedostępny.")
        return {"fetched": 0, "created": 0, "skipped": 0, "created_items": [],
                "missing_embeddings": 0, "selection": {"complete_scan": True}}

    monkeypatch.setattr(importer, "patenty", SimpleNamespace(run=patent_run, PatentError=PublicSourceError, CACHE_DIR=tmp_path))
    result = client.post("/api/radar/run", json={"source": "uprp_bup", "limit": 1, "cached_only": True})
    assert result.status_code == 200
    assert calls == [("uprp_bup", 1, {"new_only": True, "refresh": False, "cached_only": True})]
    cli = app.test_cli_runner().invoke(args=["radar", "run", "--source", "uprp_bup", "--cached-only"])
    assert cli.exit_code == 0 and calls[-1][1] == 20
    error = client.post("/api/radar/run", json={"source": "epo_eps"})
    assert error.status_code == 503 and "EPS" in error.get_json()["error"]


def test_radon_keeps_the_existing_public_project(app, monkeypatch, tmp_path):
    public = project("unique")
    monkeypatch.setattr(projekty_publiczne, "collect", lambda *_: observations([public]))
    projekty_publiczne.run("ncbr", tmp_path / "public", 1)

    candidates = [
        Candidate(
            ref=ref, title=title, description="Opis projektu z RAD-on.", leader_id="test-leader",
            leader_name=public["organization"], institution={}, start=date(2024, 1, 1), keywords=[], raw={},
        )
        for ref, title in (("duplikat", public["source_title"]), ("nowy", "Odrębny projekt"))
    ]
    monkeypatch.setattr(importer, "collect", lambda *args, **kwargs: (candidates, {"complete_scan": True}))
    result = importer.run(tmp_path / "radon", 1, new_only=True, cached_only=True)
    assert result["selection"]["cross_source_duplicates"] == 1
    assert result["created"] == 1 and result["created_items"][0]["title"] == "Odrębny projekt"
    assert db.session.scalar(select(Innovation).where(Innovation.source_name == radon.SOURCE)).source_ref == "nowy"
