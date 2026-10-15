# Bazarr PostgreSQL and retained CSI preparation

This package implements the [approved design](../../docs/superpowers/specs/2026-10-15-bazarr-postgresql-csi-design.md).
Preparation sources remain outside ApplicationSet discovery until accepted cutover.
Use the existing PostgreSQL enrollment hook and private generated SealedSecret bundle.
Never regenerate a completed or ambiguous credential output. No plaintext credentials
or recovery data belongs in Git.

The read-only retained guard checks the instance marker, existing YAML/API/session
identity, canonical PostgreSQL environment and no active SQLite files. The pinned
Bazarr image supplies its own YAML parser; no application configuration module is
imported. Both `POSTGRES_ENABLED` and `config.yaml/postgresql.enabled` must enable
PostgreSQL because stock backup uses the latter independently. All other retained
settings and existing credentials are preserved.

`data.py` materializes committed WAL through SQLite's native backup API and compares
all16 application tables using the actual PostgreSQL column types and discovered
sequences. Preserve stock Alembic revision537e9b4d10e3; loader must exclude that ledger.
Follow the documented data-only/quoted-identifier/timestamp conversion with `reset no sequences`;
the pinned loader automatic reset mishandles mixed-case column names and prevents
foreign-key restoration. Raise discovered sequence floors explicitly, reject errors
and verify every row/field, constraints, binary caches and generated allocator floors.
A checkpointed live-file count or successful pgloader exit is insufficient.

Stock PostgreSQL-mode ZIP backups contain settings, not PostgreSQL data. The shared
PostgreSQL backup and qualified SQL/config recovery procedure provide database recovery;
Bazarr's SQLite-oriented ZIP restore UI is not that path. Keep original protected NFS
sources and encrypted cold/SQL recovery outside Git. Never reopen stale SQLite after
new PostgreSQL writes.

Generate inactive sources with `python3 scripts/bazarr-postgresql/prepare.py sources`.
Run `python3 scripts/test-bazarr-retained-startup.py`; actual chart and real offline
conversion/recovery qualification remain required before any production claim.
