.PHONY: install db db-stop db-reset seed backend frontend basal test

install:
	cd backend && uv sync
	cd frontend && npm install

db:
	docker compose up -d --wait db

db-stop:
	docker compose stop db

# Kasuje wszystkie tabele, tworzy schemat od nowa i ładuje dane startowe.
db-reset: db
	cd backend && uv run flask --app app db-reset

seed:
	cd backend && uv run flask --app app seed

backend: db
	cd backend && uv run flask --app app run --debug --port 5000

frontend:
	cd frontend && npm run dev

# Serwer modelu decyzyjnego na porcie 8000 (pierwsze uruchomienie instaluje go obok repozytorium).
basal:
	scripts/basal-serve.sh

test: db
	cd backend && uv run pytest -q
