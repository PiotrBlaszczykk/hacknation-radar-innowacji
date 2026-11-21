#!/usr/bin/env bash
set -euo pipefail
umask 077

if (( $# != 0 )); then
  echo "Użycie: scripts/demo/prepare.sh (źródło radar, cel radar_t14_demo na localhost)" >&2
  exit 2
fi

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
state="${T14_STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/wihajster-t14}"
source_cache="${T14_SOURCE_CACHE:-$repo/../radar-inowacji/data/cache}"
marker='Wihajster T14 demo copy'
export PGPASSWORD="${PGPASSWORD:-radar}"
pg=(-h 127.0.0.1 -p 5432 -U radar)
mkdir -p -- "$state"
exec 9>"$state/prepare.lock"
if ! flock -n 9; then
  echo 'Trwa już przygotowanie kopii T14.' >&2
  exit 1
fi

psql_demo() {
  psql -X "${pg[@]}" -v ON_ERROR_STOP=1 -d radar_t14_demo "$@"
}

# Zgoda na odtworzenie pochodzi z komentarza bazy, niezależnego od wgrywanego schematu.
existing=$(psql -X "${pg[@]}" -At -d postgres -v ON_ERROR_STOP=1 -c "
  SELECT coalesce(shobj_description(oid, 'pg_database'), '<bez oznaczenia>')
  FROM pg_database WHERE datname = 'radar_t14_demo'")
if [[ -z "$existing" ]]; then
  createdb "${pg[@]}" radar_t14_demo
  psql_demo -c "COMMENT ON DATABASE radar_t14_demo IS '$marker'"
elif [[ "$existing" != "$marker" ]]; then
  echo 'Baza radar_t14_demo już istnieje i nie ma oznaczenia T14.' >&2
  exit 1
fi

scratch=$(mktemp -d -- "$state/prepare.XXXXXX")
trap 'rm -rf -- "$scratch"' EXIT
if [[ ! -f "$state/t13.dump" ]]; then
  PGOPTIONS='-c default_transaction_read_only=on' pg_dump "${pg[@]}" -Fc -f "$scratch/t13.dump" -d radar
  mv -- "$scratch/t13.dump" "$state/t13.dump"
fi
if [[ ! -d "$state/cache-base" ]]; then
  cp -a -- "$source_cache" "$scratch/cache-base"
  mv -- "$scratch/cache-base" "$state/cache-base"
fi

cp -a -- "$state/cache-base" "$scratch/cache"

cat "$repo/scripts/demo/guard.sql" > "$scratch/restore.sql"
pg_restore --clean --if-exists --no-owner --no-privileges -f "$scratch/dump.sql" "$state/t13.dump"
cat "$scratch/dump.sql" "$repo/scripts/demo/fixtures.sql" >> "$scratch/restore.sql"
psql_demo --single-transaction -q -o /dev/null -f "$scratch/restore.sql"

# Import w demonstracji aktualizuje tę własną kopię cache, w tym statystyki ostatniego uruchomienia.
if [[ -d "$state/cache" ]]; then
  mv -- "$state/cache" "$scratch/previous-cache"
fi
mv -- "$scratch/cache" "$state/cache"
echo 'Gotowa kopia radar_t14_demo. Przygotowanie odtwarza stan sprzed próby.'
