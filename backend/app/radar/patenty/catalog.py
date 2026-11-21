"""Small reviewable selection of publications and original Polish card summaries."""

from dataclasses import dataclass

UPRP = "uprp_bup"
EPO = "epo_eps"
SOURCES = (UPRP, EPO)

BUP_BASE = "https://uprp.gov.pl/sites/default/files/bup"
BUP_2025_48 = f"{BUP_BASE}/2025/Wynalazki%20i%20wzory%20u%C5%BCytkowe/12_48-52/48/bup48_2025.pdf"
BUP_2024_53 = f"{BUP_BASE}/2024/Wynalazki%20i%20wzory%20u%C5%BCytkowe/12_49-53/53/bup53_2024.pdf"
BUP_2016_14 = f"{BUP_BASE}/2016/14/bup14_2016.pdf"
EPS_BASE = "https://data.epo.org/publication-server/rest/v1.2/patents"

AGH = "Akademia Górniczo-Hutnicza im. Stanisława Staszica w Krakowie"
AWF = "Akademia Wychowania Fizycznego im. Eugeniusza Piaseckiego w Poznaniu"
GDANSK = "Politechnika Gdańska"
SILESIA = "Politechnika Śląska"
LODZ = "Politechnika Łódzka"
LUBLIN = "Politechnika Lubelska"
LUBLIN_ULS = "Uniwersytet Przyrodniczy w Lublinie"
LUKASIEWICZ = "Sieć Badawcza Łukasiewicz – Instytut Metali Nieżelaznych"
ENV = "energia_srodowisko"
HEALTH = "zdrowie"
INDUSTRY = "przemysl"


@dataclass(frozen=True)
class Selection:
    organizations: tuple[str, ...]
    title_marker: str
    title: str
    summary: str
    domains: tuple[str, ...]
    broker_note: str = ""


SOIL = Selection(
    (LUBLIN, LUBLIN_ULS), "gleby lekkiej", "Zagospodarowanie osadu ściekowego do poprawy gleb lekkich",
    "Zgłoszenie opisuje wykorzystanie przefermentowanego osadu z oczyszczalni komunalnej "
    "razem z mineralnym odpadem z płukania piasku kwarcowego w materiale do poprawy lekkiej gleby.",
    (ENV, "rolnictwo_zywnosc"),
    "Trop dla operatora komunalnej oczyszczalni szukającego zastosowania dla osadu.",
)
OZONE = Selection(
    (LODZ,), "kolumna barbotażowa", "Kolumna do ozonowania ścieków włókienniczych",
    "W kolumnie ścieki i ozon kontaktują się z metalowymi siatkami pokrytymi cienką warstwą katalizatora.",
    (ENV, INDUSTRY),
    "Trop dla oczyszczalni przyjmującej ścieki z zakładów tekstylnych. "
    "Przed rozmową o pilotażu warto ustalić skuteczność i koszty dla własnego strumienia ścieków.",
)
WATER = Selection(
    (SILESIA,), "water power plant", "Turbina wykorzystująca różnice temperatury i zasolenia wody",
    "Turbina w zanurzonym przewodzie ma wykorzystywać przepływ wynikający z różnic "
    "temperatury lub zasolenia między głębokościami.",
    (ENV,),
)
POLYMER = Selection(
    (GDANSK,), "thermoplastic polymer", "Kompostowalne tworzywo termoplastyczne do jednorazowych wyrobów",
    "Opis dotyczy tworzywa z polilaktydu i zmodyfikowanej skrobi. "
    "Wskazane zastosowanie to produkcja wyrobów jednorazowych.",
    (ENV, INDUSTRY),
)
BUP = {
    BUP_2025_48: {
        "PL448718A1": Selection(
            (AWF,), "ruchu kręgów kręgosłupa", "Pomiar ruchu kręgów odcinka lędźwiowo-krzyżowego",
            "Zestaw połączonych czujników żyroskopowych śledzi ruch na poziomach L1–S1.",
            (HEALTH,),
            "Materiał powiązany z potrzebą Radaru „Projekty sprzętowe po pierwszych testach terenowych”. "
            "Broker może zapytać zespół o prototyp, walidację pomiaru i próby z użytkownikami.",
        ),
        "PL448713A1": Selection(
            (GDANSK,), "napowietrzania zbiorników", "Wiatrowe napowietrzanie zbiorników wodnych",
            "Na pływającej platformie wirniki wiatrowe napędzają sprężarkę dostarczającą powietrze do dyfuzora.",
            (ENV,), "Trop dla zarządców stawów i zbiorników szukających sposobu na niedotlenienie wody.",
        ),
        "PL132167U1": Selection(
            ("Politechnika Poznańska", AWF), "pomiaru siły zacisku", "Pomiar siły zacisku szczęki i żuchwy",
            "Sprężyste elementy pomiarowe z tensometrami mają mierzyć siłę zacisku.",
            (HEALTH,),
        ),
        "PL448742A1": Selection(
            (LUKASIEWICZ, SILESIA), "rozdziału metali szlachetnych", "Odzysk metali szlachetnych z roztworu",
            "Zgłoszony proces rozdziela metale szlachetne na osobne koncentraty i osady. "
            "Wśród wymienionych metali są złoto, pallad, platyna i rod.",
            (INDUSTRY, ENV),
        ),
    },
    BUP_2024_53: {"PL445362A1": OZONE},
    BUP_2016_14: {"PL410744A1": SOIL},
}
EPS = {
    "EP4678091A1": Selection(
        (AGH,), "monitoring health status", "Monitorowanie parametrów zdrowotnych za pomocą okularów AR",
        "System analizuje razem sygnały z okularów i z niezależnych czujników w pobliżu ciała osoby badanej. "
        "Okulary mogą pokazywać instrukcje podczas pomiaru.",
        (HEALTH, "cyfryzacja_ict"),
        "Materiał powiązany z potrzebą Radaru „Projekty sprzętowe po pierwszych testach terenowych”. "
        "Przed zgłoszeniem inwestorowi broker może sprawdzić stan prototypu i wyniki dotychczasowych prób.",
    ),
    "EP4484383A1": Selection(OZONE.organizations, "bubble column", OZONE.title,
                             OZONE.summary, OZONE.domains, OZONE.broker_note),
    "EP3037500A1": Selection(SOIL.organizations, "light soil", SOIL.title,
                             SOIL.summary, SOIL.domains, SOIL.broker_note),
    "EP3907399A1": WATER,
    "EP3907399B1": WATER,
    "EP3064542A1": POLYMER,
    "EP3064542B1": POLYMER,
}
