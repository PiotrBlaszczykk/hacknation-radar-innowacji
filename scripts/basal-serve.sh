#!/usr/bin/env bash
# Uruchamia basal-serve: serwer decyzji (wybór, tak/nie, skala, wiele etykiet) ze skalibrowanymi
# prawdopodobieństwami. Wagi modelu serwuje Ollama, serwer układa prompt i czyta logity.
# Przy pierwszym uruchomieniu instaluje serwer w osobnym środowisku obok repozytorium.
#
# Backend korzysta z serwera, gdy w .env jest BASAL_URL=http://127.0.0.1:8000.
# Bez niego działa silnik zastępczy (te same pytania, prawdopodobieństwa nieskalibrowane).
set -euo pipefail

BASAL_DIR="${BASAL_DIR:-$(cd "$(dirname "$0")/../.." && pwd)/basal}"
BASAL_VERSION="v2.8.1"
MODEL_REPO="Remek/basal-2.0-4.5B-GGUF"
# Ten sam model, którego backend używa do pisania tekstu: inna nazwa zmusiłaby Ollamę
# do przeładowywania wag przy każdym przejściu między decyzją a tekstem (4 s zamiast 0,7 s).
OLLAMA_MODEL="${LLM_MODEL:-hf.co/Remek/basal-2.0-4.5B-GGUF:Q8_0}"
PORT="${BASAL_PORT:-8000}"

mkdir -p "$BASAL_DIR"
cd "$BASAL_DIR"

if [ ! -x env/bin/basal-serve ]; then
  uv venv --python 3.12 env
  # Wersja CPU wystarcza: serwer nie liczy modelu, potrzebuje tylko tokenizera i szablonu.
  uv pip install --python env/bin/python torch --index-url https://download.pytorch.org/whl/cpu
  uv pip install --python env/bin/python "basal @ https://github.com/rkinas/basal/archive/refs/tags/${BASAL_VERSION}.tar.gz"
fi

if [ ! -f basal-2.0-4.5B-GGUF/CALIBRATION.json ]; then
  # Bez plików .gguf: wagi są już w Ollamie (ollama pull "$OLLAMA_MODEL").
  env/bin/hf download "$MODEL_REPO" --local-dir basal-2.0-4.5B-GGUF --exclude "*.gguf"
fi

exec env/bin/basal-serve --model ./basal-2.0-4.5B-GGUF --mode ollama \
  --ollama-model "$OLLAMA_MODEL" --host 127.0.0.1 --port "$PORT"
