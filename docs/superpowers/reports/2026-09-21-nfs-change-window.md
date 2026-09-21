# Application backup coverage and proposed NFS durability window

## Decision requested

Approve a 45-minute supervised, online change of **only `apps/pv`**, from local
`sync=DISABLED` to local `sync=STANDARD`, with the existing Loki log-recovery
limitation accepted as an explicit exception to the complete-recovery gate.
The full Loki backup remains retained; no log deletion or repair is proposed.
Alternatively, keep this update pending while investigating Loki's semantic
WAL replay further. This proposal has not been executed.

The prior user approval covered the cold backup outage only. This new decision
covers a production storage behavior change and the newly verified Loki
limitation; it is not another request to approve the completed backup work.

## Completed backup coverage review

All 63 claims on the target dataset have a file-level restoration record. The
application/dependency inventory has 55 entries: 52 accepted for the scoped
backup-restoration prerequisite, two existing user exclusions (Filebrowser's
local DB and Audiobookshelf application acceptance), and one pending Loki
exception. These entries include the 52 affected workloads, Authentik's shared
PostgreSQL dependency, and the two stored backup/certificate claim inventories.
This is not a claim that all 55 are independently deployed applications.

The [full coverage matrix](evidence/2026-09-21-application-backup-coverage.json)
maps each claim and application to its actual checks. The earlier
[cold-backup report](2026-09-21-cold-backup-window.md) records the unchanged archive,
complete file comparison, native database checks and SQLite relationship review.

| Additional check | Actual result and limits |
| --- | --- |
| Prometheus, exact production image | All 17 source blocks reported healthy; WAL replay completed; queries at each block midpoint and near shutdown returned samples. No corruption/repair/error markers. Queries are bounded samples, not an exhaustive scan of every stored metric. |
| Alertmanager, exact production image | Ready; restored silence API opens with zero silences. No outgoing alert receiver is configured. |
| Karakeep Meilisearch, exact production image | Native store opens and reports zero indexes. That preserves the copied state; it does not prove Karakeep's indexing feature works. |
| Tempo, exact production image | Ready; nonempty WAL replays; historical search returns 100 traces. Source includes one empty WAL directory without metadata, discarded by both production and test recovery. A startup poll also raced with cleanup of an already-compacted block. |
| Loki, exact production image | Ready; historical query returns 1,000 entries across 62 streams, but WAL replay warns in both production and the restored copy. Exception remains explicit below. |
| Application file formats | 8,243 successful syntax/container checks: Home Assistant, Matter, Cineplete and changedetection JSON/gzip state, plus 3,897 qBittorrent torrent/resume pairs. No device connection, torrent announce or media payload validation was attempted. |
| Paperless search index | Files match the cold source. The index is derived from the tested PostgreSQL document records; native index rebuilding was not exercised. |

Paperless's exact-version [index rebuild command](https://github.com/paperless-ngx/paperless-ngx/blob/v3.1.3/src/documents/management/commands/document_index.py#L57)
reconstructs search data from database document objects. PostgreSQL state and the
files on `apps/pv` are the authoritative backup coverage here.

Seven claimed directories have no regular files, faithfully matching the source:
SearXNG, Listmonk's legacy claim, CWA book ingestion, Bytestash's legacy claim,
Mosquitto data, Mealie's legacy claim and Paperless's legacy claim. This is not
missing-copy evidence. Shared PostgreSQL coverage is mapped explicitly for
Authentik, Dispatcharr, Lingarr, Listmonk, Mealie, Paperless, Vaultwarden and Vikunja.

Initial isolated-test setup corrections are retained in private evidence:
Meilisearch needed its executable before flags; Tempo needed an explicit loopback
advertise address; Prometheus's first query landed in an empty lookback interval
near a historical block boundary, so the successful checks use block midpoints.
The initial Home Assistant JSON glob also selected two PEM files, subsequently
classified as ordinary byte-restored files. None of those is a source repair.

## Loki exception

The production restart at 16:36 UTC and the isolated restore both recover the
checkpoint without errors, then report segment replay errors. The source WAL
segment `00060003` is 1,245,184 bytes. An independent read-only scanner matching
the version's physical format verifies 291 CRC32C-valid fragments, 254 complete
records, valid padding and no torn record. It does not decode every application
payload or prove complete stream-reference replay.

The exact-version [recovery code](https://github.com/grafana/loki/blob/v3.6.11/pkg/ingester/recovery.go#L161)
can fail for logical stream-reference errors as well as damaged records. The
[startup logger](https://github.com/grafana/loki/blob/v3.6.11/pkg/ingester/ingester.go#L593)
prints a generic corruption warning without the underlying error. Therefore
this report does **not** claim proven physical corruption, nor complete recovery
of recent logs. The cold archive faithfully preserves the original bytes.

Approval would accept that existing log-history recovery limitation for this
NFS durability operation only. It would not authorize deleting Loki data,
disabling logging, or treating every future backup warning as acceptable.
The strict executable receipt currently remains a draft and is deliberately
rejected by `check_backup`. On approval, keep Loki's entire archive and exception
in the signed-off coverage record, and exclude complete Loki log-history recovery
from this operation's mandatory all-passed gate. The remaining 52 accepted entries
form the executable receipt; the two earlier user exclusions remain unchanged.
No validation code or general backup requirement needs weakening.

## Preparation verification

At 18:00 UTC, all five approved VM identities are running, all three nodes are
Ready and all 97 Deployments/StatefulSets have their requested ready replicas.
VM300 has no active maintenance marker. The 17:55 UTC NAS inspection confirms
the expected version, healthy ONLINE pools, local DISABLED and stopped/disabled
iSCSI with zero targets and extents. All task restore-test containers are removed.
Twenty storage-tool tests pass, and the incomplete receipt is verified to fail
closed. The full coverage/window review found no material issues.

This protection remains scoped to `apps/pv`. Original media on `main/media`,
including Immich uploads and Calibre's library, and external sealing/Vault
recovery material are outside this archive. The completed tests establish
restorable backed-up state, not full application behavior or media recovery.

## Exact operation and observation

Reserve 45 minutes after approval: ten minutes for baseline/ownership checks,
up to five minutes for the single update and readback, then at least 30 minutes
of observation. Workloads remain running; no VM shutdown, cluster replacement,
NFS restart, PV migration, iSCSI allocation, Packer build or database repair is
part of this window. Increased synchronous-write latency is the principal
operational risk. `STANDARD` restores normal handling of synchronous requests;
it does not make SQLite's network-filesystem locking safe. See the
[OpenZFS property documentation](https://openzfs.github.io/openzfs-docs/man/master/7/zfsprops.7.html#sync).

1. Recheck TrueNAS `25.10.7`, pool `apps` GUID `9917900421692286909` ONLINE,
   dataset `apps/pv` GUID `14547210392972608779`, no child datasets, and local
   `DISABLED`. Recheck the five approved VM identities and all three nodes.
   Confirm workload readiness, no unreviewed storage/data change, the retained
   snapshot/archive and private restore evidence. The archive's actual capture
   was **September 21, 16:34:04 UTC**, so the tool's 24-hour age limit is
   **September 22, 16:34:04 UTC (19:34 Israel time)**. If stale, refresh the
   prerequisite; do not relabel its creation time.
2. Acquire fresh ownership through the deployed VM300 maintenance helper.
   Pin the reviewed tool/helper hashes, receipt and plan in a new durable
   operation directory under `/var/lib/homelab-maintenance/operations/`.
   Record the approved Loki exception there. Never reuse the released backup
   operation's nonce or journal. Ownership blocks competing managed workflows;
   concurrent manual VM/storage changes must also remain suspended.
3. Under ownership, collect ten minutes of baseline node/workload readiness,
   restart counts, application storage-error counts, pool health and write
   latency. Use NAS `zpool iostat -l -p` interval samples, discarding its initial
   since-boot aggregate. Record raw units and compare busy samples; do not call
   idle averages a percentile or a load test. A short read-only qualification
   sample already confirmed the telemetry route works.
4. Run the reviewed `nfs_sync.py apply-standard` exactly once with its durable
   intent journal, accepted receipt and pinned TLS identity. It changes only
   `pool.dataset.update('apps/pv', {'sync': 'STANDARD'})`. Verify local STANDARD
   through a fresh identity-checked readback. If the response is lost or the
   operation fails, inspect and reconcile the same journal; never blindly retry.
5. Observe for at least 30 minutes, sampling workload/node readiness every
   minute, collecting pool I/O latency and reviewing new storage/database errors
   and restart counts. Compare with the recorded baseline, including existing
   Loki/Tempo startup warnings. No injected load or deliberate failure test is
   authorized by this window.
6. Treat new pool degradation/I/O errors, a node not ready, any affected workload
   below its baseline ready count for more than two minutes, new database
   corruption markers or sustained storage timeouts as a regression. Also flag
   average total write wait over both 100 ms and three times the busy baseline
   for three consecutive one-minute intervals. These are investigation triggers,
   not a performance guarantee. Keep STANDARD and the maintenance operation held
   while investigating; restoring DISABLED, restarting production or rolling back
   application data needs a separate decision.
7. On a reconciled, stable result, record final identities, local STANDARD,
   workload/error/latency comparisons and unchanged iSCSI state; release ownership.
   Preserve the archive, snapshot, receipts and durable journal. A healthy quiet
   window qualifies only the observed load; it does not claim long-term SQLite
   reliability or authorize the later Jellyfin iSCSI migration.

After this window, the next separately scoped stage remains the retained-iSCSI
pilot. This proposal does not authorize that stage.
