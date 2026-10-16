# pgAdmin PostgreSQL assessment and qualification

Status: production remains unchanged on SQLite/NFS. Approved real-data conversion,
restricted-role stock startup and independent recovery passed in the closed lab.

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

Eight local comparison/source-boundary tests pass, including unchanged source files,
rejected symlinks/unknown tables, malformed representations, equal-count changed
fields and duplicate loss. A fresh second target was also initialized by stock pgAdmin under a restricted
role with no superuser, role/database creation, replication or RLS-bypass privileges.
The role owns the native schema; the same22-table/464-row transfer, restart,
internal login and saved-password connection passed under it. An independent
restore captures465rows after normal browser startup added one user-preference
record (zero before, one afterward); the other table counts stayed unchanged.

## Approved real-data evidence

The user approved the exact sensitive payload, private destinations and cleanup
in the [transfer scope](../plans/2026-10-16-pgadmin-sensitive-transfer.md). A consistent
read-only snapshot was received privately; the production source stayed unchanged.
The closed lab received no plaintext production login or infrastructure credentials.

Data-only conversion, stock startup and an independent restore preserved every
original field and duplicate across all22tables,475rows. The original user hash,
three application keys and encrypted saved password remained unchanged; native
migration markers and all serial states passed. The target used a restricted role.
The first independent restore exposed a missing fixture role referenced by native
ACLs. Its known failed terminal and partial database were preserved; a new recovery
database with that role restored the same dump successfully. Import did not replay.

This establishes real-data conversion and recoverability. Actual authentication
and saved-server connection remain production acceptance gates; they were not
claimed from ciphertext equality or supplied with production passwords in the lab.
An independent review found binary-float rounding in the JSON comparator. A failing
regression reproduced distinct high-precision decimals comparing equal. Comparison
now preserves original number tokens, including extreme exponents and signed zero;
JSON input text was already copied unchanged. Existing real-copy state is rechecked
with the corrected comparator without replaying import.
Native file/URI, current enrollment and read-only SQL guards passed ten local
checks, including actual layered chart rendering and transactional native losses.
The stock image accepted a Secret-mounted quoted URI and its two-plus-one pool.
Current production internal login and the saved-password server connection both
passed natively; credentials stayed on the master. These are baseline checks,
not post-migration acceptance.

Fresh capacity measured60of100PostgreSQL connections and103790915584NAS bytes
available against98591333376required for all outstanding raw growth, a1Gi target,
512Mi staging and8Gi headroom. Preparation uses a dedicated scoped account because
the current chart uses the default account with automatic token mount disabled.
Production cold recovery and independent SQL recovery have now passed. The retained
disk is authoritative; original internal login, encrypted saved-server connection,
recreation and movement between workers passed. Git reconciliation, final six-minute
watch and exact temporary-resource cleanup passed. See the
[production completion report](2026-10-16-pgadmin-production-completion.md) for evidence
and the separately tested runtime checker corrections.

## Primary references

- [External configuration database](https://www.pgadmin.org/docs/pgadmin4/9.18/external_database.html)
- [Exact upstream setup CLI](https://github.com/pgadmin-org/pgadmin4/blob/REL-9_18/web/setup.py)
- [Exact schema/models](https://github.com/pgadmin-org/pgadmin4/blob/REL-9_18/web/pgadmin/model/__init__.py)
- [Exact stock entrypoint](https://github.com/pgadmin-org/pgadmin4/blob/REL-9_18/pkg/docker/entrypoint.sh)
