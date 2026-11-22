#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
root=$PWD
if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi
api_port=${API_PORT:-5000}
web_port=${WEB_PORT:-5173}
export WIHAJSTER_API_URL="http://127.0.0.1:$api_port"
export OLLAMA_URL=${OLLAMA_URL:-http://127.0.0.1:11434}
export OLLAMA_HOST="$OLLAMA_URL"
export EMBED_MODEL=${EMBED_MODEL:-bge-m3}
export LLM_MODEL=${LLM_MODEL:-hf.co/Remek/basal-2.0-4.5B-GGUF:Q8_0}
for command in uv node npm curl; do
  command -v "$command" >/dev/null || { echo "Brakuje programu $command. Zobacz README.md." >&2; exit 1; }
done

# Przed instalacją zależności sprawdź porty, także gdy jest uruchomiona prezentacja.
node --input-type=module - "$api_port" "$web_port" <<'JS'
import net from 'node:net';
for (const port of process.argv.slice(2)) {
  const s = net.createServer();
  try { await new Promise((ok, fail) => s.once('error', fail).listen(Number(port), '127.0.0.1', ok)); }
  catch { console.error('Port ' + port + ' jest niedostępny. Zatrzymaj poprzedni serwer albo ustaw API_PORT i WEB_PORT.'); process.exit(1); }
  await new Promise(ok => s.close(ok));
}
JS
pids=()
cleanup() { for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
wait_url() {
  for ((i=0;i<60;i++)); do
    curl -fsS --max-time 2 "$1" >/dev/null 2>&1 && return
    kill -0 "$2" 2>/dev/null || break
    sleep 1
  done
  echo "Usługa nie odpowiada: $1" >&2
  return 1
}
cd "$root/backend"
uv sync --locked
if ! .venv/bin/python -c 'from app.config import Config; from sqlalchemy import create_engine; create_engine(Config.SQLALCHEMY_DATABASE_URI, connect_args={"connect_timeout":3}).connect().close()' 2>/dev/null; then
  docker compose -f "$root/docker-compose.yml" up -d --wait db
fi
.venv/bin/flask --app app db-init
.venv/bin/flask --app app social-demo
if ! curl -fsS --max-time 3 "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
  ollama serve &
  pids+=("$!")
  wait_url "$OLLAMA_URL/api/tags" "$!"
fi
for model in "$EMBED_MODEL" "$LLM_MODEL"; do
  ollama show "$model" >/dev/null 2>&1 || ollama pull "$model"
done
.venv/bin/flask --app app embed
cd "$root/frontend"
npm ci --no-audit --no-fund
"$root/backend/.venv/bin/flask" --app "$root/backend/app" run --host 127.0.0.1 --port "$api_port" &
api_pid=$!
pids+=("$api_pid")
wait_url "$WIHAJSTER_API_URL/api/users" "$api_pid"
node node_modules/vite/bin/vite.js --host 127.0.0.1 --port "$web_port" --strictPort &
web_pid=$!
pids+=("$web_pid")
wait_url "http://127.0.0.1:$web_port/api/users" "$web_pid"
echo "Wihajster działa: http://127.0.0.1:$web_port  (Ctrl+C kończy sesję)"
while kill -0 "$api_pid" 2>/dev/null && kill -0 "$web_pid" 2>/dev/null; do sleep 1; done
echo 'Jeden z serwerów zakończył pracę.' >&2
exit 1
