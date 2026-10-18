# Immich PostgreSQL native recovery qualification

Preparation only. Production databases, credentials, workloads and storage are
unchanged. Task 2’s exact-image synthetic fixtures passed on 18 October 2026;
final package review and separate execution approval remain required.

The engine is the pinned Immich PostgreSQL 17.6 image with VectorChord 0.4.3
and pgvector 0.8.1. Fixtures use its actual wrapper, configuration, UID999,
native binaries and data checksums. They run disconnected with synthetic records
and credentials, using exact owned Docker resources that are removed afterward.

## Preservation proof

Native pg_dump/pg_dumpall and repeatable-read read-only psql transactions capture
all databases, schemas, table columns/content, duplicate rows, binary/non-ASCII
values, vectors, migration rows, sequence floors, roles and password verifiers.
Private records and dump files are never published. Comparisons exclude only the
unpredictable psql safety token from dump digests; original native dumps remain
untouched. Quiescent writers remain a mandatory production prerequisite.

A clean full cold archive and physical restore preserve the independently
recorded system identifier and every logical proof. The archive preserves
ownership, modes, nanosecond modification times and xattrs; complete cold-tree
hashes match before PostgreSQL starts. A separately initialized logical restore
has a different physical identity and the same logical state. Only its duplicate
bootstrap-role CREATE is omitted; every native ALTER, including its password
verifier, is applied and compared. No data conversion exemptions are used.

## Startup guard and stock recovery

Nineteen fault cases refuse wrong identity/version, missing/empty/unreadable data,
linked data/WAL/control/version, missing/truncated/unreadable control files,
CRC warnings despite native exit0, standby/recovery signals and dangling signals.
The guard runs non-root against read-only data. Before/after byte and metadata
hashes match, including when it refuses startup.

A stale PID is left untouched by the guard and handled by stock startup. An
actual abrupt process death with committed WAL also recovers through the stock
engine; all native proofs pass afterward and sequence floors never decrease.
This relies on the separately required RWOP and verified VM-retirement fencing.
Production definitions must pin the known physical identifier
`7614955115223928876`, without learning it from a candidate disk.

The dedicated cluster’s closed-root contract rejects external symlinks and
foreign tables. Fresh production inventory must reverify complete WAL/tablespace
and writer scope before execution. This preparation uses no original photo/video
files; coordinated asset recovery and existing-asset/API acceptance remain
production gates.

## Reproduce

```bash
python3 scripts/test-redis-immich-state.py
python3 scripts/test-redis-immich-native.py --app immich
```

Nine state tests and two native PG17 tests passed. Each native invocation executes
the complete physical/logical and fault batch once; named case access reuses only
that invocation’s finished metadata, after cleanup. No real cluster rebuild or
CSI placement change is claimed by this engine qualification.
