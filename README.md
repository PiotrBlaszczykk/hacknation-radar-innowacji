# Wihajster · Radar innowacji

## Jak uruchomić po pobraniu zmian

W katalogu sklonowanego repozytorium wykonaj:

```bash
git pull
./start.sh
```

Otwórz **[http://127.0.0.1:5173](http://127.0.0.1:5173)**, kiedy w terminalu pojawi się „Wihajster działa”. Pozostaw terminal otwarty. **Ctrl+C** zatrzymuje aplikację. Przy kolejnym starcie dane z PostgreSQL pozostają na miejscu.

### Pierwsze uruchomienie

Potrzebujesz Bash, curl, działającego Dockera z Compose, [uv](https://docs.astral.sh/uv/), Node.js 22.12+ z npm oraz [Ollamy](https://ollama.com/download). Pierwszy start wymaga internetu i pobiera zależności oraz dwa modele AI, więc może potrwać kilka minut.

Skrypt przygotowuje bazę PostgreSQL z pgvector, dane przykładowe i profil „Lena Wrona · demo”, sprawdza modele, uzupełnia brakujące wektory i uruchamia API oraz frontend. Nowa baza zawiera zestaw startowy. Pełny katalog zgromadzony na komputerze demonstracyjnym pochodzi z osobnych importów. Źródła możesz sprawdzić w aplikacji w zakładce **Źródła**.

### Jeśli masz już uruchomioną aplikację

Zakończ poprzednią sesję przez Ctrl+C, zanim ponownie wykonasz `./start.sh`. Domyślne porty to 5173 dla aplikacji, 5000 dla API, 5432 dla PostgreSQL i 11434 dla Ollamy. Konfigurację modeli i połączenia z bazą możesz zmienić w lokalnym pliku `.env` według [.env.example](.env.example). Osobny skalibrowany serwer decyzji można uruchomić przez `make basal` z ustawionym `BASAL_URL=http://127.0.0.1:8000`. Domyślnie decyzje obsługuje Ollama.

Licencja projektu: [EUPL-1.2](LICENSE).
