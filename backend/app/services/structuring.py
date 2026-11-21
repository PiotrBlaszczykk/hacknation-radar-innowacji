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

STRUCTURING_VERSION = "2"
TEXT_LIMITS = {"title": 140, "summary": 320, "problem": 420, "solution": 520, "results": 420}
TEXT_SCHEMA = {
    "type": "object",
    "properties": {
        **{field: {"type": "string", "maxLength": limit} for field, limit in TEXT_LIMITS.items()},
        "keywords": {"type": "array", "maxItems": 6, "items": {"type": "string", "maxLength": 56}},
        "questions": {
            "type": "array",
            "maxItems": 3,
            "items": {"type": "string", "maxLength": 180},
        },
    },
    "required": [*TEXT_LIMITS, "keywords", "questions"],
    "additionalProperties": False,
}
SYSTEM_PROMPT = """Tworzysz kartę po polsku wyłącznie na podstawie materiału źródłowego.
title: krótka nazwa. summary: 1–2 zdania o działaniu i odbiorcach. Liczbowe efekty zapisz w results.
solution: konkretne działanie, opisz jego mechanizm. Jeśli działanie jest planowane, powiedz to wprost w summary i solution.
problem: skopiuj ze źródła zdanie lub fragment opisujący trudność przed zmianą, również jeśli jest w środku zdania.
results: skopiuj całe zdania źródłowe opisujące zaobserwowane efekty lub pomiary, także brak zmiany.
Przepisuj dokładnie liczby, jednostki, kierunek i porównanie. Cel, przewidywanie i samo przeprowadzenie próby pomiń w results.
Gdy źródło nie podaje problemu, mechanizmu lub wyników, wpisz "" w odpowiednie pole.
Przy zwykłym ogłoszeniu wypełnij title, summary i keywords, a problem, solution i results zostaw puste.
keywords: do sześciu haseł ze źródła.
questions: lista od zera do trzech różnych pytań do twórcy. W każdym nazwij czynność, element rozwiązania lub odbiorców ze źródła
i zapytaj o jedną rzecz, której opis nie wyjaśnia. Jeśli wynik jest podany, można zapytać o sposób pomiaru lub okres obserwacji.
Przykład: dla „Od marca wypożyczamy wiertarki na kartę” zapytaj „Ile wiertarek wypożyczono od marca?”.
Pomiń pytania ogólne, pytania z odpowiedzią w źródle i pytania o zakończone wdrożenie w przypadku planu.
Dla ogłoszenia albo gdy nie ma konkretnej luki, zwróć []."""

FOLLOW_UP_PROMPT = """Jesteś brokerem innowacji. Zadaj autorowi jedno konkretne pytanie po polsku.
W pytaniu nazwij mechanizm lub odbiorców z opisu i poproś o szczegół, którego brakuje.
Jeśli opis podaje skuteczność, możesz zapytać, jak ją obliczono. Przy planie pytaj o planowany sposób działania.
Przykład pytania: Jak długo czytelnicy biblioteki mogą zatrzymać wypożyczone wiertarki?"""
FOLLOW_UP_SCHEMA = {
    "type": "object",
    "properties": {"question": {"type": "string", "minLength": 18, "maxLength": 180}},
    "required": ["question"],
    "additionalProperties": False,
}

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
SOURCE_BREAK = re.compile(
    r"(?<=[.!?])\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ„])|[\n;]+"
    r"|(?:,\s*|\s+)(?:a|ale|i|zaś)\s+(?=(?:\w+\s+){0,2}(?:planuj|chcemy|zamierza|docelowo|będzie))"
)
QUANTITY = re.compile(
    r"\d|\b(?:połow\w*|ćwier[ćc]\w*|jedn(?:a|ą|ej)\s+trzeci\w*|"
    r"dwie\s+trzeci\w*|pię[ćc]\w*|sześć|siedem|osiem|dziewięć|dziesięć|sto|tysiąc\w*|"
    r"dwa|dwie|dwóch|dwu|trzy|trzech|cztery|czterech|\w+naście|\w+nastu|"
    r"\w+dziesiąt|\w+set|milion\w*|miliard\w*)\b",
    re.I,
)
PROBLEM_CUE = re.compile(
    r"\b(?:wcześniej|dotąd|przed wdrożeniem|problemem był\w*|problem polegał|"
    r"musieli\w*|mieli\w* trudności|bał\w* się|długo czeka(?:li|ły|ła|ł|no) na)\b",
    re.I,
)
MECHANISM_CUE = re.compile(
    r"\b(?:wprowadz|uruchom|wdroż|wypożycz|prowadzą|rezerwuj|utworzy|zbudowa|opracowa|"
    r"zastosow|wykorzyst|koryguj|umożliwia|wyposaży|działa|służy)\w*\b",
    re.I,
)
RESULT_CUE = re.compile(
    r"\b(?:spadł\w*|wzr[oó]s\w*|zmalał\w*|zwiększył\w*|zmniejszył\w*|"
    r"skrócił\w*|wydłużył\w*|obniżył\w*|utrzymał\w*|nie zmienił\w*|"
    r"odnotowali\w*|odnotowano|zaobserwowano|wykazał\w*|uzyskano|osiągnięto|"
    r"zaobserwowali\w*|uzyskali\w*|osiągnęli\w*)\b",
    re.I,
)
FUTURE_CUE = re.compile(
    r"\b(?:planuj\w*|planowan\w*|chcemy|zamierza\w*|cel(?:em)? (?:\w+ ){0,2}(?:jest|będzie)|"
    r"cel(?: \w+){0,3}:|"
    r"docelowo|w przyszłości|"
    r"oczekuj\w*|przewiduj\w*|spodziewa\w*|powinn\w*|miałby|mogłoby|"
    r"będzie|będą|ma\w* (?:zmniejsz|zwiększ|skróci|obniż|poprawi|spaś|wzros|wynosi)\w*)(?=\W|$)",
    re.I,
)
NO_RESULT_CUE = re.compile(
    r"\b(?:nie (?:ma jeszcze|zebrano|zmierzono|badano|oceniono|znamy|mierzyli\w*|"
    r"uzyskano (?:danych|wyników))|"
    r"brak (?:danych|wyników|pomiarów))\b",
    re.I,
)
GENERIC_QUESTION = re.compile(
    r"^(?:czy (?:możesz|możecie|mógłbyś|moglibyście)\b|podaj(?:cie)? więcej\b|"
    r"na czym polega\b|co było problemem\b|jakiego wsparcia potrzebujecie\b|jak (?:dokładnie )?działa\b)",
    re.I,
)
QUESTION_STOP_WORDS = {
    "było", "były", "jakie", "jaki", "który", "które", "których", "oraz", "kiedy", "przez",
    "przed", "tylko", "około", "bardzo", "jest", "jego", "tego", "opis", "wynik", "efekt",
    "rozwi", "proje", "wdroż", "pilot", "możli", "korzy", "wpływ", "dział", "użytk", "osoby",
}


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


def _segments(text: str) -> list[str]:
    text = re.sub(r":[ \t]*\n\s*", ": ", text)
    return [" ".join(segment.split()) for segment in SOURCE_BREAK.split(text) if segment.strip()]


def _quote(proposal: str, source: str) -> str:
    phrase = proposal.strip(' „”".!?,;:')
    if not phrase:
        return ""
    match = re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", source, re.I)
    return match.group() if match else ""


def _collect_segments(segments: list[str], limit: int) -> str:
    # Skracanie cytatu w połowie może odciąć jednostkę lub punkt odniesienia.
    selected = []
    remaining = limit
    for segment in segments:
        if segment and len(segment) <= remaining:
            selected.append(segment)
            remaining -= len(segment) + 1
    return " ".join(selected)


def _observed_results(proposal: str, segments: list[str]) -> str:
    quotes = [part for part in _segments(proposal) if len(part.split()) >= 3]
    evidence = [
        segment for segment in segments
        if not FUTURE_CUE.search(segment)
        and not NO_RESULT_CUE.search(segment)
        and (
            (RESULT_CUE.search(segment) and not PROBLEM_CUE.search(segment))
            or any(_quote(quote, segment) for quote in quotes)
        )
    ]
    return _collect_segments(evidence, TEXT_LIMITS["results"])


def _grounded_prose(proposal: str, source: str, limit: int) -> str:
    return _collect_segments(
        [segment for segment in _segments(proposal) if not QUANTITY.search(segment) or _quote(segment, source)],
        limit,
    )


def _anchor_words(text: str) -> set[str]:
    return {
        word[:5] for word in re.findall(r"[^\W\d_]{4,}", text.casefold())
        if word[:5] not in QUESTION_STOP_WORDS
    }


def _follow_up(raw: object, source: str, card: dict) -> list[str]:
    if not isinstance(raw, list) or not card["solution"]:
        return []
    source_words = [_anchor_words(segment) for segment in _segments(source)]
    anchors = set().union(*source_words)
    questions = []
    seen = set()
    for proposal in raw:
        question = _clean(proposal, 180)
        key = question.casefold()
        words = _anchor_words(question)
        if (
            not question.endswith("?")
            or question.count("?") != 1
            or len(question.split()) < 4
            or GENERIC_QUESTION.match(question)
            or key in seen
            or not anchors.intersection(words)
            or (key.startswith("czy ") and any(words <= part for part in source_words))
        ):
            continue
        questions.append(question)
        seen.add(key)
        if len(questions) == 3:
            break
    return questions


def _ask_follow_up(draft: dict, source: str, card: dict) -> list[str]:
    questions = _follow_up(draft.get("questions"), source, card)
    if questions or not card["solution"]:
        return questions
    try:
        follow_up = llm.chat_json(FOLLOW_UP_PROMPT, source, FOLLOW_UP_SCHEMA, temperature=0)
    except llm.LLMUnavailable:
        return []
    proposal = follow_up.get("question") if isinstance(follow_up, dict) else None
    return _follow_up([proposal], source, card)


def structure_text(text: str) -> dict:
    """Buduje propozycję karty dla formularza i radaru. Rzuca LLMUnavailable przy awarii modelu."""
    excerpt = _source_excerpt(text)
    answers = decisions.decide(excerpt, QUESTIONS)
    draft = llm.chat_json(SYSTEM_PROMPT, excerpt, TEXT_SCHEMA, temperature=0)
    if not isinstance(draft, dict):
        raise llm.LLMUnavailable("Model językowy nie zwrócił karty.")

    tags = _extract_tags(answers)
    card = {field: _clean(draft.get(field), limit) for field, limit in TEXT_LIMITS.items()}
    segments = _segments(excerpt)
    source = " ".join(excerpt.split())
    card["problem"] = next(
        (part for part in segments if len(part) <= TEXT_LIMITS["problem"] and PROBLEM_CUE.search(part)),
        _quote(card["problem"], source),
    )
    mechanism = next(
        (
            part for part in segments
            if len(part) <= TEXT_LIMITS["solution"] and MECHANISM_CUE.search(part)
            and not RESULT_CUE.search(part) and not PROBLEM_CUE.search(part)
        ),
        "",
    )
    card["results"] = _observed_results(card["results"], segments)
    if mechanism:
        targets = [
            part for part in segments if part != mechanism and QUANTITY.search(part)
            and FUTURE_CUE.search(part) and not NO_RESULT_CUE.search(part)
        ]
        card["solution"] = _collect_segments([mechanism, *targets], TEXT_LIMITS["solution"])
        if FUTURE_CUE.search(mechanism):
            card["summary"] = mechanism
    else:
        card["solution"] = _grounded_prose(card["solution"], source, TEXT_LIMITS["solution"])
    summary = _grounded_prose(card["summary"], source, TEXT_LIMITS["summary"])
    if not summary or len(summary) < len(card["summary"]):
        opening = summary or card["solution"] or (segments[0] if segments else "")
        summary = _collect_segments(
            [opening, *_segments(card["results"])], TEXT_LIMITS["summary"]
        )
        summary = summary or _clean(opening, TEXT_LIMITS["summary"])
    card["summary"] = summary
    if QUANTITY.search(card["title"]) and not _quote(card["title"], source):
        card["title"] = ""
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
        "is_innovation": _probability(innovation.get("noul")),
        "missing": missing,
        "questions": _ask_follow_up(draft, excerpt, card),
        "version": STRUCTURING_VERSION,
        "engine": {
            "tags": innovation.get("engine") or answers.get("kind", {}).get("engine", ""),
            "text": current_app.config["LLM_MODEL"],
        },
    }
