from .. import domain

WEIGHTS = {
    "profile": {"content": 35, "areas": 18, "need": 14, "stage": 24, "potential": 6, "freshness": 2, "activity": 1},
    "query": {"content": 70, "areas": 11, "need": 7, "stage": 4, "potential": 5, "freshness": 2, "activity": 1},
}
SIGNALS = {
    "content": "Zgodność treści",
    "areas": "Wspólne obszary",
    "need": "Potrzeby twórców",
    "stage": "Dopasowanie etapu",
    "potential": "Potencjał",
    "freshness": "Czas od dodania",
    "activity": "Ostatnia aktywność",
}
SIMILARITY_LOW = 0.40
SIMILARITY_HIGH = 0.65
QUERY_MATCH_MIN = 0.50
QUERY_VECTOR_WEIGHT = 0.55
FRESHNESS_HALF_LIFE_DAYS = 30

NEED_FIT = {
    "inwestor": ("finansowanie",),
    "jst": ("pierwszy_uzytkownik", "partner_wdrozeniowy"),
    "szkola": ("pierwszy_uzytkownik", "partner_wdrozeniowy"),
    "firma": ("zespol",),
}
STAGE_FIT = {
    "jst": {"wdrozona": 1.0, "skalowana": 1.0, "pilotaz": 0.4},
    "inwestor": {"prototyp": 0.70, "pilotaz": 1.0},
    "szkola": {"pilotaz": 1.0, "wdrozona": 0.9, "skalowana": 0.9},
}
BROKER_PENDING = ("wykryta", "zgloszona", "oceniona")
NEED_REASONS = {
    "finansowanie": "Twórcy szukają finansowania.",
    "pierwszy_uzytkownik": "Twórcy szukają pierwszego użytkownika.",
    "partner_wdrozeniowy": "Twórcy szukają partnera wdrożeniowego.",
    "zespol": "Twórcy szukają ludzi do zespołu.",
}

POPULAR_WEIGHTS = {"podbicie": 3, "zainteresowany": 2, "komentarz": 2, "obserwuje": 1}
POPULAR_LABELS = {
    "podbicie": "Podbicie",
    "zainteresowany": "Zainteresowanie",
    "komentarz": "Komentarz",
    "obserwuje": "Obserwowanie",
}
POPULAR_DAYS = 14
POPULAR_HALF_LIFE_DAYS = 7
PERSONAL_ACTIVITY_CAP = 6

GEM_MIN_COMPARABLE = 3
GEM_MAX_ATTENTION = 2
GEM_EMPTY_IN_SCOPE = "W tym zestawie nie ma mało zauważonych wdrożeń ani prób spełniających kryteria."
GEM_EMPTY = (
    f"Potrzeba co najmniej {GEM_MIN_COMPARABLE} udokumentowanych kart z oceną dopuszczoną do rankingu "
    f"i przynajmniej jednej z najwyżej {GEM_MAX_ATTENTION} publicznymi interakcjami."
)


def explain() -> list[dict]:
    role_rules = [
        f"{domain.ORG_KINDS[kind]} — " + ", ".join(domain.SUPPORT_NEEDS[need].lower() for need in needs) + "."
        for kind, needs in NEED_FIT.items()
    ]
    stage_rules = [
        f"{domain.ORG_KINDS[kind]} — " + ", ".join(
            f"{domain.STAGES[stage].lower()} ({fit:.0%})" for stage, fit in stages.items()
        ) + "."
        for kind, stages in STAGE_FIT.items()
    ]
    return [
        {
            "title": "Dla Ciebie · rekomendacje z profilu (100%)",
            "lines": [
                f"{label} — {WEIGHTS['profile'][key]}%."
                for key, label in SIGNALS.items()
            ] + [
                "Uwzględniamy obszary Twoje i Twojej organizacji. Te wybrane przez Ciebie liczą się mocniej.",
                "Przy dopasowaniu do profilu wpisy Twojej organizacji trafiają za pozostałe.",
                f"Przeskalowujemy podobieństwo treści. {SIMILARITY_LOW:.2f} daje 0, a {SIMILARITY_HIGH:.2f} daje 1.",
                f"Przy wyszukiwaniu zgodność treści łączy podobieństwo ({QUERY_VECTOR_WEIGHT:.0%}) "
                f"i słowa z tytułu oraz opisu ({1 - QUERY_VECTOR_WEIGHT:.0%}).",
                f"Za datę dodania wpis dostaje o połowę mniej punktów po {FRESHNESS_HALF_LIFE_DAYS} dniach.",
            ],
        },
        {
            "title": "Dla Ciebie · po wpisaniu zapytania (100%)",
            "lines": [f"{label} — {WEIGHTS['query'][key]}%." for key, label in SIGNALS.items()],
        },
        {
            "title": "Rola i potrzeby twórców",
            "lines": role_rules + [
                "Broker — wpisy oczekujące na decyzję: "
                + ", ".join(domain.STATUSES[status].lower() for status in BROKER_PENDING) + ".",
            ],
        },
        {"title": "Dopasowanie etapu", "lines": stage_rules},
        {
            "title": "Ukryte perełki",
            "lines": [
                "Porównujemy aktywne, rzeczywiste karty z publicznym źródłem i oceną dopuszczoną do rankingu "
                "według bieżących kryteriów.",
                "Wymagamy zweryfikowanej informacji ze źródła albo cytatu z wyników, który w ocenie potwierdza "
                "przeprowadzoną próbę lub użycie.",
                f"W całej bazie muszą być co najmniej {GEM_MIN_COMPARABLE} takie karty. "
                f"Pokazujemy te z najwyżej {GEM_MAX_ATTENTION} publicznymi interakcjami.",
                "Liczymy podbicia, zainteresowania, komentarze i obserwowania od dodania karty.",
                "Najpierw pokazujemy karty z mniejszą liczbą interakcji, następnie z wyższą oceną potencjału "
                "i nowszą datą dodania. Filtry zawężają tę listę.",
            ],
        },
        {
            "title": "Popularne",
            "lines": [
                f"Zliczamy aktywność z ostatnich {POPULAR_DAYS} dni. "
                f"Po {POPULAR_HALF_LIFE_DAYS} dniach akcja daje połowę punktów.",
                ", ".join(f"{POPULAR_LABELS[key]} — {weight} pkt" for key, weight in POPULAR_WEIGHTS.items()) + ".",
            ],
        },
        {"title": "Najnowsze", "lines": ["Najpierw pokazujemy ostatnio dodane wpisy."]},
    ]
