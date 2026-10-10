#!/bin/sh
# Secret values never enter arguments, tracing or diagnostic output.
set +x
set -eu
umask 077
export PGCONNECT_TIMEOUT=5
export PGOPTIONS='-c statement_timeout=60000'
fail() { echo 'PostgreSQL enrollment failed; inspect declared identity, registry and credentials.' >&2; exit 1; }
password_file() {
  [ -f "$1" ] && [ -s "$1" ] && [ "$(wc -c < "$1")" -le 4096 ] || fail
  if ! od -An -tu1 "$1" | awk '{for(i=1;i<=NF;i++) if($i==0 || $i==10 || $i==13) exit 1}'; then
    echo 'Password contains unsupported NUL/CR/LF bytes.' >&2
    exit 1
  fi
}
admin() {
  password_file /credentials/admin/postgres-password
  PGPASSWORD=$(cat /credentials/admin/postgres-password)
  export PGPASSWORD
}
case "${1:-}" in
  run)
    [ "${PGDATABASE:-}" = postgres ] && [ "${PGUSER:-}" = postgres ] || fail
    admin
    scratch=$(mktemp -d)
    trap 'rm -rf "$scratch"' EXIT HUP INT TERM
    tab=$(printf '\t')
    psql -XqAt -F "$tab" -v ON_ERROR_STOP=1 -v preflight=true -v rows="$scratch/entries" -f /scripts/enroll.sql > /dev/null 2>&1 || fail
    # Validate ALL credential projections before creating anything.
    while IFS="$tab" read -r id db role mode key verify; do
      password_file "/credentials/apps/$key"
    done < "$scratch/entries"
    # Existing credentials are acceptance checks, never password reset permission.
    while IFS="$tab" read -r id db role mode key verify; do
      if [ "$verify" = t ]; then
        ENROLL_DATABASE=$db ENROLL_ROLE=$role ENROLL_KEY=$key /bin/sh /scripts/enroll.sh verify-login || fail
      fi
    done < "$scratch/entries"
    while IFS="$tab" read -r id db role mode key verify; do
      password=$(cat "/credentials/apps/$key")
      if ! printf '%s\n%s\n' "$password" "$password" |
        psql -XqAt -v ON_ERROR_STOP=1 -v preflight=false -v entry="$id" -f /scripts/enroll.sql > /dev/null 2>&1; then
        echo "Enrollment $id failed." >&2
        fail
      fi
      echo "Enrollment $id verified."
    done < "$scratch/entries"
    ;;
  schema)
    admin
    PGDATABASE=$ENROLL_DATABASE
    export PGDATABASE
    psql -Xq -v ON_ERROR_STOP=1 -v role="$ENROLL_ROLE" -f /scripts/schema.sql > /dev/null 2>&1 || fail
    ;;
  verify-login)
    password_file "/credentials/apps/$ENROLL_KEY"
    PGPASSWORD=$(cat "/credentials/apps/$ENROLL_KEY")
    PGUSER=$ENROLL_ROLE
    PGDATABASE=$ENROLL_DATABASE
    export PGPASSWORD PGUSER PGDATABASE
    psql -XqAt -v ON_ERROR_STOP=1 -c 'SELECT 1' > /dev/null 2>&1 || fail
    ;;
  *) fail ;;
esac
