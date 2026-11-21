---
name: Radar Innowacji
description: "Jasny, redakcyjny interfejs do odkrywania innowacji publicznych."
colors:
  primary: "#b31335"
  primary-deep: "#921029"
  primary-active: "#ce2748"
  primary-soft: "#fbecef"
  canvas: "#f9f8f6"
  surface: "#fff"
  neutral-hover: "#f8f7f5"
  neutral-soft: "#f1eeeb"
  text: "#1b1719"
  text-secondary: "#40373a"
  text-muted: "#6b6062"
  divider: "#ddd7d4"
  control: "#8d8586"
  warning-bg: "#fcf2df"
  warning-text: "#794709"
  success-bg: "#e7f3ec"
  success-text: "#275e45"
  error-bg: "#fbe9ed"
  error-text: "#9d1835"
  origin-bg: "#efedf5"
  origin-text: "#52436c"
typography:
  display:
    fontFamily: "Barlow Condensed, Arial Narrow, sans-serif"
    fontSize: "4.75rem"
    fontWeight: 700
    lineHeight: 0.93
    letterSpacing: "-0.025em"
  headline:
    fontFamily: "Barlow Condensed, Arial Narrow, sans-serif"
    fontSize: "3rem"
    fontWeight: 600
    lineHeight: 0.98
    letterSpacing: "-0.025em"
  title:
    fontFamily: "Barlow Condensed, Arial Narrow, sans-serif"
    fontSize: "2rem"
    fontWeight: 700
    lineHeight: 1.02
  body:
    fontFamily: "Source Sans 3, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Source Sans 3, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.333333
    letterSpacing: "0.1em"
rounded:
  control: "4px"
  card: "12px"
  avatar: "9999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
  xxl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "8px 16px"
  button-primary-hover:
    backgroundColor: "{colors.primary-deep}"
  button-primary-active:
    backgroundColor: "{colors.primary-active}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "8px 16px"
  button-ghost:
    textColor: "{colors.text-secondary}"
    rounded: "{rounded.control}"
    padding: "8px 16px"
  input:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.text}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
  chip:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-secondary}"
    rounded: "{rounded.control}"
    padding: "4px 12px"
  chip-selected:
    backgroundColor: "{colors.primary-soft}"
    textColor: "{colors.primary-deep}"
  navigation-link-active:
    textColor: "{colors.primary-deep}"
    height: "44px"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.card}"
  feed-post:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.card}"
    padding: "16px 16px 12px"
  featured-innovation:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.card}"
---

# Design System: Radar Innowacji

## Overview

**Creative North Star: "Redakcja innowacji publicznych"**

Czerwony nagłówek, jasne tło i zwarta typografia nadają Radarowi charakter publikacji. Białe karty i cienkie linie porządkują treść i działania.

Feed prowadzi od osoby lub instytucji do rozwiązania, dowodu i rozmowy. Jawne pochodzenie i uzasadnienia ułatwiają ocenę pomysłów, które można zastosować w kolejnych instytucjach.

**Key Characteristics**

- Czerwony nagłówek i ciemne liternictwo na jasnym tle.
- Strumień wpisów z widocznym pochodzeniem, oceną i akcjami.
- Oszczędne linie, czytelne stany i natywne pola.

## Colors

### Primary

- **Redakcyjna czerwień** wypełnia nagłówek i przycisk główny. Głębsza czerwień wyróżnia aktywne zakładki, linki i liczby. Jasny róż podkłada tło ikonom autorów i wybranym filtrom.

### Tertiary

- Bursztyn sygnalizuje ostrzeżenie, zieleń potwierdzenie, róż błąd, a przygaszony fiolet etykietę pochodzenia z radaru. Tekst nazywa znaczenie stanu.

### Neutral

- **Ciepły papier** jest tłem aplikacji, a biel wyznacza karty i nawigację. Ciemny druk służy nagłówkom i treści. Ton przygaszony opisuje daty, źródła oraz taksonomię.
- **Podział i obrys** mają osobne odcienie. Cienki podział rozdziela treść, a wyraźniejszy obrys wskazuje granicę pola.

## Typography

Barlow Condensed (600 i 700) prowadzi nagłówki i duże liczby, a Source Sans 3 (400–700) obsługuje treść, metadane i formularze. Obie rodziny korzystają z lokalnych WOFF2 w wariantach Latin i Latin Extended. Licencje SIL OFL są w `frontend/public/fonts`.

- **Display** (700, 2.4–4.75rem, interlinia .93) otwiera feed.
- **Headline** (600, 3–3.75rem, interlinia .98) prowadzi pozostałe strony. **Title** (700, 1.85–2rem, interlinia ok. 1) należy do tytułów wpisów i wyróżnień.
- **Body** (1rem) prowadzi opis, a metadane i akcje używają 0.875rem. Etykiety techniczne mają 0.75rem i zwiększony odstęp liter. Liczniki i oceny używają cyfr tabelarycznych.

## Layout

Nagłówek i główna treść trzymają wspólną szerokość do 78rem. Boczne odstępy wynoszą 16px, 32px od 640px i 40px od 1024px. Nawigacja i przełącznik person mieszczą się w mobilnym nagłówku z menu.

Feed ma jeden strumień wpisów z odstępem 12px. Od 1024px obok niego stoi przypięty panel wdrożenia o szerokości 20rem, rosnącej do 22rem od 1280px. W węższym układzie wyszukiwarka, przykład wdrożenia wraz z linkiem do zapotrzebowań oraz widoki i wpisy tworzą kolejkę czytania. Szczegóły kompozycji są w [briefie feedu](.impeccable/surfaces/frontend-src-pages-feed-tsx.md).

## Elevation & Depth

Biel kart na ciepłym tle i cienki obrys wyznaczają granice. Stopki mają podział, a w karcie wyróżnionej dodatkowo lekko tonowane tło. Karty i nagłówek są płaskie. Ruch ogranicza się do krótkich przejść stanu i obrotu strzałki rozwijania. Ustawienie ograniczenia ruchu wyłącza animacje, przejścia i płynne przewijanie.

## Shapes

Kontrolki mają mały promień (4px), karty łagodniejszy (12px), a ikony autorów okrągłe tło (40px średnicy w feedzie). Ikona radaru w nagłówku jest zamknięta w kwadratowej ramce. Pole tekstowe i przycisk wyszukiwania tworzą jeden zespół dzięki prostym krawędziom wewnętrznym.

## Components

- **Przyciski i pola.** Główne działanie ma białą etykietę na czerwieni. Wariant dodatkowy ma wyraźną granicę na bieli, a oszczędny wariant tekstowy zyskuje tło po najechaniu. Pola, filtry i przełącznik person zachowują natywne kontrolki i etykiety.
- **Nawigacja i widoki feedu.** Tekst i dolna kreska wskazują aktywną pozycję. W wersji mobilnej główna nawigacja otwiera się z przycisku „Menu”, a Escape zamyka ją i oddaje fokus temu przyciskowi. Widoki feedu pozostają osobną listą pod wyszukiwarką i wyróżnieniem.
- **Wpis.** Najpierw pojawia się autor lub instytucja, potem pochodzenie, data i ewentualne oznaczenie danych przykładowych. Dalej są tytuł, skrót, taksonomia, dostępne oceny i rozwijane uzasadnienie. Stopka mieści „Podbij”, odnośnik do komentarzy i licznik zainteresowań. Krótszy układ zachowuje nazwy akcji dla czytników ekranu.
- **Przykład wdrożenia.** Karta rekordu #514 z API łączy wynik z jednostką i okresem pomiaru. Stopka zawiera odnośnik do źródła i pełnej karty. Historyczna referencja kierunku kolorystyki i liternictwa to `tasks/referencje/T18-kierunek.png` z forum.

## Do's and Don'ts

### Do

- **Do** pokazuj pochodzenie i rozróżniaj dane przykładowe. Przy braku wyniku nazywaj brak.
- **Do** zapewnij obsługę klawiaturą od 320px i widoczny obrys fokusu (2px, odsunięcie 3px). Używaj białego obrysu na czerwonym nagłówku.
- **Do** pokazuj pełne tytuły w szczegółach i prowadź do nich czytelnym odnośnikiem ze skróconego wpisu.

### Don't

- **Don't** koduj znaczenia wyłącznie kolorem.
- **Don't** dodawaj cieni dekoracyjnych do kart wpisów ani wierszy tagów w miejsce jednej linii metadanych.
