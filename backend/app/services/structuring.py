import math
import re
from textwrap import shorten

from flask import current_app

from .. import domain
from . import decisions, llm

KIND_CRITERIA = {
    "technologiczna": "Istotą jest nowe urządzenie, technologia, algorytm lub oprogramowanie.",
    "organizacyjna": "Organizacyjna: instytucja wprowadza nową usługę albo podział ról i zasobów w swojej działalności.",
    "edukacyjna": "Edukacyjna: uczniowie w ramach zajęć uczą się inaczej, np. wykonują realne zlecenia lub uczą się nawzajem.",
    "spoleczna": "Społeczna: mieszkańcy tworzą sieć pomocy dla osób w potrzebie lub poprawiają ich włączenie społeczne.",
    "procesowa": "Istotą jest uproszczenie istniejącej procedury, obiegu informacji lub sposobu obsługi sprawy.",
}
STAGE_CRITERIA = {
    "pomysl": "Plan lub opis zamierzenia bez wzmianki o gotowym rozwiązaniu lub próbach.",
    "prototyp": "Powstał prototyp, model lub demonstrator, ewentualnie sprawdzany w warunkach testowych.",
    "pilotaz": "Pilotaż: opisana wprost czasowa próba z odbiorcami, np. jedna klasa lub placówka testuje rozwiązanie przed wdrożeniem.",
    "wdrozona": "Wdrożona lokalnie: instytucja uruchomiła rozwiązanie lub wdrożyła zmianę i korzysta z niej w zwykłej pracy.",
    "skalowana": "Rozwiązanie jest już przenoszone do kolejnych niezależnych organizacji lub lokalizacji.",
}
DOMAIN_CRITERIA = {
    "edukacja": "Edukacja: zmiana w uczeniu się, metodyce zajęć lub kształceniu jest istotnym celem rozwiązania.",
    "zdrowie": "Zdrowie: opieka zdrowotna, profilaktyka, sprzęt rehabilitacyjny lub wsparcie samodzielności osób starszych.",
    "jakosc_zycia": "Codzienne potrzeby mieszkańców, włączenie społeczne, samodzielność lub pomoc społeczna.",
    "cyfryzacja_ict": "Cyfryzacja i ICT: tekst opisuje algorytm, system informatyczny lub transmisję danych jako część rozwiązania.",
    "energia_srodowisko": "Energia, klimat, ochrona środowiska, zanieczyszczenia lub gospodarowanie zasobami.",
    "transport_mobilnosc": "Przemieszczanie osób i ładunków, transport zbiorowy lub ruch drogowy.",
    "motoryzacja": "Budowa, produkcja lub eksploatacja samochodów i ich podzespołów.",
    "lotnictwo_kosmos": "Statki powietrzne i kosmiczne, lotnictwo, satelity lub ich infrastruktura.",
    "przemysl": "Procesy produkcji przemysłowej, automatyzacja fabryk lub technologie wytwarzania na skalę przemysłową.",
    "rolnictwo_zywnosc": "Uprawa, hodowla, produkcja żywności lub jej przetwarzanie.",
    "administracja": "Obsługa spraw urzędowych, procedury administracji lub zarządzanie publiczne.",
    "kultura": "Kultura: rozwiązanie rozwija ofertę biblioteki lub innej instytucji kultury albo dotyczy sztuki lub dziedzictwa.",
    "bezpieczenstwo": "Ochrona ludzi, mienia lub systemów przed zagrożeniami albo reagowanie kryzysowe.",
}
SUPPORT_CRITERIA = {
    "partner_wdrozeniowy": "Twórcy poszukują organizacji, która pomoże uruchomić lub przenieść rozwiązanie.",
    "pierwszy_uzytkownik": "Twórcy poszukują pierwszego odbiorcy, który wypróbuje rozwiązanie w praktyce.",
    "finansowanie": "Twórcy proszą o środki pieniężne, dotację albo inwestycję.",
    "mentoring": "Twórcy proszą o konsultacje, doradztwo lub wsparcie doświadczonej osoby.",
    "ochrona_ip": "Twórcy potrzebują pomocy przy patencie, licencji lub innej ochronie własności intelektualnej.",
    "zespol": "Twórcy szukają osób, które dołączą do pracy nad rozwiązaniem.",
    "promocja": "Twórcy proszą o wsparcie w dotarciu do odbiorców lub upowszechnieniu informacji.",
}

TAG_DICTIONARIES = {
    "kind": domain.INNOVATION_KINDS,
    "stage": domain.STAGES,
    "domains": domain.DOMAINS,
    "support_needs": domain.SUPPORT_NEEDS,
}

QUESTIONS = {
    "kind": {
        "type": "choice",
        "instructions": "Wybierz główny typ zmiany. Nowe zadania w ramach zajęć to zmiana edukacyjna, a rozszerzenie stałej oferty instytucji to zmiana organizacyjna.",
        "criteria": KIND_CRITERIA,
    },
    "stage": {
        "type": "choice",
        "instructions": "Jaki etap jest udokumentowany? Jeśli instytucja już regularnie oferuje usługę i tekst nie wspomina okresu próbnego, wybierz wdrożenie lokalne.",
        "criteria": STAGE_CRITERIA,
    },
    "domains": {
        "type": "multi",
        "instructions": "Oceń, czy obszar wynika wprost z głównego celu lub zastosowania rozwiązania. "
        "Sam kontekst, poboczne zajęcia lub użycie gotowego narzędzia jako pomocy to za mało.",
        "criteria": DOMAIN_CRITERIA,
        "max": 3,
        "threshold": 0.55,
    },
    "support_needs": {
        "type": "multi",
        "instructions": "Zaznacz tylko wsparcie, o które twórcy wprost proszą lub wskazują jako brak. "
        "Jeśli tekst nic o tym nie mówi albo pomoc już otrzymano, odpowiedz nie.",
        "criteria": SUPPORT_CRITERIA,
        "max": 3,
        "threshold": 0.80,
    },
    "is_innovation": {
        "type": "noul",
        "instructions": "Czy ten tekst opisuje konkretne nowe rozwiązanie lub zmianę sposobu działania, "
        "które można przenieść do innych organizacji? Sama zapowiedź wydarzenia, rutynowa informacja "
        "lub opis tematu badań bez rozwiązania to odpowiedź nie.",
    },
}

FALLBACK_THRESHOLDS = {"domains": 0.85, "support_needs": 0.95}

TEXT_LIMITS = {"title": 140, "summary": 320, "problem": 420, "solution": 520, "results": 420}
QUESTION_TEMPLATES = {
    "results": "Ile osób skorzystało z rozwiązania „{title}” i po czym poznaliście jego efekty?",
    "problem": "Co sprawiało trudność odbiorcom, zanim pojawiło się rozwiązanie „{title}”?",
    "solution": "Co musi zrobić inna organizacja, żeby zastosować rozwiązanie „{title}”?",
    "stage": "Gdzie i z kim udało się już wypróbować rozwiązanie „{title}”?",
    "support_needs": "Jakiego wsparcia potrzebujecie w kolejnym kroku projektu „{title}”?",
    "summary": "Na czym polega rozwiązanie „{title}” i kto z niego korzysta?",
    "kind": "Co przede wszystkim zmieniło się po wprowadzeniu rozwiązania „{title}”?",
    "domains": "W jakiej dziedzinie chcecie wykorzystać rozwiązanie „{title}”?",
    "keywords": "Po jakich hasłach inni powinni znaleźć rozwiązanie „{title}”?",
}
TEXT_SCHEMA = {
    "type": "object",
    "properties": {
        **{field: {"type": "string", "maxLength": limit} for field, limit in TEXT_LIMITS.items()},
        "keywords": {"type": "array", "maxItems": 6, "items": {"type": "string", "maxLength": 56}},
        "questions": {
            "type": "object",
            "properties": {
                field: {"type": "string", "maxLength": 180}
                for field in ("results", "problem", "solution")
            },
            "required": ["results", "problem", "solution"],
            "additionalProperties": False,
        },
    },
    "required": [*TEXT_LIMITS, "keywords", "questions"],
    "additionalProperties": False,
}
SYSTEM_PROMPT = """Tworzysz kartę po polsku wyłącznie na podstawie materiału źródłowego.
title: krótka nazwa. summary: 1–2 zdania, na czym polega działanie i dla kogo lub po co je podjęto.
Jeśli źródło opisuje plan, zacznij od „Projekt ma…” lub „Zespół planuje…”. Unikaj ocen i języka reklamowego.
problem: opisana trudność przed zmianą. solution: konkretne działanie. results: tylko zaobserwowany efekt
albo wynik pomiaru, zacytowany ze źródła. Cel, czas trwania i samo przeprowadzenie testu to nie wyniki.
Gdy brakuje przesłanki, zwróć "". Dotyczy to także przypadku, gdy łatwo się domyślić problemu lub efektu.
Liczby zachowaj w zapisie ze źródła. Pomijaj skróty liczbowe i nie przeliczaj wartości.
Liczba zdarzeń bez porównania nie oznacza wzrostu ani spadku.
W ogłoszeniu podaj w summary, czego dotyczy informacja. Pola problem, solution i results zostaw puste.
Przykład materiału: „Od marca wypożyczamy wiertarki na kartę”. summary: „Biblioteka wypożycza wiertarki na kartę”
tylko jeśli źródło wskazuje bibliotekę, w pozostałych przypadkach „Wiertarki są wypożyczane na kartę”. problem i results: "".
keywords: do sześciu haseł ze źródła. questions: dla każdego pustego pola results, problem i solution napisz
po jednym pytaniu z konkretem ze źródła, a dla uzupełnionego pola wpisz "". Np. dla wiertarek i pustego results:
"Ile wiertarek wypożyczono od marca i ilu osobom?"."""

PLACEHOLDERS = {
    "", "-", "–", "—", "brak", "brak danych", "brak informacji", "brak wyników",
    "nie podano", "nie podano wyników", "nie podano danych", "nie określono",
    "nie wiadomo", "nie dotyczy", "n/d", "nd", "n/a", "na", "none", "null",
}

ABSENT_IN_SOURCE = re.compile(
    r"(?:brak|nie podano)(?: (?:danych|informacji|wyników))? (?:w (?:opisie|tekście|źródle)|o (?:wynikach|konkretnym problemie))"
    r"|(?:odnotowane )?(?:efekty|wyniki|dane) nie (?:są|zostały) podane"
    r"|trudność w opisaniu problemu [-–—] brak"
)
NUMBER = re.compile(r"(?<!\w)\d+(?:[.,]\d+)*(?!\w)")
GENERIC_QUESTION = re.compile(r"^(?:czy (?:możesz|możecie) (?:coś więcej|powiedzieć więcej)|podaj(?:cie)? więcej)", re.I)


def _source_excerpt(text: str) -> str:
    # Budżet w bajtach uwzględnia także tekst z rzadkimi znakami i zostawia miejsce na pytania oraz odpowiedź.
    budget = min(4096, current_app.config["LLM_NUM_CTX"]) * 5 // 8
    return text.strip().encode("utf-8", errors="ignore")[:budget].decode("utf-8", errors="ignore").rstrip()


def _clean(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    value = " ".join(value.split())
    marker = value.casefold().strip(' .!?;:„”"()')
    if marker in PLACEHOLDERS or ABSENT_IN_SOURCE.fullmatch(marker):
        return ""
    if len(value) <= limit:
        return value
    shortened = shorten(value, width=limit, placeholder="…")
    return shortened if shortened != "…" else value[: limit - 1] + "…"


def _probability(value: object) -> float | None:
    if type(value) in (float, int) and 0 <= value <= 1 and math.isfinite(value):
        return float(value)
    return None


def _extract_tags(answers: dict) -> dict:
    tags = {}
    for field, dictionary in TAG_DICTIONARIES.items():
        answer = answers.get(field, {})
        raw_probabilities = answer.get("probabilities")
        probabilities = {
            key: p
            for key, raw in (raw_probabilities.items() if isinstance(raw_probabilities, dict) else ())
            if key in dictionary and (p := _probability(raw)) is not None
        }
        if QUESTIONS[field]["type"] == "multi":
            selected = answer.get("selected", [])
            if not isinstance(selected, list):
                selected = []
            value = list(dict.fromkeys(k for k in selected if isinstance(k, str) and k in dictionary))
            if answer.get("calibrated") is False:
                value = [key for key in value if probabilities.get(key, 0) >= FALLBACK_THRESHOLDS[field]]
            value = value[: QUESTIONS[field]["max"]]
        else:
            choice = answer.get("choice")
            value = choice if isinstance(choice, str) and choice in dictionary else None

        confidence = _probability(answer.get("confidence"))
        if isinstance(value, str):
            confidence = probabilities.get(value, confidence)
        elif value:
            confidence = min((probabilities[key] for key in value if key in probabilities), default=confidence)
        tags[field] = {
            "value": value,
            "confidence": (confidence or 0.0) if value else 0.0,
            "probabilities": probabilities,
        }
    return tags


def _follow_up(raw: object, missing: list[str], title: str, excerpt: str) -> list[str]:
    proposals = raw if isinstance(raw, dict) else {}
    questions = []
    subject = title.replace("„", "").replace("”", "")
    subject = _clean(subject, 70) or title
    templates = QUESTION_TEMPLATES.copy()
    if re.search(r"\b(?:uczni|starszak|pierwszak)", excerpt, re.I):
        templates["results"] = "Ilu uczniów wzięło udział w „{title}” i jak sprawdziliście, czego się nauczyli?"
    if re.search(r"\bwypożycz\w*.*?\b(?:narzędzi|wiertar)", excerpt, re.I | re.S):
        templates["results"] = "Ile wypożyczeń odnotowano w ramach „{title}” i w jakim okresie?"
        templates["problem"] = "Do jakich prac mieszkańcy potrzebują narzędzi z projektu „{title}”?"
    for field, template in templates.items():
        if field not in missing:
            continue
        question = _clean(proposals.get(field), 180)
        if (
            not question.endswith("?")
            or len(question.split()) < 6
            or GENERIC_QUESTION.match(question)
            or question in questions
        ):
            question = template.format(title=subject)
        questions.append(question)
        if len(questions) == 3:
            break
    return questions


def structure_text(text: str) -> dict:
    """Buduje propozycję karty dla formularza i radaru. Rzuca LLMUnavailable przy awarii modelu."""
    excerpt = _source_excerpt(text)
    answers = decisions.decide(excerpt, QUESTIONS)
    draft = llm.chat_json(SYSTEM_PROMPT, excerpt, TEXT_SCHEMA, temperature=0)
    if not isinstance(draft, dict):
        raise llm.LLMUnavailable("Model językowy nie zwrócił karty.")

    tags = _extract_tags(answers)
    card = {field: _clean(draft.get(field), limit) for field, limit in TEXT_LIMITS.items()}
    source_numbers = set(NUMBER.findall(excerpt))
    if not set(NUMBER.findall(card["results"])).issubset(source_numbers):
        card["results"] = ""
    if not set(NUMBER.findall(card["summary"])).issubset(source_numbers):
        card["summary"] = ""
        # Powtórz tylko streszczenie z tekstem pozbawionym liczb, które model próbował przeliczyć.
        repair = llm.chat_json(
            "Streść po polsku to, co zrobiono lub zaplanowano, w 1–2 zdaniach. "
            "Korzystaj tylko z tekstu. Pomiń liczby i daty.",
            re.sub(r"\(?\d[\d.,/:-]*(?:[kK](?!\w))?\)?", "", excerpt),
            {
                "type": "object",
                "properties": {"summary": TEXT_SCHEMA["properties"]["summary"]},
                "required": ["summary"],
                "additionalProperties": False,
            },
            temperature=0,
        )
        summary = _clean(repair.get("summary"), TEXT_LIMITS["summary"]) if isinstance(repair, dict) else ""
        if not NUMBER.search(summary):
            card["summary"] = summary
    keywords = draft.get("keywords")
    card["keywords"] = list(dict.fromkeys(
        word for value in (keywords if isinstance(keywords, list) else []) if (word := _clean(value, 56))
    ))[:6]
    card.update({field: tag["value"] for field, tag in tags.items()})
    missing = [field for field, value in card.items() if not value]
    if not card["title"]:
        card["title"] = _clean(excerpt, TEXT_LIMITS["title"]) or "Innowacja bez nazwy"

    innovation = answers.get("is_innovation", {})
    return {
        "card": card,
        "tags": tags,
        "is_innovation": _probability(innovation.get("noul")) or 0.0,
        "missing": missing,
        "questions": _follow_up(draft.get("questions"), missing, card["title"], excerpt),
        "engine": {
            "tags": innovation.get("engine") or answers.get("kind", {}).get("engine", ""),
            "text": current_app.config["LLM_MODEL"],
        },
    }
