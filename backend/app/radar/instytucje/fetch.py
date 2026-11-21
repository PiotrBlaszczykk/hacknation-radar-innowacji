"""Pobieranie publicznych list i wpisów oraz sprawdzanie zredagowanych faktów."""

import hashlib
import json
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlsplit

import httpx
import yaml

from ..radon import write_json

SOURCE = "strony_instytucji"
CACHE_DIR = Path(__file__).resolve().parents[4] / "data/cache/instytucje"
USER_AGENT = "Radar-Innowacji/1.0 (HackNation; public data import)"
SOURCES = Path(__file__).with_name("sources.yaml")
MAX_BYTES = 2_000_000
MAX_ARTICLES = 32
MAX_INDEXES = 16
CACHE_AGE = 86_400
RESTRICTED = re.compile(r"\b(?:noai|noimageai|notrain|notdm|noml)\b", re.I)
DATE = re.compile(r"(?<!\d)20\d\d-\d\d-\d\d(?!\d)")


class InstitutionError(Exception):
    pass


class AnalysisRestricted(InstitutionError):
    pass


def read_sources() -> list[dict]:
    return yaml.safe_load(SOURCES.read_text(encoding="utf-8"))


def article_ref(url: str) -> str:
    parts = urlsplit(url)
    host = (parts.hostname or "").removeprefix("www.")
    path = unquote(parts.path).rstrip("/")
    query = parse_qs(parts.query)
    if host.endswith(".szkolnastrona.pl"):
        match = re.fullmatch(r"/(?:art|a),(\d+)(?:,.*)?", path)
        if match:
            return f"{host}:{match[1]}"
        if path == "/index.php" and query.get("c") == ["article"] and query.get("id", [""])[0].isdigit():
            return f"{host}:{query['id'][0]}"
    if host in {"erzeszow.pl", "urbanlab.erzeszow.pl"}:
        match = re.fullmatch(r".*/(\d+)(?:-[^/]+)?\.html?", path)
        if match:
            return f"{host}:{match[1]}"
        match = re.fullmatch(r"/print/\d+/\d+/(\d+)", path)
        if match:
            return f"{host}:{match[1]}"
    if host == "krosno.pl":
        match = re.fullmatch(r"/aktualnosci/[^/]+,(\d+)", path)
        if match:
            return f"{host}:{match[1]}"
    post_id = query.get("p", [""])[0]
    if post_id.isdigit():
        return f"{host}:post:{post_id}"
    return f"{host}{path}"


class Page(HTMLParser):
    def __init__(self, html: str):
        super().__init__()
        self.links = []
        self.text = []
        self.restricted = False
        self.published = None
        self.hidden = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style"}:
            self.hidden = True
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag == "meta":
            name = (attrs.get("name") or "").lower()
            content = attrs.get("content") or ""
            if (name in {"robots", "googlebot"} and RESTRICTED.search(content)) or (
                name == "tdm-reservation" and content.strip() == "1"
            ):
                self.restricted = True
            date_name = attrs.get("property") or attrs.get("itemprop") or name
            if date_name in {"article:published_time", "datePublished", "date"}:
                self.published = self.published or date_value(content)
        if tag == "time":
            self.published = self.published or date_value(attrs.get("datetime") or "")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = False

    def handle_data(self, data):
        if not self.hidden:
            self.text.append(data)


def date_value(value: str) -> str | None:
    match = DATE.search(value)
    return match[0] if match else None


def normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def allowed(rules: str, url: str) -> bool:
    groups = defaultdict(list)
    agents = []
    started_rules = False
    for line in rules.splitlines():
        directive, _, value = line.partition("#")[0].partition(":")
        directive, value = directive.strip().lower(), value.strip()
        if directive == "user-agent" and value:
            if started_rules:
                agents = []
                started_rules = False
            agents.append(value.lower())
        elif directive in {"allow", "disallow"}:
            started_rules = True
            if value:
                for agent in agents:
                    groups[agent].append((value, directive == "allow"))

    product = USER_AGENT.split("/", 1)[0].lower()
    parts = urlsplit(url)
    target = unquote(parts.path or "/")
    if parts.query:
        target += "?" + unquote(parts.query)
    matches = []
    for value, permit in groups.get(product, groups["*"]):
        pattern = re.escape(unquote(value.removesuffix("$"))).replace(r"\*", ".*")
        if re.match(pattern + ("$" if value.endswith("$") else ""), target):
            matches.append((len(value.replace("*", "").removesuffix("$")), permit))
    return max(matches, default=(0, True))[1]


class Reader:
    def __init__(self, http: httpx.Client, cache: Path, *, refresh: bool, cached_only: bool):
        self.http = http
        self.cache = cache
        self.refresh = refresh
        self.cached_only = cached_only
        self.robots = {}
        self.last_request = {}

    def request(self, url: str) -> tuple[int, httpx.Headers, str]:
        host = urlsplit(url).netloc
        time.sleep(max(0, self.last_request.get(host, 0) + 0.5 - time.monotonic()))
        try:
            with self.http.stream("GET", url) as response:
                if response.status_code != 200:
                    return response.status_code, response.headers, ""
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise InstitutionError("Odpowiedź przekroczyła limit rozmiaru.")
                return response.status_code, response.headers, data.decode(response.encoding or "utf-8", errors="replace")
        except httpx.HTTPError as exc:
            raise InstitutionError("Witryna nie odpowiedziała.") from exc
        finally:
            self.last_request[host] = time.monotonic()

    def robot_rules(self, origin: str) -> str:
        if origin not in self.robots:
            try:
                status, _, rules = self.request(f"{origin}/robots.txt")
                if status not in {200, 404, 410}:
                    raise InstitutionError(f"Nie można sprawdzić robots.txt (HTTP {status}).")
                self.robots[origin] = rules
            except InstitutionError as exc:
                self.robots[origin] = exc
        rules = self.robots[origin]
        if isinstance(rules, InstitutionError):
            raise rules
        return rules

    def page(self, origin: str, url: str) -> Page:
        rules = self.robot_rules(origin)
        for _ in range(4):
            parts = urlsplit(url)
            if f"{parts.scheme}://{parts.netloc}" != origin or not allowed(rules, url):
                raise AnalysisRestricted("Adres spoza listy lub ścieżka wyłączona w robots.txt.")
            status, headers, html = self.request(url)
            if status in {301, 302, 303, 307, 308} and headers.get("location"):
                url = urljoin(url, headers["location"])
                continue
            if status != 200 or "text/html" not in headers.get("content-type", "").lower():
                raise InstitutionError(f"Brak dostępnej strony HTML (HTTP {status}).")
            if RESTRICTED.search(headers.get("x-robots-tag", "")) or headers.get("tdm-reservation") == "1":
                raise AnalysisRestricted("Witryna zastrzega analizę maszynową.")
            page = Page(html)
            if page.restricted:
                raise AnalysisRestricted("Witryna zastrzega analizę maszynową.")
            return page
        raise InstitutionError("Zbyt wiele przekierowań.")

    def read(self, origin: str, path: str, marker: str, aliases: dict[str, str]) -> dict:
        url = origin + path
        cache_key = f"{url}\n{marker}" if marker else json.dumps([url, *sorted(aliases)])
        digest = hashlib.sha256(cache_key.encode()).hexdigest()[:24]
        cached = self.cache / f"page-{digest}.json"
        if not self.refresh:
            try:
                if self.cached_only or time.time() - cached.stat().st_mtime < CACHE_AGE:
                    data = json.loads(cached.read_bytes())
                    if isinstance(data, dict) and {"observed_at", "matched" if marker else "links"} <= data.keys():
                        return data
            except (OSError, ValueError):
                pass
        if self.cached_only:
            raise InstitutionError("Brak zapisanej obserwacji.")
        try:
            page = self.page(origin, url)
        except AnalysisRestricted:
            cached.unlink(missing_ok=True)
            raise
        if marker:
            text = normalized(" ".join(page.text))
            data = {"matched": normalized(marker) in text, "published": page.published}
        else:
            # Zapisujemy jedynie linki z rejestru, które znaleziono na liście.
            linked = {article_ref(urljoin(url, href)) for href in page.links}
            data = {"links": sorted({aliases[key] for key in linked & aliases.keys()})}
        data["observed_at"] = datetime.now(timezone.utc).isoformat()
        write_json(cached, data)
        return data


def collect(cache_dir: Path, *, refresh: bool = False, cached_only: bool = False) -> tuple[list[dict], dict]:
    cache_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    sources = read_sources()
    if (
        sum(len(site["indexes"]) for site in sources) > MAX_INDEXES
        or sum(len(site["articles"]) for site in sources) > MAX_ARTICLES
    ):
        raise InstitutionError("Lista adresów przekracza limit pojedynczego skanu.")

    failures = []
    rejected = []
    scanned = 0
    candidates = {}
    listed = set()
    seen = set()
    with httpx.Client(timeout=8.0, headers={"User-Agent": USER_AGENT}) as http:
        reader = Reader(http, cache_dir, refresh=refresh, cached_only=cached_only)
        for site in sources:
            origin = site["origin"]
            reviews = {}
            aliases = {}
            for row in site["articles"]:
                ref = article_ref(origin + row.get("id_path", row["path"]))
                reviews.setdefault(ref, row)
                aliases[ref] = ref
                aliases[article_ref(origin + row["path"])] = ref
            for path in site["indexes"]:
                try:
                    listed.update(reader.read(origin, path, "", aliases)["links"])
                except InstitutionError as exc:
                    failures.append({"url": origin + path, "reason": str(exc)})

            # Adresy w rejestrze prowadzą także do starszych wpisów, które zeszły z listy aktualności.
            for ref in [*sorted(listed & reviews.keys()), *(key for key in reviews if key not in listed)]:
                if ref in seen:
                    continue
                row = reviews[ref]
                url = origin + row["path"]
                try:
                    result = reader.read(origin, row["path"], row["match"], {})
                except InstitutionError as exc:
                    failures.append({"url": url, "reason": str(exc)})
                    continue
                seen.add(ref)
                scanned += 1
                if not result["matched"]:
                    failures.append({"url": url, "reason": "Brak sprawdzonego fragmentu w źródle."})
                    continue
                if "reject" in row:
                    rejected.append({"url": url, "reason": row["reject"]})
                    continue
                candidates[ref] = {
                    **row, "site": site, "ref": ref, "url": url,
                    "observed_at": result["observed_at"], "published": row.get("published") or result.get("published"),
                }

    stats = {
        "scanned": scanned, "linked_from_indexes": len(listed), "eligible": len(candidates),
        "rejected": rejected, "unavailable": failures, "complete_scan": not failures,
    }
    return list(candidates.values()), stats
