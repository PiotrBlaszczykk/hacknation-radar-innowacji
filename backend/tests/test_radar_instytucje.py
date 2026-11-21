import httpx
from sqlalchemy import select

from app.extensions import db
from app.models import Innovation
from app.radar import instytucje
from app.radar.instytucje.fetch import allowed, article_ref
from app.radar.radon import SOURCE as RADON_SOURCE, write_json


ORIGIN = "https://test.szkolnastrona.pl"
APPLIED = "/a,42,ogrod"
ANNOUNCEMENT = "/a,43,nabor"
UNAVAILABLE = "/a,44,przerwa"
BLOCKED = "/a,45,zakaz"
TDM = "/a,46,chroniony"
FACT = "Uczniowie badali wpływ światła na wzrost roślin."


def test_article_references_and_robot_rules():
    variants = [
        ORIGIN + APPLIED,
        ORIGIN + "/art%2C42%2Cinny-tytul?utm_campaign=portal#tresc",
        ORIGIN + "/index.php?c=article&id=42",
    ]
    assert len({article_ref(url) for url in variants}) == 1
    assert article_ref("https://www.krosno.pl/aktualnosci/stary-tytul%2C300?utm_source=feed") == (
        article_ref("https://krosno.pl/aktualnosci/nowy-tytul,300")
    )
    assert article_ref("https://spboguchwala.pl/?p=42#galeria") != article_ref("https://spboguchwala.pl/?p=43")
    assert article_ref("https://erzeszow.pl/print/41/1713/147964") == (
        article_ref("https://erzeszow.pl/41-miasto-rzeszow/1713-aktualnosci/147964-tytul.html")
    )
    rules = "User-agent: *\nDisallow: /*print*\nDisallow: /*.pdf$\nAllow: /public/print/\n"
    assert not allowed(rules, ORIGIN + "/print/42")
    assert not allowed(rules, ORIGIN + "/zasoby/plik.pdf")
    assert allowed(rules, ORIGIN + "/public/print/artykul")
    assert allowed(rules, ORIGIN + APPLIED)


def test_institution_scan_api_import_and_cache(app, client, monkeypatch, tmp_path):
    app.config["INSTITUTIONS_CACHE_DIR"] = tmp_path
    site = {
        "id": "test-szkola", "name": "Szkoła w przykładzie", "kind": "szkola", "city": "Przykład",
        "origin": ORIGIN, "indexes": ["/aktualnosci"],
        "articles": [
            {"path": APPLIED, "title": "Ogrodowe doświadczenia", "match": "wzrost roślin",
             "problem": "Potrzeba praktycznych zajęć.", "solution": "Prowadzenie szkolnego ogrodu.", "evidence": FACT},
            {"path": ANNOUNCEMENT, "match": "rozpoczynamy nabór", "reject": "Ogłoszenie."},
            {"path": UNAVAILABLE, "match": "wynik"},
            {"path": BLOCKED, "match": "wynik"},
            {"path": TDM, "match": "wynik"},
        ],
    }
    monkeypatch.setattr("app.radar.instytucje.fetch.read_sources", lambda: [site])
    requests = []
    pages = {
        "/robots.txt": "User-agent: *\nDisallow: /a,45*",
        "/aktualnosci": '''<a href="/art%2C42%2Cogrod?utm_source=demo">Artykuł</a>
                          <a href="/a,42,ogrod#galeria">Galeria</a>''',
        APPLIED: f"""<meta name=robots content=noarchive><time datetime="2026-11-20T16:30:00+01:00"></time>
                    <p>{FACT}</p> Testowe Nazwisko, uczen@example.org""",
        ANNOUNCEMENT: "Rozpoczynamy nabór pomysłów.",
        TDM: '<meta name="tdm-reservation" content="1"><p>wynik</p>',
    }

    def handler(request):
        path = request.url.path
        requests.append(path)
        if path == UNAVAILABLE:
            return httpx.Response(503)
        return httpx.Response(200, text=pages[path], headers={"Content-Type": "text/html; charset=utf-8"})

    http_client = httpx.Client
    monkeypatch.setattr(
        "app.radar.instytucje.fetch.httpx.Client", lambda **_: http_client(transport=httpx.MockTransport(handler))
    )
    monkeypatch.setattr("app.radar.instytucje.fetch.time.sleep", lambda _: None)
    inputs = []

    def structure(text):
        inputs.append(text)
        return {
            "card": {"summary": "Ogród jako pracownia uczniów.", "kind": "edukacyjna", "solution": FACT,
                     "domains": ["edukacja", "nieznany"], "results": "Niezweryfikowany efekt."},
            "engine": {"tags": "tagger", "text": "writer"},
            "is_innovation": 0.82, "version": "2",
        }

    monkeypatch.setattr(instytucje.structuring, "structure_text", structure)
    preflight = app.test_cli_runner().invoke(args=["radar", "scan-institutions"])
    assert preflight.exit_code == 0, preflight.output
    assert "potwierdzono 1, odrzucono 1" in preflight.output
    assert "HTTP 503" in preflight.output and "zastrzega analizę" in preflight.output
    assert APPLIED in requests and requests.count(APPLIED) == 1 and BLOCKED not in requests
    assert not inputs
    assert db.session.scalar(select(Innovation).where(Innovation.source_name == instytucje.SOURCE)) is None

    # Import i ponowienie korzystają tylko z tych samych zapisanych obserwacji.
    requests.clear()
    result = app.test_cli_runner().invoke(args=["radar", "run", "--source", instytucje.SOURCE, "--cached-only"])
    assert result.exit_code == 0, result.output
    assert "dodano 1" in result.output
    assert len(inputs) == 1 and FACT in inputs[0] and "Testowe Nazwisko" not in inputs[0]
    assert all("uczen@example.org" not in item.read_text() for item in tmp_path.glob("*.json"))

    record = db.session.scalar(select(Innovation).where(Innovation.source_name == instytucje.SOURCE))
    assert record.source_url == ORIGIN + APPLIED and record.source_ref == article_ref(record.source_url)
    assert record.organization.name == site["name"] and record.organization.region == "podkarpackie"
    assert record.origin == "radar" and record.claimed is False
    assert record.results == FACT and record.raw["structuring_version"] == "2"
    assert record.raw["published"] == "2026-11-20"
    assert record.solution == "Prowadzenie szkolnego ogrodu."
    assert record.summary == "Ogród jako pracownia uczniów." and record.domains == ["edukacja"]
    assert record.structured_by == "tagger + writer"
    assert record.embedding is not None
    detail = client.get(f"/api/innovations/{record.id}").get_json()
    assert detail["source_url"] == ORIGIN + APPLIED and detail["results"] == FACT
    replay = app.test_cli_runner().invoke(args=["radar", "run", "--source", instytucje.SOURCE, "--cached-only"])
    assert replay.exit_code == 0 and "dodano 0, pominięto 1" in replay.output
    assert len(inputs) == 1 and not requests
    response = client.post("/api/radar/run", json={"source": instytucje.SOURCE})
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["created"] == 0


def test_radar_sources_live_review_counts(app, client, tmp_path):
    app.config.update(RADON_CACHE_DIR=tmp_path, INSTITUTIONS_CACHE_DIR=tmp_path / "institutions")
    write_json(tmp_path / "last-scan.json", {"scanned": 37649, "complete_scan": True})
    write_json(tmp_path / "last-run.json", {"selection": {"scanned": 100, "complete_scan": False}})
    db.session.add_all([
        Innovation(title="Wybrana karta", origin="radar", source_name=RADON_SOURCE),
        Innovation(title="Druga karta", origin="radar", source_name=RADON_SOURCE),
        Innovation(title="Inny radar", origin="radar", source_name="inne",
                   raw={"radar_review": {"decision": "odrzucona"}}),
    ])
    db.session.commit()

    def radon():
        return next(item for item in client.get("/api/radar/sources").get_json()["items"] if item["name"] == RADON_SOURCE)

    status = radon()
    assert status["count"] == 2
    assert status["statistics"] == {"scanned": 37649, "complete_scan": True, "reviewed": 0, "rejected": 0}
    record = db.session.scalar(select(Innovation).where(Innovation.title == "Wybrana karta"))
    record.raw = {"radar_review": {"decision": "odrzucona"}}
    db.session.commit()
    assert radon()["statistics"] == {"scanned": 37649, "complete_scan": True, "reviewed": 1, "rejected": 1}


def test_offline_missing_and_unavailable_source(app, client, tmp_path, monkeypatch):
    app.config["INSTITUTIONS_CACHE_DIR"] = tmp_path
    monkeypatch.setattr("app.radar.instytucje.fetch.time.sleep", lambda _: None)

    def response(request):
        assert request.url.path == "/robots.txt"
        return httpx.Response(503)

    http_client = httpx.Client
    monkeypatch.setattr(
        "app.radar.instytucje.fetch.httpx.Client", lambda **_: http_client(transport=httpx.MockTransport(response))
    )
    cli = app.test_cli_runner().invoke(args=["radar", "run", "--source", instytucje.SOURCE, "--cached-only"])
    assert cli.exit_code != 0 and "Brak zapisanej obserwacji" in cli.output
    result = client.post("/api/radar/run", json={"source": instytucje.SOURCE})
    assert result.status_code == 503 and "robots.txt" in result.get_json()["error"]
