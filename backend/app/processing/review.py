import re

from ..services import decisions, structuring

VERSION = "t13-2"
MAX_INNOVATION = 0.65
MIN_RESEARCH = 0.60
MIN_SCIENTIFIC = 0.40
MIN_ACCEPT = 0.70

CLASSIFY = {
    "type": "choice",
    "instructions": (
        "Oceniaj cały podany materiał rejestru projektów. Co faktycznie jest zamierzonym wynikiem projektu? "
        "Jeżeli jest określony praktyczny odbiorca, zastosowanie lub prototyp do takiego użycia, "
        "wybierz zastosowanie nawet wtedy, gdy projekt to dopiero badania. Nowa metoda służąca "
        "wyłącznie badaniu zjawiska dla samej nauki pasuje do badań podstawowych. "
        "Jeżeli brak rozstrzygającej informacji, wybierz niejasne."
    ),
    "criteria": {
        "badania": "Opis zawiera konkretny cel poznawczy lub wyłącznie badawczą metodę do badania zjawiska i nie podaje praktycznego zastosowania.",
        "zastosowanie": "Wskazano choćby plan konkretnego praktycznego zastosowania produktu, metody, usługi lub zmiany społecznej.",
        "niejasne": "Opis jest ogólny, za krótki lub zawiera niejednoznaczne informacje do klasyfikacji.",
    },
}

PRACTICAL_USE = {
    "type": "choice",
    "instructions": (
        "Wybierz czy opis podaje choć jedno konkretne zastosowanie praktyczne albo test interwencji z odbiorcami. "
        "Nazwany pomiar zjawiska, metoda badawcza stosowana wyłącznie w astronomii lub innej nauce i eksperyment "
        "bez praktycznego celu nie są zastosowaniami praktycznymi. Samo zapewnienie, że kiedyś wyniki mogą pomóc "
        "jakiejś grupie, to opis niejednoznaczny."
    ),
    "criteria": {
        "praktyczne": "Jest plan lub opis praktycznej interwencji, na przykład test leczenia u pacjentów, narzędzia w organizacji lub zmiany procesu.",
        "naukowe": "Jest konkretny cel poznawczy lub nowa metoda badawcza służąca wyłącznie obserwacji albo wyjaśnieniu zjawiska.",
        "niejasne": "Jest wzmianka o możliwym wykorzystaniu w przyszłości lub materiał nie pozwala wykluczyć konkretnego praktycznego zastosowania.",
    },
}


def research_evidence(title: str, description: str) -> dict:
    # Cytat wybieramy wyłącznie z opisu, a skrócony materiał nie jest podstawą archiwizacji.
    normalized = " ".join(description.split())
    excerpt = structuring._source_excerpt(normalized)
    if excerpt != normalized:
        return {"limited": True}
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ„])", excerpt)
    passages = [part for part in sentences if 35 <= len(part) <= 360][:12]
    choices = {str(index): part for index, part in enumerate(passages, 1)}
    if not choices:
        return {}
    answers = decisions.decide(f"{title}\n{excerpt}", {
        "classification": CLASSIFY,
        "practical_use": PRACTICAL_USE,
        "evidence": {
            "type": "choice",
            "instructions": (
                "Wybierz dosłowny fragment, który jawnie określa cel poznawczy "
                "lub metodę badania zjawiska w tym projekcie. Pomiń tło, cudze badania i ogólne opisy. "
                "Jeśli brak takiego fragmentu, wybierz brak dowodu."
            ),
            "criteria": {**choices, "none": "Brak dowodu wśród fragmentów."},
        },
    })
    classification = answers.get("classification", {})
    application = answers.get("practical_use", {})
    evidence = answers.get("evidence", {})
    quote = choices.get(evidence.get("choice"))
    if quote:
        index = sentences.index(quote)
        context = " ".join(sentences[max(0, index - 1):index + 2])
        if len(context) <= 700:
            quote = context
    return {
        "classification": classification.get("choice"),
        "probability": (classification.get("probabilities") or {}).get("badania"),
        "practical_use": application.get("choice"),
        "scientific_probability": (application.get("probabilities") or {}).get("naukowe"),
        "quote": quote,
        "engine": classification.get("engine"),
        "calibrated": classification.get("calibrated") is True and application.get("calibrated") is True,
    }


def evaluate(innovation, protected: bool) -> dict:
    raw = innovation.raw or {}
    probability = structuring._probability(raw.get("is_innovation"))
    engines = raw.get("structuring_engine")
    signal = {
        "is_innovation": probability,
        "engine": engines.get("tags") if isinstance(engines, dict) else None,
        "max_innovation": MAX_INNOVATION,
        "min_research": MIN_RESEARCH,
        "min_scientific": MIN_SCIENTIFIC,
    }
    result = {"version": VERSION, "signal": signal}

    if protected:
        return {**result, "decision": "chroniona", "reason": "Karta potwierdzona lub z udokumentowaną decyzją człowieka."}
    if probability is None:
        return {**result, "decision": "przeglad", "reason": "Brak miarodajnego sygnału strukturyzacji."}
    if probability >= MIN_ACCEPT:
        return {**result, "decision": "pozostawiona", "reason": "Sygnał konkretnego zastosowania."}
    if probability <= MAX_INNOVATION and innovation.description and (signal["engine"] or "").startswith("basal-serve"):
        research = research_evidence(innovation.title, innovation.description)
        signal["research"] = research
        if (
            research.get("classification") == "badania" and research.get("calibrated") and research.get("quote")
            and (structuring._probability(research.get("probability")) or 0) >= MIN_RESEARCH
            and research.get("practical_use") == "naukowe"
            and (structuring._probability(research.get("scientific_probability")) or 0) >= MIN_SCIENTIFIC
        ):
            return {
                **result, "decision": "odrzucona",
                "reason": "Materiał źródłowy wskazuje wyłącznie cel poznawczy bez konkretnego praktycznego zastosowania.",
            }
    return {**result, "decision": "przeglad", "reason": "Brak wystarczającego dowodu do automatycznej decyzji."}
