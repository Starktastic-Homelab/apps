# Approved application-state cold backup

The user approved a backup-only application outage, reserving 30 minutes.
The window stopped existing VMs 200–202 gracefully, captured one recursive
`apps/pv` snapshot, and restarted those same VM generations. TrueNAS 100 and
runner 300 remained running. No NFS property, iSCSI resource, VM configuration,
image, or application deployment setting was changed.

## Outage and recovery evidence

The persistent shared maintenance lock was acquired on VM300 at 16:27:52 UTC.
Its private continuation and durable journal are under
`/var/lib/homelab-maintenance/operations/pre-nfs-backup-20260921T162744Z`.
The exact VM identities match the approved preflight report.

| Event | September 21, 2026, UTC |
| --- | --- |
| Master graceful shutdown requested / stopped | 16:28:06 / 16:29:51 |
| Worker 201 graceful shutdown requested / stopped | 16:30:15 / 16:32:02 |
| Worker 202 graceful shutdown requested / stopped | 16:32:06 / 16:33:41 |
| All writers absent | 16:34:01 |
| Cold snapshot created | 16:34:04 |
| Master start confirmed / API ready | 16:34:25 / 16:35:16 |
| Worker 201 / worker 202 start confirmed | 16:35:30 / 16:36:41 |
| Fresh node heartbeats and all 52 workload replica counts recovered | By 16:38:01 |

No forced shutdown or forced pod deletion was used. Writer checks required the
three exact VM generations stopped, zero established NAS NFS clients, and zero
local writable file descriptors beneath `/mnt/apps/pv`. Recovery used fresh
node leases and application readiness, rather than cached pre-shutdown status.
The shutdown-request-to-confirmed-recovery interval was about ten minutes.

Snapshot: `apps/pv@pre-nfs-standard-20260921T162744Z`.
Snapshot GUID: `10509111943305369503`; creation epoch: `1790008444`;
transaction group: `3937181`. Pool and dataset GUIDs remain those approved in
the preflight report. Dataset `sync` remained `DISABLED` during this operation.

## Backup scope and verification

A low-priority NAS-local archive reads only the immutable cold snapshot. Its
private staging directory is `/mnt/apps/.pre-nfs-backup-20260921T162744Z`, outside
the NFS export. The full source manifest contains 278,346 regular files, 100,366
directories, 40 symlinks and three stale qBittorrent Unix sockets. Regular-file
logical size is 81,956,862,143 bytes. The three sockets are runtime endpoints,
not persistent application state, and tar does not restore them. Their exact
paths are recorded in the private filesystem verification report.

The archive and restored tree match numeric ownership, modes, nanosecond
modification times, symlinks and file contents. ACL/xattr and hard-link options
were enabled, but this snapshot contains no extended attributes or hard links;
those cases were not exercised. The independent copy
uses CA-validated and leaf-pinned HTTPS to the approved encrypted laptop backup
root. Full extraction precedes content/metadata comparisons and independent database
checks. Database checks use further disposable copies and isolated containers, preserving
the original archive and initial restored tree.

Filebrowser's worker-local database is outside this snapshot. Audiobookshelf's
NFS files are copied but are not a mandatory application restore gate. Original
media on `main/media` and external sealing/Vault recovery material remain outside
this archive's coverage. This is not a complete NAS disaster-recovery backup.

## Verified results

The independent archive is retained at:
`/home/benf/Backups/homelab/pre-nfs-standard/20260921T162744Z/apps-pv.tar.zst`.
It contains 65,600,779,609 bytes (61.1 GiB), with SHA-256
`c6d01940982d48d8fd2a90554db77b8ef7c39d54c0f51f6172976b8bc3878507`.
The private backup directory is 0700 and the original archive is read-only (0400).
Source and received archive/manifest hashes matched; full extraction succeeded.
All 63 affected NFS claim directories are represented.

| Check | Result |
| --- | --- |
| Complete filesystem restore | All 378,752 persistent entries match; three runtime sockets excluded |
| SQLite | All 57 databases pass structural integrity and table reads; five fail the additional foreign-key check, described below |
| Shared PostgreSQL, exact production image | Cleanly stopped source; page checksums pass; nine databases, 542 tables, 586,789 rows read |
| Immich PostgreSQL, exact production image | Cleanly stopped source; page checksums pass; 71 application tables, 319,751 rows read; vector/vchord loaded |
| Jellyfin, exact production image | Healthy; same server identity, 14 users, catalog counts and plugin states; no tested SQLite/LiteDB error markers |
| Kodi Sync Queue LiteDB, exact plugin library | All documents readable: 7,295 items and 2,368 user-info records |
| Redis, exact production image | Multipart AOF/RDB check passes; all three checked files remain unchanged |
| Stirling PDF H2, bundled production library | Export and fresh import pass; all 22 tables read, 11 rows; no recovery-error comments |
| Zigbee2MQTT JSON database | Both records parse with unique IDs |
| Paperless Celery schedule | GNU dbm opens and all four values are readable; pickle contents were not executed |

The original root-directory manifest entry reflected snapshot mountpoint
metadata. The mounted immutable snapshot root, archive header and restored root
all independently matched each other. Only that reference entry was corrected;
no restored file was changed. The original manifest, initial failed comparison,
corrected manifest and reconciliation receipt are retained. Every other entry
matched the original manifest. The corrected manifest SHA-256 is
`ad795e69bdd3ce0a132779be4186dba6e77c5881d4be25af2902117f2e709c7f`.

Redis's checker required writable handles even without a repair flag. It ran on
a further disposable copy, and subsequent hashes proved its files unchanged.
The initial read-only attempt did not establish a database failure. The LiteDB
checker's initial compiler name collision was corrected before its successful
scan; the first attempt did not open the database.

Jellyfin's API comparison baseline was taken after the production restart. It
is useful restore evidence but does not substitute for the future iSCSI pilot's
required pre-hold API baseline. No external media was mounted into the isolated
Jellyfin test. Not every application or monitoring index was started independently;
general file coverage must not be presented as complete application acceptance.

## Existing application-data findings

These are foreign-key relationship failures, not SQLite structural-integrity
failures. The independent copies faithfully preserve the cold source.

| Active database | Finding |
| --- | --- |
| Autobrr | 23,663 release-action history rows reference absent actions; two reference absent filters |
| Calibre-Web | Four magic-shelf rows reference absent users |
| ConvertX | Six file-name rows reference absent jobs |

The Autobrr backup from September 16 already contains the same 23,665 violations;
its May 13 backup contains two. Thus the five strict SQLite-check failures cover
three active databases and two historical backups. No rows were deleted, no
repair was attempted, and no live application setting changed.

Autobrr v1.86.0 enables SQLite foreign-key enforcement only in its test environment
in [the upstream connection code](https://github.com/autobrr/autobrr/blob/v1.86.0/internal/database/sqlite.go#L68).
This supports treating the relationship findings separately from evidence of
filesystem corruption; it does not by itself explain every orphan's origin.
The Calibre-Web and ConvertX findings need application-level disposition too.
No complete critical-application acceptance receipt was issued, and this window
did not authorize the NFS durability change.

## Final disposition

All five original VM identities are running. All three node leases are fresh;
all 97 Deployments/StatefulSets, including the 52 affected workloads, have their
requested ready replica counts. The shared maintenance ownership was released
after reconciliation, with the durable VM300 journal retained.

The cold snapshot, encrypted independent archive, restored tree and private
verification receipts remain available. The exact task-owned NAS staging
directory was removed, reclaiming the redundant archive space. Test containers
were removed. `apps/pv` still has local `sync=DISABLED`; iSCSI remains stopped,
disabled and empty. No Packer build, VM replacement or storage cutover ran.

The [sanitized evidence](evidence/2026-09-21-cold-backup-window.json) records the
hashes, identity readbacks, claim coverage, checks, findings and operation timeline.
The next storage step remains gated on reviewing these application findings and
separately authorizing the durability change and its observation window.
