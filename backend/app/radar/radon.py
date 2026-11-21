"""Stronicowanie RAD-on i lokalna kopia stron z polami potrzebnymi radarowi."""

import hashlib
import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from fcntl import LOCK_EX, LOCK_NB, flock
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import quote, urlencode

import httpx

API = "https://radon.nauka.gov.pl/opendata/polon"
SOURCE = "radon_projekty"
PROJECTS_URL = f"{API}/projects"
START_DATE = "2019-01-01"
PAGE_SIZE = 100
CACHE_DIR = Path(__file__).resolve().parents[3] / "data/cache/radon"

PROJECT_FIELDS = (
    "projectUuid", "projectTitlePl", "projectAbstractPl", "keywords", "projectStartDate",
    "projectEndDate", "projectClassification", "anotherProjectClassification", "financedCompetition",
    "entityShowingAchievementsUuid", "entityShowingAchievementsName", "totalFunds",
    "nationalFunds", "foreignFunds",
)
INSTITUTION_FIELDS = ("institutionUuid", "name", "iKindName", "voivodeship", "city", "www")
PARTNER_FIELDS = ("institutionUuid", "institutionName", "leader")
FINANCER_FIELDS = ("financingInstitutionUuid", "financingInstitutionName", "sourceOfFinancing")


class RadonError(Exception):
    pass


class MissingCachedPage(RadonError):
    pass


class RadarBusy(RadonError):
    pass


def profile_url(ref: str) -> str:
    return f"https://radon.nauka.gov.pl/dane/profil/{quote(ref, safe='')}"


def write_json(path: Path, value: dict) -> None:
    with NamedTemporaryFile(dir=path.parent, encoding="utf-8", mode="w", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, ensure_ascii=False, separators=(",", ":"))
            stream.close()
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


@contextmanager
def run_lock(cache_dir: Path):
    cache_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (cache_dir / ".run.lock").open("a") as stream:
        try:
            flock(stream, LOCK_EX | LOCK_NB)
        except BlockingIOError as exc:
            raise RadarBusy("Radar już sprawdza to źródło.") from exc
        yield


def _project_fields(record: dict) -> dict:
    return {
        **{key: record.get(key) for key in PROJECT_FIELDS},
        "implementingInstitutions": [
            {key: partner.get(key) for key in PARTNER_FIELDS}
            for partner in (record.get("implementingInstitutions") or []) if isinstance(partner, dict)
        ],
        "financingInstitutions": [
            {key: financer.get(key) for key in FINANCER_FIELDS}
            for financer in (record.get("financingInstitutions") or []) if isinstance(financer, dict)
        ],
    }


def _valid_page(page) -> bool:
    return (
        isinstance(page, dict)
        and isinstance(page.get("results"), list)
        and all(isinstance(row, dict) for row in page["results"])
        and isinstance(page.get("pagination"), dict)
        and type(page["pagination"].get("maxCount")) is int
    )


class RadonClient:
    def __init__(
        self, http: httpx.Client, cache_dir: Path, *, refresh: bool = False, cached_only: bool = False,
    ):
        self.http = http
        self.cache_dir = cache_dir
        self.refresh = refresh
        self.cached_only = cached_only
        self.last_request = 0.0
        self.downloaded_pages = 0

    def pages(self, endpoint: str, **filters: str) -> Iterator[list[dict]]:
        token = ""
        seen = set()
        received = 0
        while True:
            params = {"resultNumbers": PAGE_SIZE, **filters}
            if token:
                params["token"] = token
            page = self._page(endpoint, params)
            results = page["results"]
            pagination = page["pagination"]
            received += len(results)
            if results:
                yield results
            if not results or received >= pagination["maxCount"]:
                return
            token = pagination.get("token")
            if not token or token in seen:
                raise RadonError("RAD-on nie zwrócił kolejnego tokenu przed końcem danych.")
            seen.add(token)

    def _page(self, endpoint: str, params: dict) -> dict:
        key = hashlib.sha256(urlencode(sorted(params.items())).encode()).hexdigest()[:24]
        path = self.cache_dir / f"{endpoint}-{key}.json"
        if not self.refresh and path.is_file():
            try:
                cached = json.loads(path.read_bytes())
                if _valid_page(cached):
                    return cached
            except (ValueError, UnicodeError):
                pass

        if self.cached_only:
            raise MissingCachedPage("W pamięci brakuje kolejnej strony RAD-on.")

        for attempt in range(3):
            time.sleep(max(0, self.last_request + 0.35 - time.monotonic()))
            try:
                response = self.http.get(f"{API}/{endpoint}", params=params)
                response.raise_for_status()
                page = response.json()
                break
            except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
                status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                if attempt == 2 or (status is not None and status < 500 and status != 429):
                    raise RadonError(f"Nie udało się pobrać danych RAD-on ({status or 'brak poprawnej odpowiedzi'}).") from exc
                time.sleep(2 ** attempt)
            finally:
                self.last_request = time.monotonic()

        if not _valid_page(page):
            raise RadonError("RAD-on zwrócił nieoczekiwany format danych.")

        if endpoint == "projects":
            results = [_project_fields(record) for record in page["results"]]
        else:
            results = [{key: row.get(key) for key in INSTITUTION_FIELDS} for row in page["results"]]
        page = {"results": results, "pagination": page["pagination"], "version": page.get("version")}
        write_json(path, page)
        self.downloaded_pages += 1
        return page


def http_client() -> httpx.Client:
    return httpx.Client(timeout=30.0, headers={"User-Agent": "Radar-Innowacji/1.0 (HackNation; public data import)"})
