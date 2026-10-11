# PostgreSQL application enrollment sources

This directory is outside ApplicationSet discovery. Reviewed generated manifests
in the PostgreSQL Application activate the retained synthetic canary described in
the [operations guide](../../docs/operations/postgresql-enrollment.md). The eight
existing application databases and their credentials remain unchanged. Bootstrap
is a separately approved one-time operation and is never mounted in the Sync Job.

## Contracts

`prepare.py` creates encrypted inputs once. The native `enroll.sh run` consumes
those inputs repeatedly; it never generates credentials. Declarations are stable
ID/database/role/mode bindings. Removing one retains SQL objects and the ledger.
Names use lower-case ASCII with a leading letter; SQL names allow digits and
underscores, IDs/credential keys also allow hyphens, maximum 63 characters.
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
sessions, with a 30-second acquisition deadline. Each mutating session rechecks the
complete catalog and keeps the same maintenance connection through child schema
and authentication checks. Direct administrators are outside this lock contract.
The batch is not transactional across databases: a conflict appearing after
preflight can leave earlier completed entries intact.

New roles begin restricted and `NOLOGIN`. The role and provisioning ledger row
commit together. Native psql `\password` assigns SCRAM without plaintext SQL;
`CREATE DATABASE` then runs outside a transaction. A child connection restricts
new PUBLIC schema privileges. The final ready marker and `LOGIN` commit together.
Native authentication needs committed LOGIN. A later authentication-child failure
fails the Job but keeps completed ready/LOGIN; a retry never resets that credential.
Writers must wait for Job/acceptance success, not simply LOGIN or the ready row.
Schema/setup child failure keeps provisioning/NOLOGIN. This protocol still needs
native writer-gate qualification before activation.

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
An omitted Secret template type uses the native `Opaque` default; explicit
non-`Opaque` types and null or empty types are rejected.
Existing target keys are refused rather than overwritten. Application inputs
cannot target databases/postgres-admin-secret or databases/postgres-enrollment-credentials. `adopt` uses the same
arguments and reads the exact current password from stdin (no trailing newline).
Passwords support quotes, spaces, backslashes, dollar signs, backticks and UTF-8;
empty, NUL/CR/LF or values over 4096 bytes are rejected before writes/publication.
Never place passwords in command arguments or shell tracing.

The private bundle contains updated config, a ConfigMap, a generation-specific
enrollment Job, two SealedSecrets and inactive consumer gate/init sources.
Only ciphertext and non-secret declarations are published. Plaintext flows through
private subprocess stdin, with no plaintext temporary files. Both sealing operations
finish before exclusive output creation; retries refuse an existing output/config
binding. A successful preparation is one-time; a successful SQL retry is idempotent.
Review bundle paths/metadata before any separately approved source integration.

## Consumer completion gate (inactive)

`consumer-gate.yaml` supplies a dedicated ServiceAccount, a local script ConfigMap
and two RoleBindings for this declaration. Integrate the shared
`completion-reader-roles.yaml` once with the PostgreSQL Application. Each Role
permits only GET of one named object: `argocd/applications/postgres` and
`databases/configmaps/postgres-enrollment-config`. Consumers cannot read Kubernetes
Secrets through the API, list/watch objects, modify resources or use administrator
credentials. Multi-namespace resources require reviewed Argo project permissions.

`consumer-init.yaml` is a **PodSpec fragment**, not a deployable workload. Merge its
ServiceAccount selection, two ordered init containers and volumes into the app's
actual Helm values; preserve other init containers/volumes and any existing
ServiceAccount permissions needed by that app. Review the rendered Pod and
bindings before activation. Do not mount `/gate-api` or its volume in the main app:
the projected token is confined to the Python init. The following native psql init
mounts only the exact application password key, verifies login with `SELECT 1`,
and suppresses private connection error output. The main app still receives its
ordinary app credentials through its existing configuration. Both inits run as
UID1001 without privilege escalation, writable root filesystem or capabilities.

Preparation fingerprints the declared config, native runtime, gate protocol/code,
full Job template and a digest of aggregate **ciphertext**, never a password hash.
The ConfigMap records the full generation; the Job name uses its first128bits.
Publish the ConfigMap, generated Job and encrypted aggregate as a matching bundle.
Changing any of those inputs requires regenerating the ConfigMap/Job from the
existing ciphertext without resealing or resetting credentials. The low-level
`render_configmap(config, encrypted_data)` supports that operation; omitting
ciphertext produces only a SQL-fixture ConfigMap that the gate deliberately rejects.
Secret-only updates outside this matching-bundle contract are unsupported. Retain
removed entries' ciphertext and SQL objects under the existing retention contract.

The Python init brackets the Application read with two ConfigMap reads and rejects
changes in UID, resourceVersion or data. It requires the declared ID/database/role,
a verified generation, no active operation, Healthy/Synced status and a Succeeded
full sync containing that exact successful Sync Job hook. An unrelated Git commit
with unchanged enrollment inputs keeps that acceptance valid; Argo need not rerun
an already-Synced application just to advance its recorded operation revision. A selective or apply-only sync cannot serve as acceptance. Run a
**full hook sync** to recover; no retained successful Job object or SQL acceptance
schema is added. Authentication-child failure after ready/LOGIN remains blocked
because the Argo hook failed, even when login would already work.

Missing metadata, RBAC denial, unavailable TLS/API access or stale acceptance keeps
fresh Pods waiting. The init polls every5seconds for600seconds (plus bounded
in-flight10second API requests), then fails so kubelet can retry. Existing running
Pods continue. This is startup verification of an observed generation, not a
continuous SQL reconciler or an atomic lock on future configuration changes.
This source is regression-tested and the native consumer ordering, failed-child
and fresh-metadata retained-disk rebuild checks passed in the
[disposable qualification](../../docs/operations/postgresql-enrollment-qualification.md).
Generated manifests, rather than this source directory, activate consumers.

## Native runtime and qualification

Mount `/config/config.json`, the three non-bootstrap scripts under `/scripts`,
admin key `/credentials/admin/postgres-password` and app keys under
`/credentials/apps`. Supply only PGHOST/PGPORT/PGUSER=postgres/PGDATABASE=postgres
as environment. The inactive `job.yaml` is the bounded, nonroot native client
template; deploy the matching prepared `enrollment-job.yaml`, never the fixed-name
template, when integrating the completion gate.

```sh
python3 scripts/test-pg-enrollment.py -v
python3 scripts/test-pg-backup.py
```

The suite needs the local Docker socket. It uses synthetic passwords, an internal
network with no published ports, digest-pinned PG18.6 client/current Bitnami server,
once-named containers and one owned volume. Server limit1GiB/1CPU; at most two
clients 128Mi/0.5CPU each; logs two5Mi files. Data usage is observed below 1GiB,
not a filesystem quota. Cleanup removes only recorded test resources, never prunes
the daemon. No arbitrary external DSN, existing container or production credential
is accepted. Pause-only copies of native SQL qualify six interruption boundaries;
no production fault flag exists. Private verifier assertions never print hashes.

Local SQL qualification is distinct from the completed disposable Argo/Sealed
Secrets and retained-disk rebuild qualification. Sync hooks do not run during selective sync. Keep
failed Job evidence; retries require full PostgreSQL Application sync. Controller
consumers sharing the PostgreSQL rollout group need explicit writer gating.
Production activation, synthetic pilot, individual legacy adoption, Autobrr
conversion and PostgreSQL CSI migration remain separately approved stages.

See the [design](../../docs/superpowers/specs/2026-10-10-postgresql-enrollment-design.md)
and [plan](../../docs/superpowers/plans/2026-10-10-postgresql-enrollment.md).
