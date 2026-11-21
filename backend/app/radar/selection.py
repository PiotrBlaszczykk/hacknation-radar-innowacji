"""Kryteria kwalifikacji projektów oraz mapowanie pól RAD-on."""

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlsplit

from .radon import START_DATE, MissingCachedPage, RadonClient

REGION = "podkarpackie"
MIN_ABSTRACT = 300
PROGRAMS = {
    "LIDER": r"\blider\b",
    "TANGO": r"\btango\b",
    "Szybka ścieżka": r"\bszybka ścieżka\b",
    "Ścieżka SMART": r"\b(?:ścieżka smart|smart path)\b",
    "Inkubator Innowacyjności": r"\binkubator innowacyjności\b",
    "Doktorat wdrożeniowy": r"\bdoktorat\w* wdrożeniow\w*\b",
    "Program Badań Stosowanych": r"\b(?:program badań stosowanych|pbs)\b",
    "Horyzont Europa / 2020": r"\b(?:horyzont|horizon) (?:europa|europe|2020)\b",
}
NCBR = re.compile(r"\b(?:ncbr|narodow\w+ centr\w+ badań i rozwoju)\b", re.I)
FINANCERS = {
    "Narodowe Centrum Badań i Rozwoju": NCBR,
    "Narodowe Centrum Nauki": re.compile(r"\b(?:ncn|narodow\w+ centr\w+ nauki)\b", re.I),
    "Komisja Europejska": re.compile(r"\b(?:komisj\w+ europejsk\w+|european commission)\b", re.I),
    "Ministerstwo Nauki i Szkolnictwa Wyższego": re.compile(
        r"\b(?:mnisw|mnsw|minister\w+ nauki i szkolnictwa wyższego)\b", re.I
    ),
}
RULES = [
    f"Projekt rozpoczął się {date.fromisoformat(START_DATE):%d.%m.%Y} lub później.",
    f"Projekt ma polski tytuł i polski opis zawierający co najmniej {MIN_ABSTRACT} znaków.",
    f"Projekt finansuje NCBR lub jest realizowany w jednym z programów: {', '.join(PROGRAMS)}.",
    "Można ustalić instytucję lidera. Gdy źródło nie oznacza lidera, używamy jedynego wykonawcy lub instytucji wykazującej.",
    "Pełny import uwzględnia wszystkie pasujące projekty z liderem z Podkarpacia i uzupełnia limit projektami z pozostałych regionów.",
]

SENTENCE_BOUNDARY = re.compile(r"(?<!\bnp\.)(?<!\bm\.in\.)(?<!\btj\.)(?<!\bitp\.)(?<=[.!?])\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ])")


@dataclass
class Candidate:
    ref: str
    title: str
    description: str
    leader_id: str
    leader_name: str
    institution: dict
    start: date
    keywords: list[str]
    raw: dict

    @property
    def regional(self) -> bool:
        return text(self.institution.get("voivodeship")).lower() == REGION


def text(value) -> str:
    return value.replace("\0", "").strip() if isinstance(value, str) else ""


def summary(description: str) -> str:
    compact = " ".join(description.split())
    sentences = SENTENCE_BOUNDARY.split(compact, maxsplit=2)
    result = " ".join(sentences[:2])
    if len(result) <= 300:
        return result
    if len(sentences[0]) <= 300:
        return sentences[0]
    return result[:299].rsplit(" ", 1)[0].rstrip(".,:;") + "…"


def organization_fields(candidate: Candidate) -> dict:
    institution = candidate.institution
    label = text(institution.get("iKindName")).lower()
    kind = "instytucja_publiczna"
    if "uczeln" in label:
        kind = "uczelnia"
    elif "przedsiębior" in label or "spółk" in label:
        kind = "firma"
    elif "fundacj" in label or "stowarzysze" in label:
        kind = "ngo"

    website = text(institution.get("www"))
    if website and "://" not in website:
        website = f"https://{website}"
    try:
        url = urlsplit(website)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or re.search(r"\s", website):
            website = ""
    except ValueError:
        website = ""

    return {
        "name": candidate.leader_name[:300],
        "kind": kind,
        "region": text(institution.get("voivodeship")).lower()[:80] or None,
        "city": text(institution.get("city"))[:120] or None,
        "website": website if 0 < len(website) <= 300 else None,
        "external_ids": {"radon": candidate.leader_id},
    }


def _leader(project: dict, partners: list[dict]) -> dict:
    for partner in partners:
        if text(partner.get("leader")).casefold() == "tak":
            return partner
    if len(partners) == 1 and partners[0].get("institutionUuid"):
        return partners[0]
    return {
        "institutionUuid": project.get("entityShowingAchievementsUuid"),
        "institutionName": project.get("entityShowingAchievementsName"),
    }


def _keywords(value) -> list[str]:
    words = value if isinstance(value, list) else re.split(r"[,;\n]", text(value))
    return list(dict.fromkeys(word for item in words if (word := text(item))))


def _date_field(value) -> str | None:
    value = text(value)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value
    return None


def _amount(value) -> str | None:
    value = str(value) if isinstance(value, (str, int, float)) else ""
    return value if re.fullmatch(r"\d+(?:[.,]\d+)?", value) else None


def select_project(project: dict, institutions: dict[str, dict], counts: Counter) -> Candidate | None:
    counts["scanned"] += 1
    ref = text(project.get("projectUuid"))
    title = text(project.get("projectTitlePl"))
    if not ref or len(ref) > 200 or not title:
        return None
    counts["identified"] += 1

    try:
        start = date.fromisoformat(_date_field(project.get("projectStartDate")) or "")
    except ValueError:
        return None
    if start < date.fromisoformat(START_DATE):
        return None
    counts["recent"] += 1

    description = text(project.get("projectAbstractPl"))
    if len(" ".join(description.split())) < MIN_ABSTRACT:
        return None
    counts["described"] += 1

    program_text = " ".join(
        text(project.get(key)) for key in ("projectClassification", "anotherProjectClassification", "financedCompetition")
    )
    programs = [name for name, pattern in PROGRAMS.items() if re.search(pattern, program_text, re.I)]
    finance_info = project.get("financingInstitutions") or []
    financer_names = []
    is_ncbr = False
    for financer in finance_info:
        evidence = " ".join(text(financer.get(key)) for key in ("financingInstitutionName", "sourceOfFinancing"))
        is_ncbr |= bool(NCBR.search(evidence))
        official = text(institutions.get(text(financer.get("financingInstitutionUuid")), {}).get("name"))
        recognized = next((name for name, pattern in FINANCERS.items() if pattern.search(evidence)), "")
        if official or recognized:
            financer_names.append(official or recognized)
    if not programs and not is_ncbr:
        return None
    counts["applied"] += 1

    partners = project.get("implementingInstitutions") or []
    leader = _leader(project, partners)
    leader_id = text(leader.get("institutionUuid"))
    institution = institutions.get(leader_id, {})
    leader_name = text(institution.get("name")) or text(leader.get("institutionName"))
    if not leader_id or not leader_name:
        return None
    counts["with_leader"] += 1

    raw_partners = []
    for partner in partners:
        partner_id = text(partner.get("institutionUuid"))
        if partner_id:
            raw_partners.append({
                "id": partner_id,
                "name": text(institutions.get(partner_id, {}).get("name")) or None,
                "leader": partner_id == leader_id,
            })
    return Candidate(
        ref=ref,
        title=title[:400],
        description=description,
        leader_id=leader_id,
        leader_name=leader_name,
        institution=institution,
        start=start,
        keywords=_keywords(project.get("keywords")),
        raw={
            "program": programs or ([program] if (program := text(project.get("projectClassification"))) else []),
            "financing_institutions": list(dict.fromkeys(financer_names)),
            "total_funds": _amount(project.get("totalFunds")),
            "national_funds": _amount(project.get("nationalFunds")),
            "foreign_funds": _amount(project.get("foreignFunds")),
            "start_date": start.isoformat(),
            "end_date": _date_field(project.get("projectEndDate")),
            "partners": raw_partners,
        },
    )


def collect(
    client: RadonClient, *, known: set[str | None], demo_limit: int | None = None,
) -> tuple[list[Candidate], dict]:
    institutions = {
        uuid: row
        for page in client.pages("institutions")
        for row in page
        if (uuid := text(row.get("institutionUuid")))
    }
    counts = Counter(dict.fromkeys(("scanned", "identified", "recent", "described", "applied", "with_leader"), 0))
    candidates = {}
    new_refs = set()
    before_projects = client.downloaded_pages
    complete = True
    pages = client.pages("projects", projectStartDate=START_DATE)
    while True:
        try:
            page = next(pages)
        except StopIteration:
            break
        except MissingCachedPage:
            complete = False
            break
        for row in page:
            candidate = select_project(row, institutions, counts)
            if candidate:
                if candidate.ref not in known:
                    new_refs.add(candidate.ref)
                current = candidates.setdefault(candidate.ref, candidate)
                if candidate.regional and not current.regional:
                    candidates[candidate.ref] = candidate
        if demo_limit and len(new_refs) >= demo_limit and client.downloaded_pages > before_projects:
            complete = False
            break

    ordered = sorted(candidates.values(), key=lambda row: (not row.regional, -row.start.toordinal(), row.ref))
    return ordered, {
        **counts,
        "complete_scan": complete,
        "institutions": len(institutions),
        "eligible": len(ordered),
        "eligible_regional": sum(row.regional for row in ordered),
        "eligible_region_unknown": sum(not text(row.institution.get("voivodeship")) for row in ordered),
    }
