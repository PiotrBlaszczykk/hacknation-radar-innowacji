from functools import cache
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from ..models import Innovation


STEPS = {
    "rozwoj": [
        ("Ustal, co sprawdzić", "Zapisz najważniejsze założenie, grupę odbiorców i kryterium udanego testu."),
        ("Przygotuj wersję do testu", "Zbuduj najmniejszy prototyp lub przygotuj próbę zmienionego procesu. Wyznacz osobę odpowiedzialną i termin."),
        ("Zbierz dowody", "Przeprowadź próbę z odbiorcami, porównaj wynik z ustalonym kryterium i zapisz decyzję o dalszych pracach."),
    ],
    "transfer": [
        ("Przygotuj dokumentację transferu", "Zbierz opis rozwiązania, wyniki testów, ograniczenia techniczne i listę praw do wyników."),
        ("Wybierz odbiorcę technologii", "Przedstaw zakres współpracy firmom lub instytucjom, które mogą przejąć technologię. Ustal, kto odpowiada za walidację i integrację."),
        ("Uzgodnij warunki przekazania", "Ustal z partnerem zakres testu, dostęp do dokumentacji i warunki korzystania z technologii lub know-how."),
    ],
    "komercjalizacja": [
        ("Potwierdź zainteresowanie klientów", "Pokaż rozwiązanie potencjalnym nabywcom i zapytaj o warunki zakupu, cenę oraz alternatywy."),
        ("Przygotuj ofertę i policz koszty", "Określ zakres oferty, sposób sprzedaży lub licencjonowania, cenę oraz koszty uruchomienia i obsługi."),
        ("Zaproponuj odpłatny pilotaż", "Ustal z pierwszym klientem budżet, termin, kryteria odbioru i warunki kontynuacji po pilotażu."),
    ],
    "wdrozenie": [
        ("Opisz rozwiązanie do powtórzenia", "Przygotuj instrukcję, materiały do użycia, koszty, wymagane zasoby, podział ról i sposób pomiaru efektu."),
        ("Znajdź pierwszą organizację", "Wybierz organizację z podobnym problemem i uzgodnij z jej przedstawicielem zakres, zasoby i osobę prowadzącą."),
        ("Przeprowadź wspólny pilotaż", "Uruchom ograniczoną wersję u partnera, zmierz efekt przed i po i wspólnie zdecydujcie o kontynuacji."),
    ],
}

METRICS = {
    "rozwoj": [
        ("Plan testu", "W ciągu 4 tygodni powstaje 1 scenariusz testu z mierzalnym kryterium sukcesu."),
        ("Wynik pierwszego testu", "W ciągu 3 miesięcy zespół przeprowadza co najmniej 1 test i zapisuje wynik oraz decyzję o dalszych pracach."),
    ],
    "transfer": [
        ("Pakiet transferowy", "W ciągu 6 tygodni powstaje 1 pakiet z wynikami testów, opisem technicznym i listą praw do wyników."),
        ("Odbiorca technologii", "W ciągu 6 miesięcy co najmniej 1 odbiorca podpisuje porozumienie o walidacji lub umowę umożliwiającą korzystanie z technologii."),
    ],
    "komercjalizacja": [
        ("Walidacja popytu", "W ciągu 2 miesięcy zespół dokumentuje rozmowy o cenie i warunkach zakupu z co najmniej 5 potencjalnymi klientami."),
        ("Pierwsza sprzedaż", "W ciągu 6 miesięcy co najmniej 1 klient zawiera umowę odpłatnego pilotażu, zakupu lub licencji."),
    ],
    "wdrozenie": [
        ("Pierwsze wdrożenie poza miejscem powstania", "W ciągu 6 miesięcy co najmniej 1 inna organizacja uruchamia rozwiązanie u siebie."),
        ("Pomiar efektu u odbiorcy", "W ciągu 30 dni od zakończenia pilotażu partner zapisuje pomiar co najmniej 1 wskaźnika przed i po oraz decyzję o kontynuacji."),
    ],
}


@cache
def instruments() -> list[dict]:
    return yaml.safe_load(Path(__file__).with_name("instruments.yaml").read_text(encoding="utf-8"))


def plan_for(innovation: Innovation, path: str) -> tuple[list[dict], list[dict]]:
    organization = innovation.organization
    supplements = {}
    if organization and innovation.kind and innovation.stage:
        website = urlsplit(organization.website or "").hostname or ""
        region = (organization.region or "").strip().casefold()
        needs = innovation.support_needs or []
        matching = (
            item for item in instruments()
            if path in item["paths"]
            and innovation.kind in item["innovation_kinds"]
            and innovation.stage in item["stages"]
            and organization.kind in item["organization_kinds"]
            and (not item.get("region") or region == item["region"])
            and (not item.get("website_domain") or website == item["website_domain"]
                 or website.endswith("." + item["website_domain"]))
            and (item["id"] != "uprp-zgloszenie" or path == "transfer" or "ochrona_ip" in needs)
        )
        # Najpierw dopasowane, potwierdzone źródła. Jedno uzupełnienie na etap planu.
        for item in sorted(matching, key=lambda candidate: (not candidate["verified"], candidate["after_step"])):
            supplements.setdefault(item["after_step"], item)
            if len(supplements) == 2:
                break

    steps = []
    for position, (title, description) in enumerate(STEPS[path], start=1):
        if item := supplements.get(position - 1):
            steps.append({
                "title": item["step_title"], "description": item["guidance"],
                "instrument": item["name"], "url": item["url"], "verified": item["verified"],
            })
        steps.append({"title": title, "description": description, "instrument": None, "url": None})
    return steps, [{"name": name, "target": target} for name, target in METRICS[path]]
