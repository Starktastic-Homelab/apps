# pgAdmin PostgreSQL and retained CSI migration

## Intent and authority

The user requested autonomous completion of pgAdmin after Grafana, pausing for
an actual decision or missing access. Preserve users, roles, saved server
credentials, preferences, macros and private files. Keep ordinary Terraform/Ansible
rebuilds unchanged and use the existing shared PostgreSQL enrollment and retained
CSI contracts. This applies the established migration architecture to one app.

## Current source and selected approach

Read-only October16 assessment found chart1.70.4, stock pgAdmin9.18 image
`dpage/pgadmin4@sha256:c332c5f6dfba995d9ebc4af261d93506d6876085d712eaaa3defc8dd1a3f26de`,
SQLite schema52, one Ready Pod and one pre-existing restart. Source is
`databases/pgadmin-pgadmin4` on `/mnt/apps/pv/databases/pgadmin-pgadmin4`.
A consistent in-memory SQLite backup passed integrity and foreign-key checks.
There is one internal user, one server with an encrypted password, one custom
user-preference record and22 macro records; query history and process tables are
empty. The directory has393216 regular-file bytes, including the previous SQLite
backup. These are inventory measurements, not a stopped-source backup.

Use pgAdmin's supported external PostgreSQL backend and the existing idempotent
restricted-role/database enrollment. Keep the exact pgAdmin image, chart, auth
configuration, administrator Secret and server declarations. The upstream setup
CLI creates/upgrades schemas; it is not a whole-state SQLite-to-PostgreSQL importer.
Qualify a data-only transfer into a schema initialized by the exact stock app,
using its installed SQLAlchemy/psycopg dependencies and strict complete comparison.
Keep backend schema/version markers native and require source/target versions to
match. No application patch, third-party runtime image or new controller is needed.

Server export/reimport alone is rejected because it does not establish full
user/preferences/credential preservation. SQLite on retained CSI remains the
fallback design only if complete PostgreSQL preservation cannot be qualified;
changing to that fallback requires a user decision.

## Qualification and data handling

First use a closed, labelled local Docker network, no published ports, exact
upstream images and dummy credentials. Exercise Unicode, nulls, booleans, JSON,
binary-as-hex encrypted fields, timestamps, duplicate rows, composite keys and
serial floors. Prove missing/altered rows, extra source tables, wrong schema,
wrong database and unsupported representations fail. Preserve every application
field, native catalog and each database's original migration markers. Verify
saved-password decryption, internal login, private-file access, restart and an
independent dump restore to a different physical PostgreSQL server.

Real-data rehearsal may use consistent private copies only within the approved
operation scope, owner-only and Git-ignored, encrypted for durable recovery on
VM300 and this computer with separate outside-Git keys. Treat the SQLite database,
its embedded keys and encrypted saved connection password as sensitive. Do not
print them, include them in Git, or give fixtures real infrastructure credentials.
If scoped transfer approval is required by access review, finish a concrete
reviewable transfer proposal before asking. Keep source unchanged. Do not claim
complete migration from process success or row counts alone.

## Permanent runtime

Use a statically declared ext4 ReadWriteOncePod/Retain CSI claim for private files,
with target capacity chosen after fresh directory and full aggregate-growth
measurement. The existing NFS claim/path remains protected and admission-held.
Retain canonical file identity and reject absent/wrong data, SQLite fallback or
conflicting database configuration before the stock entrypoint starts.

Use the chart's existing service account and native extraInitContainers/volumes
for current Argo enrollment acceptance plus restricted canonical SQL login and
retained-schema/physical-database checks. Set Recreate and worker placement;
preserve existing chart inheritance, auth and server discovery. Bound the
configuration database connection pool after measuring shared-server capacity.
Provide the database URI through a Secret-mounted file using stock upstream
support; never expose its value in command arguments, logs or committed values.
Missing established data must not trigger stock first-run account/schema seeding.

## Production operation

Reuse the verified native maintenance owner and scoped Argo deny-window procedure.
Recheck ownership, current VM/node generations, exact source/target identities,
healthy dependencies, quota/full planned growth and every overlapping writer.
Include pgAdmin, base-configs, Filebrowser and the NFS provisioner where ownership
and parent-export writes require them. Preserve declared sync options when
retiring an exact captured blocked queue and queuing a full current-source sync.

Before allocation stop all resolved writers and verify API/CRI/mount retirement.
Take an exact cold all-file/metadata archive, encrypt and verify off-NAS recovery,
then independently restore it. Allocate/populate once, initialize/import once,
prove the current converted dump independently restorable, retire every helper
and attachment, then mark authority before starting stock pgAdmin. Never reopen
stale SQLite after PostgreSQL writes. Unknown child state excludes replay.

Accept existing authentication behavior, saved server connection and settings,
clean recreation and actual healthy-worker movement with the same disk identity.
Resume auxiliary writers. Verify the unchanged scheduled full PostgreSQL backup
includes pgAdmin. Merge final Git reconciliation only after exact-head hosted
checks and reviewed application diff. Require desired/live equality, release only
the owned hold, and observe a continuous six-minute no-regression watch.

One operation clock starts before writer shutdown:90minutes before authoritative
target startup and3hours total. Do not reset or extend it without user approval.
Leave source/target/recovery protected on failure; recover from exact receipts.
Clean only owned temporary resources and plaintext after encrypted audits and a
merged sanitized completion report. Native owner releases last; no broad prune.

## References

- [External database](https://www.pgadmin.org/docs/pgadmin4/9.18/external_database.html)
- [Exact upstream setup CLI](https://github.com/pgadmin-org/pgadmin4/blob/REL-9_18/web/setup.py)
- [Exact models and types](https://github.com/pgadmin-org/pgadmin4/blob/REL-9_18/web/pgadmin/model/__init__.py)
- [Exact stock entrypoint](https://github.com/pgadmin-org/pgadmin4/blob/REL-9_18/pkg/docker/entrypoint.sh)
- [Established live migration workflow](2026-10-10-live-storage-migrations-design.md)
