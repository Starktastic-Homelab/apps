# Remaining storage assessment

Read-only assessment on 18 October 2026. This report records running storage,
native configuration and pinned upstream behavior. It does not claim a migration,
backup, restore test, live repair or production rollout. The accompanying
[evidence](evidence/2026-10-18-remaining-storage.json) contains metadata only.

## Scope and recommendation

Use CSI for an actual database, index or demonstrated filesystem requirement.
An NFS PVC, a directory named `config`, or the use of PostgreSQL alone does not
justify moving ordinary files. Keep the existing unmodified Proxmox CSI driver,
static retained bindings, VM retirement fencing and unattended rebuild workflow.

| Workload | Verified remaining state | Recommendation |
| --- | --- | --- |
| Immich | Dedicated PostgreSQL 17.6 with VectorChord 0.4.3 and pgvector 0.8.1; live database directory is on NFS | Move only PostgreSQL storage to retained CSI, preserving the dedicated image and database identity. |
| Redis | Shared queue service; Git and mounted config say AOF on, running server says AOF off and scheduled RDB saves off | User selected queue preservation with AOF on CSI. Capture current memory safely before any restart; copying old disk files is insufficient. |
| Paperless-ngx | PostgreSQL plus a separate 34MiB data directory containing a Tantivy search index, model/runtime files and logs; no SQLite file found there | CSI for the private data directory is justified as a storage-contract improvement. Keep documents and consume inbox on NFS. Prepare it as a separate operation. |
| Calibre-Web Automated | Five SQLite databases across config and library directories; network-share mode enabled; all five file headers use rollback journal format, with no WAL/SHM sidecars observed | Rehearse stock split-library handling before selecting a migration. Candidate: CSI for config/database directories, NFS for books and shared ingest. |
| Mealie, Listmonk, Vaultwarden, Dispatcharr | Existing PostgreSQL integrations plus ordinary/private/shared files; no demonstrated additional database requirement from the current assessment | Keep their file storage on NFS. |
| Models and caches | Regenerable ML/model, translation, SearXNG and pip caches | No automatic retained-CSI migration. |

The next preparation is [Redis followed by Immich](../specs/2026-10-18-redis-immich-retained-csi-design.md).
Paperless and Calibre have separate preparation/acceptance boundaries. Existing
PostgreSQL enrollment adoption is a different follow-up; none of these changes
converts Immich to the shared PostgreSQL service.

## Immich

The running server is 3.2.2. Its dedicated pinned PostgreSQL image is
`ghcr.io/immich-app/postgres:17-vectorchord0.4.3-pgvector0.8.1@sha256:79b95b795f0911e95ffa4d092a2162c4d81a984d5629bc8f786afe0bc0657671`.
Native SQL reports PostgreSQL 17.6, physical system identifier
`7614955115223928876`, VectorChord 0.4.3 and pgvector 0.8.1. The full data tree
has about 348MiB apparent size; the Immich database reports about 246MiB.
The existing NFS claim requests 10GiB, which is the proposed retained-disk size.
No top-level or second-level data-tree symlinks were observed; complete tablespace,
WAL and link inventory remains a mandatory preparation gate.

The PostgreSQL Pod currently runs on the control plane. Its CSI replacement must
use the existing Linux worker placement and retirement contract. The owner of
`PGDATA` is UID999; preserve actual file ownership and modes rather than applying
a blanket ownership rewrite. Photos/videos and model cache remain on their
current NFS claims and keep their existing in-container paths.

[Immich storage requirements](https://docs.immich.app/install/requirements/)
advise against a network share for database files. This supports placing a guest
filesystem on a retained block disk; it does not remove the NAS as the underlying
infrastructure dependency. Its [backup guide](https://docs.immich.app/administration/backup-and-restore/)
also requires protecting both database metadata and original assets. Stop Immich
writers when establishing the coordinated recovery point; leave the live asset
layout unchanged.

## Redis

The running server is Redis 8.10.2. Its image reference is mutable `latest`, but
the actual running digest is recorded in the evidence. Preserve that exact image
and loaded modules during preparation and pin the current digest in the eventual
change; this is not an engine upgrade. Preserve the current exporter image too.

Fresh `CONFIG GET` and `INFO persistence` report:

```text
appendonly no
save ""
appendfsync everysec
aof_enabled:0
```

The StatefulSet starts Redis with the chart's included configuration files.
Both mounted and ConfigMap `redis.conf` contain `appendonly yes` and `save ""`.
Logs show successful AOF loading at the last process start and successful AOF
rewrites through 11 October. Old AOF base/incremental files remain on disk.
This establishes runtime/configuration drift, not its actor or reason. No
`CONFIG SET`, save, restart or correction was performed by this assessment.

Live client-to-Pod mapping confirms Immich and Paperless use database0 and
Dispatcharr uses database4, including blocking queue consumers. This is a
snapshot of connected clients, not proof of an exhaustive writer inventory.
Preparation must inspect configured but idle consumers before defining the
outage. Cache-only assumptions would discard actual job state.

The user selected **preserve queues with AOF on retained CSI**. Recovery must start
from a native export of current server memory after writers quiesce, not from
the historical AOF directory. The [Redis persistence guide](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)
distinguishes AOF, snapshots and disabled persistence and warns that simply
changing configuration and restarting can lose current data. A proven transition,
independent restore and current-state comparison precede any source shutdown.
The original runtime disable remains unattributed; final acceptance must verify
AOF remains enabled with consumers running, and loss of durability must be
observable without a liveness-triggered restart of volatile state.

## Paperless

The pinned Paperless 3.1.3 backend is Tantivy, not the older Whoosh implementation.
Native file inspection found an index directory and no SQLite file in the private
data tree. Its apparent sizes are about 34MiB data, 2.5MiB media and an empty
consume directory at inspection.

The [pinned backend](https://github.com/paperless-ngx/paperless-ngx/blob/v3.1.3/src/documents/search/_backend.py)
serializes multiple application processes with a file lock and opens a fresh
on-disk index for each write. Tantivy's
[MmapDirectory documentation](https://docs.rs/tantivy/latest/tantivy/directory/struct.MmapDirectory.html)
warns that NFS implementations may not honor its lock contract. This is a
concrete reason to prefer a guest filesystem for the index. It is not evidence
of observed corruption or a failed lock on this particular NFS installation.

A separate preparation should move only `/usr/src/paperless/data` to a retained
volume, retaining PostgreSQL, `/usr/src/paperless/media`, polling-based consumption
and `/usr/src/paperless/consume`. Verify the complete native index/model and query
behavior on recovered copies. Inspect the inherited `/config` claim before
disabling an unused mount; do not delete a source PVC or its data as cleanup.

## Calibre-Web Automated

The installed image is stock CWA 4.0.6. `/config` contains `app.db`, `cwa.db` and
`gdrive.db`; `/calibre-library` contains `metadata.db` and `.calnotes/notes.db`.
Their observed headers use SQLite rollback-journal format. Config is about 7MiB,
the current library tree about 2.3MiB and shared ingest empty at inspection.
File/header inspection is not a SQLite integrity or conversion test.

The [pinned compose example](https://github.com/crocodilestick/Calibre-Web-Automated/blob/v4.0.6/docker-compose.yml)
describes network-share mode's WAL, ownership and polling adaptations. Its
[native settings](https://github.com/crocodilestick/Calibre-Web-Automated/blob/v4.0.6/cps/config_sql.py)
include separate database and book-library paths; the
[ingest implementation](https://github.com/crocodilestick/Calibre-Web-Automated/blob/v4.0.6/scripts/ingest_processor.py)
sets `CALIBRE_OVERRIDE_DATABASE_PATH` when split mode is enabled. This offers a
stock candidate that can keep books and ingest on NFS while moving all SQLite
state to CSI.

Do not declare this candidate qualified from source inspection. Rehearse the
exact image's web library, book import/conversion, metadata updates, covers,
notes and every enabled integration on synthetic/offline copies. Some helpers
use the fixed `/calibre-library/metadata.db` path, so retain that as the database
mount and put book files at the separately configured path. Do not mount a
single SQLite file using `subPath`; its journals must share the same filesystem.
No source database relocation or settings change has occurred.

## Capacity and evidence boundaries

NAS dataset `apps/k3s-block`, GUID13918781591004512447, has a 288GiB quota and no
reservation. The pool was ONLINE. There are39 active raw images totaling214GiB
logical capacity. The historical Jellyfin partial remains present and unchanged;
its allocated bytes remain included in dataset usage.

Fresh measurements leave roughly23GiB for new logical allocation after full
growth of existing raw images,512MiB staging and8GiB spare. Redis2GiB plus
Immich10GiB therefore fit the current conservative budget. Every actual
allocation must repeat the complete dataset and physical-pool check; this is
neither an allocation nor a growth guarantee for later operations. No quota or
reservation change is proposed.

The inventory did not read application records, Redis key values or credential
values into its output. No application data was copied to a lab or workstation.
The temporary probes inspected metadata/configuration through the existing
verified read-only transport. Production backup, native restore, worker movement,
GitOps acceptance and full-cluster rebuild remain distinct evidence gates.
