"""Słowniki domenowe: jedno źródło prawdy dla backendu i frontu (GET /api/meta).

Klucze są stabilne (trafiają do bazy), etykiety są do wyświetlania.
Kolejność w STAGES i STATUSES ma znaczenie: to kolejne kroki.
"""

INNOVATION_KINDS = {
    "technologiczna": "Technologiczna",
    "organizacyjna": "Organizacyjna",
    "edukacyjna": "Edukacyjna",
    "spoleczna": "Społeczna",
    "procesowa": "Procesowa",
}

STAGES = {
    "pomysl": "Pomysł",
    "prototyp": "Prototyp",
    "pilotaz": "Pilotaż",
    "wdrozona": "Wdrożona lokalnie",
    "skalowana": "Skalowana",
}

ORG_KINDS = {
    "szkola": "Szkoła",
    "uczelnia": "Uczelnia",
    "jst": "Samorząd",
    "instytucja_publiczna": "Instytucja publiczna",
    "iob": "Instytucja otoczenia biznesu",
    "firma": "Firma",
    "inwestor": "Inwestor",
    "ngo": "Organizacja pozarządowa",
}

DOMAINS = {
    "edukacja": "Edukacja",
    "zdrowie": "Zdrowie",
    "jakosc_zycia": "Jakość życia",
    "cyfryzacja_ict": "Cyfryzacja i ICT",
    "energia_srodowisko": "Energia i środowisko",
    "transport_mobilnosc": "Transport i mobilność",
    "motoryzacja": "Motoryzacja",
    "lotnictwo_kosmos": "Lotnictwo i kosmos",
    "przemysl": "Przemysł",
    "rolnictwo_zywnosc": "Rolnictwo i żywność",
    "administracja": "Administracja i usługi publiczne",
    "kultura": "Kultura",
    "bezpieczenstwo": "Bezpieczeństwo",
}

# Czego twórcy potrzebują, żeby pójść dalej.
SUPPORT_NEEDS = {
    "partner_wdrozeniowy": "Partner wdrożeniowy",
    "pierwszy_uzytkownik": "Pierwszy użytkownik",
    "finansowanie": "Finansowanie",
    "mentoring": "Mentoring",
    "ochrona_ip": "Ochrona własności intelektualnej",
    "zespol": "Ludzie do zespołu",
    "promocja": "Promocja",
}

# Skąd rekord trafił do systemu.
ORIGINS = {
    "zgloszenie": "Zgłoszenie",
    "radar": "Wykryta przez radar",
}

# Co dzieje się z innowacją po jej zidentyfikowaniu.
STATUSES = {
    "wykryta": "Wykryta",
    "zgloszona": "Zgłoszona",
    "oceniona": "Oceniona",
    "skierowana": "Skierowana na ścieżkę",
    "w_kontakcie": "W kontakcie z partnerem",
    "wdrazana": "Wdrażana",
    "archiwum": "Archiwum",
}

PATHS = {
    "rozwoj": "Dalszy rozwój",
    "transfer": "Transfer technologii",
    "komercjalizacja": "Komercjalizacja",
    "wdrozenie": "Wdrożenie w innej organizacji",
}

USER_ROLES = {
    "tworca": "Twórca innowacji",
    "broker": "Koordynator innowacji",
    "poszukujacy": "Poszukujący rozwiązań",
}

MATCH_STATUSES = {
    "proponowane": "Proponowane",
    "zainteresowanie": "Zainteresowanie",
    "kontakt": "Kontakt nawiązany",
    "odrzucone": "Odrzucone",
}


def as_meta() -> dict:
    def items(d: dict) -> list[dict]:
        return [{"key": k, "label": v} for k, v in d.items()]

    return {
        "innovation_kinds": items(INNOVATION_KINDS),
        "stages": items(STAGES),
        "org_kinds": items(ORG_KINDS),
        "domains": items(DOMAINS),
        "support_needs": items(SUPPORT_NEEDS),
        "origins": items(ORIGINS),
        "statuses": items(STATUSES),
        "paths": items(PATHS),
        "user_roles": items(USER_ROLES),
        "match_statuses": items(MATCH_STATUSES),
    }
