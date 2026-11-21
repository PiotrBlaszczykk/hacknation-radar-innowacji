"""Read bibliographic facts from Poppler coordinates and EPS XML."""

import re
import subprocess
from datetime import date
from xml.etree import ElementTree as ET

MONTHS = "stycznia lutego marca kwietnia maja czerwca lipca sierpnia września października listopada grudnia".split()
BUP_DATE = re.compile(r"Warszawa, dnia\s+(\d{1,2})\s+(\w+)\s+(\d{4})\s+r\.", re.I)
BUP_START = re.compile(r"^(A1|U1)\s+\(21\)\s+(\d{6})\s+\(22\)\s+(\d{4}\s+\d{2}\s+\d{2})\b")
FIELD = re.compile(r"^\((\d{2})\)\s+(.*)")
EPS_KINDS = {
    "A1": "application_publication", "A2": "application_publication",
    "B1": "grant_publication", "B2": "amended_patent_publication",
    "B3": "limited_patent_publication",
}


class PatentError(Exception):
    pass


def _text(element: ET.Element | None) -> str:
    return " ".join("".join(element.itertext()).split()) if element is not None else ""


def _date(value: str) -> str | None:
    digits = re.sub(r"\s", "", value)
    if not re.fullmatch(r"\d{8}", digits):
        return None
    try:
        return date.fromisoformat(digits).isoformat()
    except ValueError:
        return None


def _bup_columns(page):
    midpoint = float(page.get("width")) / 2
    columns = ([], [])
    for line in page.findall(".//{*}line"):
        y = float(line.get("yMin"))
        if y < 45:
            continue
        words = [word.text for word in line.findall("{*}word") if word.text]
        text = " ".join(words)
        if text:
            columns[float(line.get("xMin")) >= midpoint].append((y, text))
    for column in columns:
        yield from (line for _, line in sorted(column, key=lambda item: item[0]))


def parse_bup(pdf: bytes) -> dict:
    try:
        result = subprocess.run(
            ["pdftotext", "-bbox-layout", "-", "-"],
            input=pdf, capture_output=True, check=True, timeout=35,
        )
        root = ET.fromstring(re.sub(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]", b"", result.stdout))
    except FileNotFoundError as exc:
        raise PatentError("Do odczytu BUP potrzebny jest pdftotext (poppler-utils).") from exc
    except (subprocess.SubprocessError, ET.ParseError) as exc:
        raise PatentError("Nie udało się odczytać układu PDF biuletynu UPRP.") from exc

    publication_date = None
    records = {}
    current = None
    fields = {}
    active_field = None

    def finish():
        if current is not None:
            current.update(
                title=_join_lines(fields.get("54", [])),
                parties=_join_lines(fields.get("71", [])).split(";"),
                abstract=_join_lines(fields.get("57", [])) or None,
            )
            records[current["ref"]] = current

    for page_number, page in enumerate(root.findall(".//{*}page"), 1):
        if publication_date is None:
            page_text = " ".join(" ".join(line.itertext()).strip() for line in page.findall(".//{*}line"))
            match = BUP_DATE.search(" ".join(page_text.split()))
            if match:
                day, month, year = match.groups()
                if month.lower() in MONTHS:
                    publication_date = _date(f"{year}{MONTHS.index(month.lower()) + 1:02}{int(day):02}")
        for line in _bup_columns(page):
            if match := BUP_START.match(line):
                finish()
                kind, number, filing = match.groups()
                current = {
                    "ref": f"PL{number}{kind}", "kind": kind, "application_id": f"PL{number}",
                    "filing_date": _date(filing), "page": page_number,
                }
                fields = {}
                active_field = None
            elif match := FIELD.match(line):
                code, value = match.groups()
                active_field = code if code in {"54", "57", "71"} else None
                if active_field:
                    fields.setdefault(active_field, []).append(value)
            elif re.match(r"^\(\d+\s+zastrzeż", line, re.I) or line.startswith(("DZIAŁ ", "WYKAZ ")):
                active_field = None
            elif active_field:
                fields[active_field].append(line)
    finish()
    if not publication_date or not records:
        raise PatentError("PDF nie zawiera rozpoznawalnej daty i ogłoszeń BUP.")
    return {"publication_date": publication_date, "records": records}


def _join_lines(lines: list[str]) -> str:
    return re.sub(r"(?<=\w)[\u00ad-]\n(?=\w)", "", "\n".join(lines)).replace("\n", " ").strip()


def parse_eps(xml: bytes) -> dict:
    if b"<!ENTITY" in xml:
        raise PatentError("XML EPO zawiera nieobsługiwane deklaracje encji.")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise PatentError("EPO nie zwrócił poprawnego dokumentu XML.") from exc
    for element in root.iter():
        element.tag = element.tag.rsplit("}", 1)[-1]
    kind = root.get("kind")
    number = root.get("doc-number", "")
    publication_date = _date(root.get("date-publ", ""))
    if (
        root.tag != "ep-patent-document" or root.get("country") != "EP"
        or kind not in EPS_KINDS or not re.fullmatch(r"\d{7}", number) or not publication_date
    ):
        raise PatentError("XML EPO nie zawiera obsługiwanej publikacji patentowej.")

    biblio = root.find("SDOBI")
    if biblio is None:
        raise PatentError("Brak metadanych SDOBI w XML EPO.")
    language = root.get("lang", "en")
    titles = {
        _text(language_node): _text(title_node)
        for title_group in biblio.findall(".//B540")
        for language_node, title_node in zip(title_group.findall("B541"), title_group.findall("B542"))
    }
    title = titles.get(language) or titles.get("en") or next(iter(titles.values()), "")
    parties = [_text(item.find("snm")) for item in biblio.findall(".//B710/B711")]
    party_role = "applicant"
    if not parties and kind.startswith("B"):
        parties = [_text(item.find("snm")) for item in biblio.findall(".//B730/B731")]
        party_role = "proprietor"

    priorities = []
    for entry in biblio.findall(".//B300"):
        country = _text(entry.find("B330"))
        priority = _text(entry.find("B310"))
        filing = _date(_text(entry.find("B320/date")))
        if country == "PL" and re.fullmatch(r"\d{8}", priority) and filing and priority[-2:] == filing[2:4]:
            priorities.append({"application_id": f"PL{priority[:6]}", "filing_date": filing})
    app_number = _text(biblio.find(".//B210"))
    return {
        "ref": f"EP{number}{kind}", "title": title, "kind": kind,
        "application_id": f"EP{app_number}" if re.fullmatch(r"\d{8}\.\d", app_number) else None,
        "filing_date": _date(_text(biblio.find(".//B220/date"))),
        "publication_date": publication_date,
        "application_publication_date": _date(_text(biblio.find(".//B430/date"))),
        "grant_announced_on": publication_date if kind == "B1" else None,
        "party_role": party_role, "parties": parties, "priority_claims": priorities,
        "has_other_priorities": len(biblio.findall(".//B300")) != 1,
        "abstract": _text(root.find("abstract")) or None,
    }
