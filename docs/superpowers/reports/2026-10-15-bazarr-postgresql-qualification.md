# Bazarr PostgreSQL and retained CSI qualification

Qualified October15,2026 against a consistent online copy of production state.
Production remains SQLite/NFS at this checkpoint; this report does not claim a cutover.
The execution packet still needs its final review before enrollment and downtime.

## Accepted evidence

The disposable VM980 has2 CPUs,3GiB RAM,12GiB disk and no physical NIC. Its
stock k3s/Bazarr/PostgreSQL/pgloader image digests match the approved pins. It
cannot reach production integrations or NAS media. PostgreSQL credentials are
fixture-only; the copied Bazarr settings contain existing credentials and remain
root-only in the offline lab/temporary media. No private data is committed.

The online SQLite native backup included committed WAL and passed integrity and
foreign-key checks. The recovered SQLite copy started under stock Bazarr1.6.1;
its API reported128 series,259 movies,37,900 episode-history rows,2,067 movie-history
rows and1 language profile. Production remained Healthy/Synced during the copy.

All16 application tables (59,233 rows) passed exact typed comparison, including
binary caches, Unicode, booleans, mixed-case columns and timestamp precision.
The stock Alembic revision537e9b4d10e3,85 constraints including13 foreign keys,
and83 indexes remain exact. Actual generated sequences meet the source floors,
including deleted IDs; no allocator is invented for a non-generated key.

A custom PostgreSQL dump restored into a separate fresh physical PostgreSQL18.6
data directory under the ordinary bazarr database owner. Every typed field and
source allocator floor matched again. Stock Bazarr started and restarted against
that restore. All YAML settings and credentials remained semantically unchanged
except postgresql.enabled=true; no active SQLite file was recreated. A disposable
announcement received a generated ID above its source floor and was then removed.

## Corrections established by the rehearsal

The pinned loader's automatic sequence reset double-quotes a mixed-case column
name and aborts before reinstalling foreign keys. That initial fixture was rejected:
its rows matched, but all13 foreign keys were missing. A separate fresh physical
fixture succeeded with the documented reset no sequences option and explicit,
discovered-sequence floor restoration. The production procedure must use that
qualified combination and compare the complete stock constraint/index contract.

The API history endpoints are episodes/history and movies/history. The initial
wrong URLs returned the SPA HTML page with HTTP200; acceptance now requires JSON.
The original failed operation/fixture evidence remains distinct from the continuation.

The retained SQL guard now counts catalog base tables and rejects an unexpected
public table even when another owner hides it from information_schema. Native
positive/extra-table/wrong-role tests passed against the actual retained fixture;
CI also tests empty, missing, incomplete and wrong-revision synthetic states.

The production-sized proof also passed using stock psycopg2 beside the data under
a512MiB limit (about269MiB peak). Cold population/settings passed on disposable
ext4 with exact metadata/hashes and omitted active SQLite files. Stock schema
initialization and Kubernetes runtime retirement matched the same85 constraints
and83 indexes. The temporary initializer receives only its database credential.

## Production conditions

Use the latest fully stopped source, not the online rehearsal snapshot. Require
independent cold-tree recovery, exact typed/schema/allocator proof, SQL recovery,
verified writer/VM fencing, capacity checks and one90/180-minute outage clock.
The runtime ARC cap was temporarily lowered to10GiB with explicit approval and
passed the unchanged6GiB lab capacity gate. Restore its exact original value
immediately after owned lab removal. No persistent host setting was changed.

Media/subtitles stay on NFS. Retained private configuration will use the fixed
4GiB ext4/RWOP/Retain CSI binding. Enrollment uses the existing hook and consumer
gate. PostgreSQL-mode Bazarr ZIPs contain configuration only; shared SQL backup
and qualified SQL/config recovery provide database recovery.

The production merge, live acceptance, worker movement, final backup, six-minute
merged-main reconciliation watch and exact temporary cleanup remain required.
