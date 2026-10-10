#!/bin/bash
# Identity guard only. RWOP attachment and verified VM retirement fence writers.
set -eu
export LC_ALL=C
fail() {
  echo 'Retained PostgreSQL startup refused: data identity validation failed.' >&2
  exit 1
}
data=/bitnami/postgresql/data
bin=/opt/bitnami/postgresql/bin/pg_controldata
expected=${EXPECTED_SYSTEM_IDENTIFIER:-}
# Canonical decimal identifiers only; the native identifier comparison also
# rejects values outside uint64 range. Never infer the expectation from PGDATA.
[[ $expected =~ ^[1-9][0-9]{0,19}$ ]] || fail
[[ $("$bin" --version) == 'pg_controldata (PostgreSQL) 18.'* ]] || fail
for directory in /bitnami/postgresql "$data" "$data/base" "$data/global" "$data/pg_wal"; do
  [ -d "$directory" ] && [ ! -L "$directory" ] && [ -r "$directory" ] && [ -x "$directory" ] || fail
done
for file in "$data/PG_VERSION" "$data/global/pg_control"; do
  [ -f "$file" ] && [ ! -L "$file" ] && [ -r "$file" ] || fail
done
[ "$(cat "$data/PG_VERSION")" = 18 ] || fail
# PG18 stores an8192-byte control file; the native tool reads only its header.
[ "$(stat -c %s "$data/global/pg_control")" = 8192 ] || fail
# Test existence including dangling symlinks, before Bitnami can delete signals.
for signal in standby.signal recovery.signal; do
  [ ! -e "$data/$signal" ] && [ ! -L "$data/$signal" ] || fail
done
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
# Native pg_controldata may return0 despite a CRC warning. Reject all stderr.
if ! timeout 30 "$bin" "$data" >"$scratch/control" 2>"$scratch/error"; then fail; fi
[ ! -s "$scratch/error" ] || fail
actual=$(awk '/^Database system identifier:[[:space:]]+[0-9]+$/ {print $NF}' "$scratch/control")
[ "$actual" = "$expected" ] || fail
# Leave a remaining postmaster.pid untouched; stock entrypoint handles restart
# cleanup under the separately verified fencing contract. Do not initialize,
# repair, chown or connect to this database here.
echo 'Retained PostgreSQL data identity verified.'
