#!/usr/bin/env bash
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
export T14_STATE_DIR="${T14_STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/wihajster-t14}"
case "${1:-}" in
  api)
    cd -- "$repo/backend"
    export PYTHONPATH="$repo/backend"
    exec uv run python "$repo/scripts/demo/serve.py"
    ;;
  web)
    cd -- "$repo/frontend"
    exec npm run dev -- --config "$repo/scripts/demo/vite.config.mts"
    ;;
  *)
    echo 'Użycie: scripts/demo/serve.sh api | web' >&2
    exit 2
    ;;
esac
