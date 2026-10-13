# Prowlarr PostgreSQL: real-data qualification

The pinned stock Prowlarr application passed main-database conversion, restricted
owner-role operation, restart and independent PostgreSQL restore in a disposable
offline VM. Production remains SQLite on its original NFS claim. This report
does not authorize a production outage, enrollment, allocation or activation.

The user selected fresh PostgreSQL diagnostic logs. Preserve the old diagnostic
logs in the full encrypted recovery archive and original source; do not import
them. Search history is in the main database and remains part of the migration.

## Results

The [sanitized evidence](evidence/2026-10-13-prowlarr-postgresql-qualification.json)
contains image pins, table counts, acceptance outcomes and cleanup verification.
It excludes credentials, private records and hashes derived from configuration
or credential-bearing rows.

| Check | Observed result |
| --- | --- |
| Source | Existing scheduled ZIP containing main DB, config.xml and INFO; cached definitions captured separately |
| SQLite | ZIP CRC and integrity passed; zero foreign-key violations, invalid UTF-8 fields or NUL-containing text fields |
| Isolation | Fresh VM980, no physical NIC, no production mounts or PostgreSQL credentials; exact production images |
| Conversion | Stock app created schema; pinned PGLoader loaded data only with quoted identifiers; no loader errors or omitted rows |
| Main data | All 20 tables and every typed field matched, including 268,864 History rows and 45 application-indexer mappings |
| IDs | All 19 main allocators checked against current IDs and SQLite's historical high-water marks, including empty tables |
| Settings | 20 indexers, five applications, one download client, one indexer proxy, one notification, three tags, one app profile and one custom filter |
| Stock application | PostgreSQL backend, original API key usable, settings preserved, test tag ID4 created and deleted |
| Permissions | Separate restricted main/log owners; no superuser, CREATEDB or CREATEROLE; owner-role VACUUM and exact newly requested Housekeeping completed |
| Connections | Five-connection cap per pool; two main and one log connection observed |
| Restart | Clean restart retained the protected settings and credentials |
| Recovery | Both stopped-writer PostgreSQL dumps restored into fresh physical data storage; every table's row count and SHA256 fingerprint matched before app startup |
| Restored writes | 19 main and two log allocators verified; next tag received ID5 and was deleted; protected settings still matched |
| Cleanup | Lab VM, its two disks, private ISO and staged private inputs removed; maintenance owner released |
| Production | Same Pod/container, Deployment, NFS binding and configured API entities; Healthy/Synced; no Prowlarr PostgreSQL roles or databases |

Date/time comparisons use PostgreSQL's native cast, independently of PGLoader.
The SQLite values can have seven fractional digits; PostgreSQL stores microseconds.
This establishes preservation at the target engine's precision, not byte-exact
preservation of 100ns timestamps. No SQLite source values were edited or rewritten.
Normal stock background Commands and Logs writes advanced those two sequences
after restored-app startup; all other restored sequence values matched exactly.

## Qualification limits

Prowlarr's [upstream guide](https://wiki.servarr.com/prowlarr/postgres-setup) supports
fresh PostgreSQL installations and marks existing SQLite conversion unsupported.
This successful local rehearsal does not change that support boundary. The stock
application and converter were not forked or patched.

The rehearsal used a scheduled main backup, not the complete current production
directory. It excludes old logs.db and filesystem logs. Before production release,
stop every source writer, capture the complete directory including WAL sidecars,
retain a verified encrypted archive outside the NAS and recheck the latest main
data. Do not use the scheduled ZIP as the cutover source.

The offline lab could not test real indexer searches, application synchronization
or download-client connections. They remain production acceptance checks. The
per-app retained-config startup guard and composition of two existing consumer
gates remain preparation work. Generic PostgreSQL enrollment, shared retained
storage and full-cluster replacement need not be requalified for this app.

The probe needed corrections to lab CPU requests, final-server readiness, empty
sequence result handling and verification fingerprints. The pinned PostgreSQL
image rejected the original MD5 check, so restore comparison used bounded per-row
SHA256 fingerprints. Failed guest operations were inspected and continued from
their recorded checkpoints. These were probe corrections, not application fixes.

Protected operational receipts remain under the VM300 operation
`/var/lib/homelab-maintenance/operations/prowlarr-postgresql-20261013/receipts/`.
The private source and media copies have been deleted. The original NFS data and
scheduled backups remain untouched.

## Next operation

The [cutover proposal](../specs/2026-10-13-prowlarr-postgresql-cutover-design.md)
uses fresh diagnostic logs, the qualified main conversion and the existing live
migration workflow. Its preparation merge changes documentation only. Production
execution requires the reviewed concrete package and a separately approved outage.

References: [pinned connection handling](https://github.com/Prowlarr/Prowlarr/blob/v2.6.5.5623/src/NzbDrone.Core/Datastore/ConnectionStringFactory.cs),
[PGLoader SQLite options](https://pgloader.readthedocs.io/en/latest/ref/sqlite.html),
[PostgreSQL timestamp resolution](https://www.postgresql.org/docs/18/datatype-datetime.html).
