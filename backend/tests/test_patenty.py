import json
import shutil

import pytest
from sqlalchemy import select

from app.extensions import db
from app.models import Innovation
from app.radar import patenty
from app.radar.patenty import transport
from app.radar.patenty.catalog import EPO, UPRP, Selection
from app.radar.patenty.parsers import parse_bup, parse_eps

BUP_URL = "https://uprp.gov.pl/test.pdf"
EPO_REF = "EP1234567B1"


def two_column_pdf():
    lines = [
        (55, 782, "Warszawa, dnia 1 grudnia 2025 r."),
        (55, 605, "A1 (21) 123456 (22) 2024 05 01"),
        (310, 605, "U1 (21) 123457 (22) 2024 06 02"),
        (55, 580, "(71) POLITECHNIKA A, Miasto"),
        (310, 580, "(71) POLITECHNIKA B, Miasto"),
        (55, 555, "(72) DANE OSOBOWE A"),
        (310, 555, "(72) DANE OSOBOWE B"),
        (55, 530, "(54) Czujnik ruchu"),
        (310, 530, "(54) Pomiar w terenie"),
        (55, 507, "(57) Pierwszy pasek opisu"),
        (55, 485, "i dalszy tekst z lewej kolumny."),
    ]
    stream = "\n".join(
        f"BT /F1 10 Tf {x} {y} Td ({value.replace('(', chr(92) + '(').replace(')', chr(92) + ')')}) Tj ET"
        for x, y, value in lines
    ).encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, obj in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        pdf.extend(f"{offset:010} 00000 n \n".encode())
    pdf.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(pdf)


EPS_XML = b"""<ep-patent-document xmlns="urn:eps-test" country="EP" doc-number="1234567"
    kind="B1" date-publ="20260121" lang="en">
  <SDOBI>
    <B200><B210>24123456.7</B210><B220><date>20240410</date></B220></B200>
    <B300><B310>12345624</B310><B320><date>20240501</date></B320><B330>PL</B330></B300>
    <B400><B450><date>20260121</date></B450><B430><date>20251112</date></B430></B400>
    <B500><B540><B541>de</B541><B542>Bewegung</B542><B541>en</B541><B542>Motion sensor</B542></B540></B500>
    <B700><B720><B721><snm>DANE OSOBOWE C</snm></B721></B720>
          <B730><B731><snm>Politechnika A</snm></B731></B730></B700>
  </SDOBI>
</ep-patent-document>"""


requires_poppler = pytest.mark.skipif(shutil.which("pdftotext") is None, reason="Poppler required")


@requires_poppler
def test_bup_pdf_keeps_fields_in_their_own_column():
    issue = parse_bup(two_column_pdf())
    left = issue["records"]["PL123456A1"]
    right = issue["records"]["PL123457U1"]
    assert issue["publication_date"] == "2025-12-01"
    assert (left["title"], left["parties"], left["abstract"]) == (
        "Czujnik ruchu", ["POLITECHNIKA A, Miasto"],
        "Pierwszy pasek opisu i dalszy tekst z lewej kolumny.",
    )
    assert (right["title"], right["parties"], right["abstract"]) == (
        "Pomiar w terenie", ["POLITECHNIKA B, Miasto"], None,
    )
    assert "DANE OSOBOWE" not in str(issue)


def test_eps_grant_with_no_abstract_keeps_dates_and_proprietor():
    record = parse_eps(EPS_XML)
    assert record["abstract"] is None
    assert record["title"] == "Motion sensor"
    assert record["party_role"] == "proprietor"
    assert record["parties"] == ["Politechnika A"]
    assert record["filing_date"] == "2024-04-10"
    assert record["application_publication_date"] == "2025-11-12"
    assert record["publication_date"] == record["grant_announced_on"] == "2026-01-21"
    assert record["priority_claims"] == [{"application_id": "PL123456", "filing_date": "2024-05-01"}]
    assert "DANE OSOBOWE" not in str(record)


@requires_poppler
def test_patents_cli_and_offline_repeat(app, tmp_path, monkeypatch):
    app.config["PATENT_CACHE_DIR"] = tmp_path
    first = Selection(("Politechnika A",), "czujnik ruchu", "Czujnik", "Czujnik mierzy ruch.", ("zdrowie",))
    second = Selection(("Politechnika B",), "pomiar w terenie", "Pomiary", "Pomiar w terenie.", ("zdrowie",))
    european = Selection(("Politechnika A",), "motion sensor", "Czujnik", "Czujnik mierzy ruch.", ("zdrowie",))
    monkeypatch.setattr(transport, "BUP", {BUP_URL: {"PL123456A1": first, "PL123457U1": second}})
    monkeypatch.setattr(transport, "EPS", {EPO_REF: european})
    monkeypatch.setattr(transport.Downloads, "read", lambda _, url: two_column_pdf() if url == BUP_URL else EPS_XML)
    runner = app.test_cli_runner()

    def run(source, *options):
        invocation = runner.invoke(args=["patenty", "run", "--source", source, *options])
        assert invocation.exit_code == 0, (invocation.output, invocation.exception)
        return json.loads(invocation.output)

    assert run(UPRP, "--limit", "1")["created"] == 1
    assert run(EPO)["created"] == 1

    def offline(*args):
        pytest.fail("Tryb offline wykonał pobranie")

    monkeypatch.setattr(transport, "_live", offline)
    assert run(UPRP, "--limit", "1", "--cached-only")["created"] == 1
    assert (repeated := run(UPRP, "--cached-only"))["created"] == 0
    assert repeated["skipped"] == 2
    assert run(EPO, "--cached-only")["skipped"] == 1
    assert patenty.run(EPO, 1, new_only=True, cached_only=True)["fetched"] == 0
    records = list(db.session.scalars(select(Innovation).where(Innovation.source_name.in_((UPRP, EPO)))))
    assert len(records) == 3
    assert all(card.results is None and card.stage is None and card.embedding is None for card in records)
    assert all("DANE OSOBOWE" not in str(card.raw) for card in records)
    pl, ep = next(card for card in records if card.source_ref == "PL123456A1"), next(
        card for card in records if card.source_ref == EPO_REF
    )
    assert pl.source_url == f"{BUP_URL}#page=1"
    assert ep.source_url == transport.eps_url(EPO_REF, "pdf")
    assert pl.raw["patent"]["related_documents"][0]["url"] == ep.source_url
    assert ep.raw["patent"]["related_documents"][0]["relation"] == "priority_claim"
    assert len(pl.events) == len(ep.events) == 2


def test_priority_requires_matching_date_and_single_claim():
    pl = {"source_name": UPRP, "application_id": "PL123456", "filing_date": "2024-04-30", "ref": "PL123456A1"}
    ep = {**parse_eps(EPS_XML), "source_name": EPO}
    assert patenty._relation(pl, ep) is None
    pl["filing_date"] = "2024-05-01"
    assert patenty._relation(pl, {**ep, "has_other_priorities": True}) is None
