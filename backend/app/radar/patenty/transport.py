"""Bounded downloads from the publication endpoints. Cache only filtered facts."""

import json
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from ..radon import http_client, write_json
from .catalog import BUP, EPO, EPS, EPS_BASE, LUBLIN_ULS, UPRP, Selection
from .parsers import EPS_KINDS, PatentError, parse_bup, parse_eps

CACHE_VERSION = 1
MAX_BYTES = 8 * 1024 * 1024
RESTRICTED = re.compile(r"\b(?:noai|noimageai|notrain|notdm|noml)\b", re.I)
POLISH_GRANT = {
    "ref": "PL230537B1",
    "grant_announced_on": "2018-11-30",
    "url": "https://uprp.gov.pl/sites/default/files/wup/2018/11/wup11_2018.pdf#page=14",
}


def eps_url(ref: str, extension: str) -> str:
    return f"{EPS_BASE}/{ref[:-2]}NW{ref[-2:]}/document.{extension}"


def _download(http: httpx.Client, url: str, *, robots=False) -> bytes:
    try:
        with http.stream("GET", url) as response:
            if robots and response.status_code in {404, 410}:
                return b""
            response.raise_for_status()
            if response.status_code != 200:
                raise PatentError(f"Niepełna odpowiedź z {url}.")
            headers = response.headers
            if RESTRICTED.search(headers.get("x-robots-tag", "")) or headers.get("tdm-reservation") == "1":
                raise PatentError(f"Źródło zastrzega analizę maszynową. {url}")
            data = bytearray()
            max_bytes = 256 * 1024 if robots else MAX_BYTES
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > max_bytes:
                    raise PatentError(f"Odpowiedź przekroczyła limit rozmiaru. {url}")
            return bytes(data)
    except httpx.HTTPStatusError as exc:
        raise PatentError(f"Źródło niedostępne (HTTP {exc.response.status_code}). {url}") from exc
    except httpx.HTTPError as exc:
        raise PatentError(f"Błąd pobierania z urzędu. {url}") from exc


class Downloads:
    def __init__(self, http: httpx.Client):
        self.http = http
        self.rules = {}

    def read(self, url: str) -> bytes:
        origin = f"https://{urlsplit(url).netloc}"
        if origin not in self.rules:
            rules = RobotFileParser()
            robots = _download(self.http, origin + "/robots.txt", robots=True)
            rules.parse(robots.decode("utf-8", errors="replace").splitlines())
            self.rules[origin] = rules
        if not self.rules[origin].can_fetch("Radar-Innowacji", url):
            raise PatentError(f"Ścieżka niedostępna dla robota. {url}")
        time.sleep(0.5)
        return _download(self.http, url)


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold().replace("ł", "l"))
    return " ".join(re.findall(r"[a-z0-9]+", "".join(char for char in value if not unicodedata.combining(char))))


def _published_record(source: str, parsed: dict, selected: Selection, url: str, observed: str) -> dict:
    ref = parsed["ref"]
    if _normalize(selected.title_marker) not in _normalize(parsed["title"]) or not parsed["filing_date"]:
        raise PatentError(f"{ref}: tytuł lub metadane publikacji odbiegają od sprawdzonego dokumentu.")
    parties = [
        _normalize(name.split(",", 1)[0]) if source == UPRP else _normalize(name)
        for name in parsed["parties"]
    ]
    if ref == "EP3037500A1":
        parties = [_normalize(LUBLIN_ULS) if name == "uniwersytet przyrodniczy" else name for name in parties]
    expected = [_normalize(name) for name in selected.organizations]
    if sorted(parties) != sorted(expected):
        raise PatentError(f"{ref}: wykaz instytucji odbiega od sprawdzonego dokumentu.")
    notice = POLISH_GRANT if ref == "PL410744A1" else None
    metadata = {
        key: parsed.get(key)
        for key in ("ref", "kind", "application_id", "filing_date", "publication_date",
                    "application_publication_date", "grant_announced_on", "party_role", "page")
    }
    metadata.update(
        official_title=parsed["title"],
        source_name=source, url=url, organizations=list(selected.organizations),
        publication_type=(
            "utility_model_publication" if parsed["kind"] == "U1" else EPS_KINDS[parsed["kind"]]
        ),
        abstract_available=bool(parsed["abstract"]),
        priority_claims=parsed.get("priority_claims", []),
        has_other_priorities=parsed.get("has_other_priorities", False),
        observed_at=observed,
        grant_notice=notice,
        grant_announced_on=notice["grant_announced_on"] if notice else metadata["grant_announced_on"],
        summary_provenance="opracowanie redakcyjne na podstawie wskazanego dokumentu",
    )
    return {
        "title": selected.title, "summary": selected.summary, "domains": list(selected.domains),
        "broker_note": selected.broker_note, "patent": metadata,
    }


def _live(source: str) -> list[dict]:
    observed = datetime.now(timezone.utc).isoformat()
    rows = []
    with http_client() as http:
        client = Downloads(http)
        if source == UPRP:
            for url, entries in BUP.items():
                issue = parse_bup(client.read(url))
                for ref, selection in entries.items():
                    parsed = issue["records"].get(ref)
                    if parsed is None:
                        raise PatentError(f"{ref}: brak ogłoszenia w odczytanym PDF. {url}")
                    metadata = dict(
                        parsed, publication_date=issue["publication_date"],
                        application_publication_date=issue["publication_date"], party_role="applicant",
                    )
                    page_url = f'{url}#page={metadata["page"]}'
                    rows.append(_published_record(source, metadata, selection, page_url, observed))
        else:
            for ref, selection in EPS.items():
                metadata = parse_eps(client.read(eps_url(ref, "xml")))
                if metadata["ref"] != ref:
                    raise PatentError(f"{ref}: EPO zwróciło inny dokument XML.")
                rows.append(_published_record(source, metadata, selection, eps_url(ref, "pdf"), observed))
    return rows


def collect(source: str, cache_dir: Path, *, refresh: bool, cached_only: bool) -> list[dict]:
    if refresh and cached_only:
        raise PatentError("Wybierz odświeżenie albo tryb offline.")
    path = cache_dir / "publications.json"
    refs = list(EPS) if source == EPO else [ref for entries in BUP.values() for ref in entries]
    if not refresh:
        try:
            cached = json.loads(path.read_bytes())
            rows = cached["items"]
            if cached["version"] == CACHE_VERSION and [row["patent"]["ref"] for row in rows] == refs:
                return rows
        except (OSError, ValueError, TypeError, KeyError):
            pass
    if cached_only:
        raise PatentError(f"Brak zgodnej kopii danych dla {source}. Uruchom import z dostępem do sieci.")
    rows = _live(source)
    write_json(path, {"version": CACHE_VERSION, "items": rows})
    return rows
