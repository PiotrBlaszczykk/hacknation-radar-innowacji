# Radar Innowacji

Prototyp na HackNation 2026 (zadanie „Radar innowacji”, Podkarpackie Centrum Innowacji).

Platforma, na której innowacje ze szkół, uczelni, samorządów i instytucji publicznych mają swoje profile. Profil powstaje ze zgłoszenia twórcy albo automatycznie, gdy radar wykryje innowację w otwartym źródle. Każda innowacja dostaje ocenę potencjału według jawnych kryteriów, rekomendację dalszej ścieżki, listę podobnych rozwiązań i dopasowanych odbiorców, partnerów lub inwestorów.

## Uruchomienie

Wymagania: Docker, [uv](https://docs.astral.sh/uv/), Node 20+, [Ollama](https://ollama.com).

```bash
make install        # zależności backendu i frontu
ollama pull bge-m3  # model embeddingów
make db-reset       # Postgres w kontenerze, schemat i dane przykładowe
make backend        # API na http://127.0.0.1:5000
make frontend       # aplikacja na http://127.0.0.1:5173 (w drugim terminalu)
make basal          # serwer modelu decyzyjnego na porcie 8000 (opcjonalny, w trzecim terminalu)
make test
```

Konfiguracja jest w zmiennych środowiskowych, opis w `.env.example`. Bez pliku `.env` działają wartości domyślne.

## Budowa

| Katalog | Zawartość |
|---|---|
| `backend/` | API we Flasku, SQLAlchemy, PostgreSQL z pgvector |
| `frontend/` | React, TypeScript, Vite, Tailwind |
| `docker-compose.yml` | baza danych |

Modele językowe działają lokalnie przez Ollamę, więc treść zgłoszeń nie opuszcza maszyny.

## Licencja

EUPL-1.2, tekst w pliku `LICENSE`.
