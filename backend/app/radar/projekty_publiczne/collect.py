import json
import re
from datetime import datetime, timezone
from io import BytesIO
from time import monotonic, sleep
from urllib.parse import quote, urljoin, urlsplit
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile, ZipFile

import httpx
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from ..instytucje.fetch import RESTRICTED, USER_AGENT, Page, allowed, normalized

INTERREG_URL = "https://interreg.gov.pl/lista-projektow/"
NCBR_URL = "https://www.gov.pl/web/ncbr/wyszukiwarka-sukcesow-beneficjentow"
CROSSREF_URL = "https://api.crossref.org"
ORIGINS = {"https://interreg.gov.pl", "https://www.gov.pl", "https://plsk.eu", CROSSREF_URL}
MAX_BYTES = 2_000_000
MAX_PROJECTS = 10_000
MAX_REVIEWS = 20
WORKBOOK_NAME = re.compile(r"/wp-content/uploads/.*/Wykaz[_-]projektow[_-]Interreg[^/]*\.xlsx$", re.I)
ARTICLE = re.compile(r'<article\b[^>]*\bid="main-content"[^>]*>(.*?)</article>', re.I | re.S)
BLOCKS = re.compile(r"<(h[2-4]|p)\b[^>]*>(.*?)</\1>", re.I | re.S)


class PublicSourceError(Exception):
    pass


class Reader:
    def __init__(self, http: httpx.Client):
        self.http = http
        self.last_request = {}
        self.robots = {}

    def _request(self, url: str):
        host = urlsplit(url).netloc
        sleep(max(0, self.last_request.get(host, 0) + 0.5 - monotonic()))
        try:
            with self.http.stream("GET", url) as response:
                data = bytearray()
                if response.status_code == 200:
                    for chunk in response.iter_bytes():
                        if len(data) + len(chunk) > MAX_BYTES:
                            raise PublicSourceError("Odpowiedź przekracza 2 MB.")
                        data.extend(chunk)
                return response.status_code, response.headers, bytes(data)
        except httpx.HTTPError as exc:
            raise PublicSourceError("Witryna nie odpowiedziała.") from exc
        finally:
            self.last_request[host] = monotonic()

    def get(self, url: str) -> tuple[bytes, str]:
        for _ in range(4):
            parts = urlsplit(url)
            origin = f"{parts.scheme}://{parts.netloc}"
            if origin not in ORIGINS:
                raise PublicSourceError("Adres spoza rejestru obsługiwanych witryn.")
            if origin not in self.robots:
                robots = f"{origin}/robots.txt"
                status, headers, rules = self._request(robots)
                if status in {301, 302, 303, 307, 308} and headers.get("location"):
                    redirected = urljoin(robots, headers["location"])
                    target = urlsplit(redirected)
                    if f"{target.scheme}://{target.netloc}" == origin:
                        status, _, rules = self._request(redirected)
                if status not in {200, 404, 410}:
                    raise PublicSourceError(f"Nie można sprawdzić robots.txt (HTTP {status}).")
                self.robots[origin] = rules.decode("utf-8", errors="replace")
            if not allowed(self.robots[origin], url):
                raise PublicSourceError("Ścieżka jest wyłączona w robots.txt.")
            status, headers, data = self._request(url)
            if status in {301, 302, 303, 307, 308} and headers.get("location"):
                url = urljoin(url, headers["location"])
                continue
            if status != 200:
                raise PublicSourceError(f"Witryna odpowiedziała HTTP {status}.")
            if RESTRICTED.search(headers.get("x-robots-tag", "")) or headers.get("tdm-reservation") == "1":
                raise PublicSourceError("Witryna zastrzega analizę maszynową.")
            return data, headers.get("content-type", "").lower()
        raise PublicSourceError("Zbyt wiele przekierowań.")

    def html(self, url: str) -> tuple[str, Page]:
        data, content_type = self.get(url)
        if "text/html" not in content_type:
            raise PublicSourceError("Oczekiwano strony HTML.")
        body = data.decode("utf-8", errors="replace")
        page = Page(body)
        if page.restricted:
            raise PublicSourceError("Witryna zastrzega analizę maszynową.")
        return body, page


def workbook_url(page: Page) -> str:
    links = []
    for href in page.links:
        url = urljoin(INTERREG_URL, href)
        parts = urlsplit(url)
        if parts.scheme == "https" and parts.netloc == "interreg.gov.pl" and WORKBOOK_NAME.search(parts.path):
            links.append(url)
    if not links:
        raise PublicSourceError("Na stronie Interreg nie znaleziono aktualnego wykazu XLSX.")
    # Starszy wykaz może pozostać na stronie obok aktualnego. Nazwy zawierają datę YYYYMMDD.
    return max(links, key=lambda url: max(re.findall(r"20\d{6}", urlsplit(url).path), default=""))


HEADERS = {
    "project no.": "ref", "project title": "source_title", "project description": "description",
    "lead partner name": "lead", "lead partner and partners name": "partners",
    "voivodeship or region": "region", "city": "city", "programme": "programme",
}


def workbook_projects(payload: bytes):
    try:
        with ZipFile(BytesIO(payload)) as archive:
            if sum(member.file_size for member in archive.infolist()) > 24_000_000:
                raise PublicSourceError("Rozpakowany wykaz Interreg przekracza limit rozmiaru.")
        workbook = load_workbook(BytesIO(payload), read_only=True, data_only=True)
    except (BadZipFile, InvalidFileException, KeyError, ParseError, ValueError) as exc:
        raise PublicSourceError("Interreg nie zwrócił prawidłowego pliku XLSX.") from exc
    recognized = False
    scanned = 0
    try:
        for sheet in workbook:
            columns = {}
            for number, values in enumerate(sheet.values, 1):
                if not columns:
                    if number > 15:
                        break
                    labels = [normalized(str(value or "").rsplit("/", 1)[-1]) for value in values]
                    found = {HEADERS[label]: index for index, label in enumerate(labels) if label in HEADERS}
                    if set(HEADERS.values()) <= found.keys():
                        columns = found
                        recognized = True
                    continue
                row = {key: " ".join(str(values[index] or "").split()) for key, index in columns.items()}
                if not row["ref"]:
                    continue
                scanned += 1
                if scanned > MAX_PROJECTS:
                    raise PublicSourceError("Wykaz Interreg przekracza limit liczby projektów.")
                yield {**row, "sheet": sheet.title, "row": number}
        if not recognized or not scanned:
            raise PublicSourceError("Brak rozpoznawalnego arkusza projektów Interreg.")
    except (IndexError, KeyError, ParseError, ValueError) as exc:
        raise PublicSourceError("Nie udało się odczytać wierszy wykazu Interreg.") from exc
    finally:
        workbook.close()


def interreg(reader: Reader, reviews: dict) -> tuple[list[dict], dict]:
    _, page = reader.html(INTERREG_URL)
    url = workbook_url(page)
    payload, _ = reader.get(url)
    rows = []
    unavailable = []
    scanned = 0
    seen = set()
    for row in workbook_projects(payload):
        scanned += 1
        ref = row["ref"]
        review = reviews.get(ref)
        if review is None or ref in seen:
            continue
        lead = row["lead"].split("/", 1)[0].strip()
        if normalized(lead) != normalized(review["lead"]) or normalized(review["match"]) not in normalized(row["description"]):
            continue
        try:
            _, evidence = reader.html(review["url"])
            if normalized(review["evidence_match"]) not in normalized(" ".join(evidence.text)):
                raise PublicSourceError("Karta programu nie zawiera już zweryfikowanego faktu.")
        except PublicSourceError as exc:
            unavailable.append({"url": review["url"], "reason": str(exc)})
            seen.add(ref)
            continue
        seen.add(ref)
        rows.append({
            **review, "ref": ref, "source_title": row["source_title"].split("/", 1)[0].strip(),
            "organization": lead, "organization_kind": "jst", "city": row["city"], "region": row["region"].title(),
            "locator": {
                "workbook_url": url, "sheet": row["sheet"], "row": row["row"], "programme": row["programme"],
                "lead_partner": lead,
                "partners": [
                    name.split("/", 1)[0].strip() for name in row["partners"].split("|")
                    if name.strip() and normalized(name.split("/", 1)[0]) != normalized(lead)
                ],
            },
        })
    unavailable.extend(
        {"url": url, "reason": f"Brak zweryfikowanych danych projektu {ref} w aktualnym wykazie."}
        for ref in reviews.keys() - seen
    )
    return rows, {"scanned": scanned, "unavailable": unavailable, "eligible": len(rows)}


def ncbr(reader: Reader, reviews: dict) -> tuple[list[dict], dict]:
    _, index = reader.html(NCBR_URL)
    links = set()
    for href in index.links:
        parts = urlsplit(urljoin(NCBR_URL, href))
        if parts.scheme == "https" and parts.netloc == "www.gov.pl" and parts.path.startswith("/web/ncbr/"):
            links.add(parts.path.rstrip("/"))
    rows = []
    unavailable = []
    scanned = 0
    for ref, review in reviews.items():
        path = f"/web/ncbr/{ref}"
        url = f"https://www.gov.pl{path}"
        try:
            if path not in links:
                raise PublicSourceError("Brak odnośnika do wdrożenia na liście NCBR.")
            body, page = reader.html(url)
            article = ARTICLE.search(body)
            if not article:
                raise PublicSourceError("Brak materiału o wdrożeniu w odpowiedzi NCBR.")
            scanned += 1
            blocks = [" ".join(" ".join(Page(content).text).split()) for _, content in BLOCKS.findall(article[1])]
            sections = dict(zip((normalized(value) for value in blocks), blocks[1:]))
            lead = sections.get("nazwa beneficjenta/beneficjentów")
            source_title = sections.get("tytuł projektu")
            if not lead or not source_title or normalized(review["match"]) not in normalized(" ".join(blocks)):
                raise PublicSourceError("Zmieniono dane beneficjenta lub nie udało się potwierdzić faktu zastosowania.")
            rows.append({
                **review, "ref": ref, "source_title": source_title, "organization": lead, "url": url,
                "locator": {
                    "publisher": "Narodowe Centrum Badań i Rozwoju", "published": page.published,
                    "project_period": sections.get("okres realizacji projektu"), "processing": "Opracowanie Radaru Innowacji",
                },
            })
        except PublicSourceError as exc:
            unavailable.append({"url": url, "reason": str(exc)})
    return rows, {"scanned": scanned, "unavailable": unavailable, "eligible": len(rows)}


def crossref(reader: Reader, reviews: dict) -> tuple[list[dict], dict]:
    rows = []
    unavailable = []
    for doi, review in reviews.items():
        url = f"{CROSSREF_URL}/works/{quote(doi, safe='/')}"
        try:
            payload, _ = reader.get(url)
            work = json.loads(payload)["message"]
            title = work["title"][0]
            if not title or work["DOI"].lower() != doi or not work["publisher"]:
                raise ValueError("Niekompletna odpowiedź Crossref.")
            rows.append({
                **review, "doi": doi, "title": title, "publisher": work["publisher"],
                "doi_url": f"https://doi.org/{doi}", "metadata_url": url, "metadata_source": "crossref",
                "relationship": "verified_use",
            })
        except (PublicSourceError, ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            unavailable.append({"url": url, "reason": str(exc) if isinstance(exc, PublicSourceError) else "Nieprawidłowe metadane DOI."})
    return rows, {"scanned": len(rows), "eligible": len(rows), "unavailable": unavailable}


COLLECTORS = {"interreg": interreg, "ncbr": ncbr, "crossref": crossref}


def collect(source: str, reviews: dict) -> dict:
    if len(reviews) > MAX_REVIEWS:
        raise PublicSourceError("Wykaz zweryfikowanych rekordów przekracza limit pojedynczego skanu.")
    with httpx.Client(timeout=10, headers={"User-Agent": USER_AGENT}) as http:
        rows, counts = COLLECTORS[source](Reader(http), reviews)
    if not rows:
        reason = counts["unavailable"][0]["reason"] if counts["unavailable"] else "Brak zweryfikowanych rekordów."
        raise PublicSourceError(reason)
    return {
        "rows": rows,
        "selection": {**counts, "complete_scan": not counts["unavailable"]},
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
