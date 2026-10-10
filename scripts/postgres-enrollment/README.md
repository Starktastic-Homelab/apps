# PostgreSQL application enrollment (inactive source)

This directory is outside ApplicationSet discovery. Nothing here installs a
registry, creates production credentials or starts a Job until separately reviewed
manifests are copied into the PostgreSQL Application. The current server, eight
existing application databases and their credentials remain unchanged.

## Contracts

`prepare.py` creates encrypted inputs once. The native `enroll.sh run` consumes
those inputs repeatedly; it never generates credentials. Declarations are stable
ID/database/role/mode bindings. Removing one retains SQL objects and the ledger.
Names use lower-case ASCII with a leading letter; SQL names allow digits and
underscores, IDs/credential keys also allow hyphens, maximum63 characters.
Reserved PostgreSQL identities and duplicate bindings are rejected.

The maintenance database `postgres` contains the admin-only
`homelab_enrollment.enrollments` ledger. A separate, explicitly approved one-time
`bootstrap.sql` creates it transactionally while checking the expected physical
system identifier. It is deliberately absent from the ordinary ConfigMap/Job.
Normal enrollment rejects a missing, corrupt or differently owned registry, a
standby, or another physical server. Logical restore requires reviewed identity
rebinding. Enrollment does not restore lost data.

All declarations, catalogs and existing/adopted credentials are preflighted before
writes. A session advisory lock `(1346848082,1)` serializes cooperating enrollment
sessions, with a30-second acquisition deadline. Each mutating session rechecks the
complete catalog and keeps the same maintenance connection through child schema
and authentication checks. Direct administrators are outside this lock contract.
The batch is not transactional across databases: a conflict appearing after
preflight can leave earlier completed entries intact.

New roles begin restricted and `NOLOGIN`. The role and provisioning ledger row
commit together. Native psql `\password` assigns SCRAM without plaintext SQL;
`CREATE DATABASE` then runs outside a transaction. A child connection restricts
new PUBLIC schema privileges. The final ready marker and `LOGIN` commit together.
Interrupted provisioning resumes the recorded names/owner; missing recorded roles,
unexpected LOGIN or wrong database ownership fail. Ready databases are never
recreated. Canonical authentication failure never resets an established password.

Explicit `adopt` requires existing compatible roles/databases and the verified
current password. It writes only the ledger; legacy memberships, grants, schema
owners, extensions and data remain unchanged. Elevated memberships are rejected.
New databases revoke PUBLIC database/schema access. This does not tighten legacy
server-wide access silently. Applications own their migrations and extensions.
Password rotation, renaming, ownership transfer and deletion require separate work.

## Prepare encrypted inputs

Requires Python3, PyYAML and the existing `scripts/seal.sh` tools/certificate
(kubectl client dry-run and kubeseal). No SQL or Kubernetes apply occurs.

```sh
python3 scripts/postgres-enrollment/prepare.py new \
  --config /private/enrollment/config.json \
  --id example --database example --role example \
  --password-key example-password \
  --app-namespace media --app-secret example-db-secret \
  --app-password-key password --app-url-key database-url \
  --output-dir /private/enrollment/example-bundle
```

For subsequent entries, pass the existing encrypted aggregate with
`--aggregate-secret PATH`; it must contain every prior declared credential key.
Use `--app-sealed-secret PATH` to retain unrelated application encrypted keys and
metadata. Both inputs must match exact name/namespace and strict sealing scope.
Existing target keys are refused rather than overwritten. `adopt` uses the same
arguments and reads the exact current password from stdin (no trailing newline).
Passwords support quotes, spaces, backslashes, dollar signs, backticks and UTF-8;
empty, NUL/CR/LF or values over4096 bytes are rejected before writes/publication.
Never place passwords in command arguments or shell tracing.

The private bundle contains updated config, a ConfigMap and two SealedSecrets.
Only ciphertext and non-secret declarations are published. Plaintext flows through
private subprocess stdin, with no plaintext temporary files. Both sealing operations
finish before exclusive output creation; retries refuse an existing output/config
binding. A successful preparation is one-time; a successful SQL retry is idempotent.
Review bundle paths/metadata before any separately approved source integration.

## Native runtime and qualification

Mount `/config/config.json`, the three non-bootstrap scripts under `/scripts`,
admin key `/credentials/admin/postgres-password` and app keys under
`/credentials/apps`. Supply only PGHOST/PGPORT/PGUSER=postgres/PGDATABASE=postgres
as environment. The inactive `job.yaml` defines the bounded, nonroot native client.

```sh
python3 scripts/test-pg-enrollment.py -v
python3 scripts/test-pg-backup.py
```

The suite needs the local Docker socket. It uses synthetic passwords, an internal
network with no published ports, digest-pinned PG18.6 client/current Bitnami server,
once-named containers and one owned volume. Server limit1GiB/1CPU; at most two
clients128Mi/0.5CPU each; logs two5Mi files. Data usage is observed below1GiB,
not a filesystem quota. Cleanup removes only recorded test resources, never prunes
the daemon. No arbitrary external DSN, existing container or production credential
is accepted. Pause-only copies of native SQL qualify six interruption boundaries;
no production fault flag exists. Private verifier assertions never print hashes.

Local SQL qualification is distinct from the remaining Argo/Sealed Secrets and
retained-disk rebuild gate. Sync hooks do not run during selective sync. Keep
failed Job evidence; retries require full PostgreSQL Application sync. Controller
consumers sharing the PostgreSQL rollout group need explicit writer gating.
Production activation, synthetic pilot, individual legacy adoption, Autobrr
conversion and PostgreSQL CSI migration remain separately approved stages.

See the [design](../../docs/superpowers/specs/2026-10-10-postgresql-enrollment-design.md)
and [plan](../../docs/superpowers/plans/2026-10-10-postgresql-enrollment.md).
