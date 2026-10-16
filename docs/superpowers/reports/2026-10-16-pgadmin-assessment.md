# pgAdmin PostgreSQL assessment and synthetic qualification

Status: production remains unchanged on SQLite/NFS. Real-data qualification is
blocked on explicit sensitive-transfer approval; no production data was exported.

## Current source

Read-only assessment found stock pgAdmin9.18 at digest
`sha256:c332c5f6dfba995d9ebc4af261d93506d6876085d712eaaa3defc8dd1a3f26de`,
chart1.70.4, one Ready Pod with one pre-existing restart, schema52 and a healthy
consistent in-memory SQLite snapshot. The source claim is
`databases/pgadmin-pgadmin4`, NAS `/mnt/apps/pv/databases/pgadmin-pgadmin4`.
Regular files total393216bytes, including the previous SQLite backup.

The source has22 application/native-schema tables plus SQLite's internal allocator
ledger. It contains one internal user, one server with an encrypted saved password,
three application keys,22macros, one custom preference, three settings and seven
cached database records. Source query history, process state and MFA are empty.
These counts are inventory; no current cold-backup or production migration is
represented by this report.

## Upstream behavior and selected qualification

pgAdmin officially supports an external PostgreSQL configuration database. The
setup CLI handles initialization/schema upgrades, while server export/import alone
does not establish complete state preservation. The proposed one-time transfer
copies data into a schema initialized by the exact stock app. It does not patch
pgAdmin, rewrite migration markers or create a third-party runtime dependency.

The stock entrypoint may initialize an absent configuration database. Permanent
startup must therefore reject missing/wrong retained data, an unaccepted current
enrollment or an empty/wrong native SQL target before that entrypoint executes.
Use the existing completion gate and static retained CSI workflow.

## Accepted synthetic evidence

A labelled internal Docker network has no published ports or outside egress.
Fixtures use the exact deployed pgAdmin image, pinned PostgreSQL18.6 and dummy
credentials. Public authentication configuration matches production.

The data-only transaction preserved every mapped field and duplicate in all22
native tables,464rows before application startup. Both native schema markers
remain unchanged. Ten serial allocators were checked; import replay and a wrong
physical PostgreSQL identity were rejected without changing the accepted state.
Comparison preserves SQL NULL separately from JSON null/string null, validates
booleans and32/64-bit integers, checks strict UTF8 and timestamps, and treats
pgAdmin's encrypted binary-as-hex values as unchanged text.

After the target stock app restarted, a real internal HTTP form login succeeded.
The saved server connected through stock pgAdmin without supplying its PostgreSQL
password, proving the preserved user hash and encrypted saved password remain
usable in the dummy fixture. Initial HTTP probes used a JSON request and omitted
the server-group URL segment; tracing stock routes corrected the probe without
changing the application. Startup took about40seconds; an earlier30second ping
was simply premature.

An actual native dump was restored to another physical PostgreSQL instance. All22
tables, every mapped field/duplicate, native schema markers and serial state match.
The encrypted saved password still decrypts. The first read-only restore checker
omitted the stock module path; its exact failed terminal was retained, and only
that checker was resumed after fixing its import path. The dump and restore did
not replay.

Seven local comparison/source-boundary tests pass, including unchanged source files,
rejected symlinks/unknown tables, malformed representations, equal-count changed
fields and duplicate loss. A fresh second target was also initialized by stock pgAdmin under a restricted
role with no superuser, role/database creation, replication or RLS-bypass privileges.
The role owns the native schema; the same22-table/464-row transfer, restart,
internal login and saved-password connection passed under it. An independent
restore captures465rows after normal browser startup added one user-preference
record (zero before, one afterward); the other table counts stayed unchanged.

These tests and synthetic evidence do not establish real-data compatibility or
production acceptance.

## Next required gate

The real source contains sensitive application keys, the internal account's
password hash and an encrypted saved PostgreSQL password. Automatic approval
review rejected exporting that payload to a private local rehearsal directory:
autonomous migration authority did not explicitly identify the payload/destination.
The rejected process never started; the planned source copy does not exist.

Obtain the scoped [transfer approval](../plans/2026-10-16-pgadmin-sensitive-transfer.md),
then qualify complete real-data preservation and restricted-role startup/recovery.
Afterward complete native-package review, enrollment, current cold recovery,
retained disk allocation, cutover, lifecycle/connection acceptance, final backup,
Git reconciliation and exact cleanup under the
[implementation plan](../plans/2026-10-16-pgadmin-postgresql-csi.md).

## Primary references

- [External configuration database](https://www.pgadmin.org/docs/pgadmin4/9.18/external_database.html)
- [Exact upstream setup CLI](https://github.com/pgadmin-org/pgadmin4/blob/REL-9_18/web/setup.py)
- [Exact schema/models](https://github.com/pgadmin-org/pgadmin4/blob/REL-9_18/web/pgadmin/model/__init__.py)
- [Exact stock entrypoint](https://github.com/pgadmin-org/pgadmin4/blob/REL-9_18/pkg/docker/entrypoint.sh)
