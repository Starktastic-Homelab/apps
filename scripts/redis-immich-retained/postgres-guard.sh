#!/bin/bash
# Read-only PG17 identity guard. RWOP and verified retirement fence writers.
set -eu
export LC_ALL=C
fail() { echo 'Retained Immich PostgreSQL startup refused: identity check failed.' >&2; exit 1; }
data=/data/pgdata
bin=/usr/lib/postgresql/17/bin/pg_controldata
expected=${EXPECTED_SYSTEM_IDENTIFIER:-}
[[ $expected =~ ^[1-9][0-9]{0,19}$ ]] || fail
[[ $("$bin" --version) == 'pg_controldata (PostgreSQL) 17.'* ]] || fail
for directory in /data "$data" "$data/base" "$data/global" "$data/pg_wal"; do
  [ -d "$directory" ] && [ ! -L "$directory" ] && [ -r "$directory" ] && [ -x "$directory" ] || fail
done
for file in "$data/PG_VERSION" "$data/global/pg_control"; do
  [ -f "$file" ] && [ ! -L "$file" ] && [ -r "$file" ] || fail
done
[ "$(cat "$data/PG_VERSION")" = 17 ] || fail
[ "$(stat -c %s "$data/global/pg_control")" = 8192 ] || fail
for signal in standby.signal recovery.signal; do
  [ ! -e "$data/$signal" ] && [ ! -L "$data/$signal" ] || fail
done
# This dedicated cluster has no external WAL/tablespaces. Preparation and each
# production preflight must verify that complete root contract again.
[ -z "$(find "$data" -type l -print -quit)" ] || fail
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
if ! timeout 30 "$bin" "$data" >"$scratch/control" 2>"$scratch/error"; then fail; fi
[ ! -s "$scratch/error" ] || fail
actual=$(awk '/^Database system identifier:[[:space:]]+[0-9]+$/ {print $NF}' "$scratch/control")
[ "$actual" = "$expected" ] || fail
# Leave postmaster.pid untouched. Stock PostgreSQL alone performs qualified WAL
# and stale-PID recovery under verified fencing. Never init, repair or chown.
echo 'Retained Immich PostgreSQL identity verified.'
