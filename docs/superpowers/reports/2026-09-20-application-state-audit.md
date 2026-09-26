# Application-state audit: live placement, incidents and lab capacity

Observed 2026-09-20, approximately 18:03–18:16 UTC. Scope: read-only production
inspection and local documentation. No VMs, storage, snapshots or diagnostic
pods were created; no workloads, credentials or host settings were changed.

## Findings that change the next step

1. **SQLite on NFS is widespread:** SQLite file headers were confirmed on NFS
   for 15 media workloads and eight additional application/infrastructure
   groups. This establishes exposure, not that all these files are active or
   that NFS caused every service failure.
2. **Jellyfin still has live contention:** four matching SQLite lock log lines
   form one burst at 16:34:27.952–.955 UTC today, near a readiness failure.
3. **Contention extends beyond Jellyfin:** seven-day Loki queries also find
   SQLite busy/locked matches for Sonarr and Sonarr RU. Probe failures affect
   several more services; SQLite errors are not established for all of them.
   All audited current containers were Ready with zero restarts.
4. **Whole-cluster recovery already has non-NFS gaps:** Filebrowser stores its
   authoritative database on a worker disk; Audiobookshelf metadata is on the
   container filesystem; Mosquitto's configured persistence path is missing.
5. **The selected Proxmox host has disk headroom but a RAM constraint:** about
   136GiB allocatable on vm-pool, about 5GiB host MemAvailable, no swap and
   ballooning disabled for the NAS and three K3s VMs. Do not start the proposed
   18GiB lab on the strength of configured-memory overcommit alone.

## Access and baseline

The user supplied the existing SSH key and fetched kubeconfig. Kubernetes API
access works at `10.9.9.50:6443`; all three nodes are Ready on `v1.37.0+k3s1`.
The key does not authorize root SSH to Proxmox. The user then supplied a local
password-file reference for root, which enabled read-only SSH queries.

The Proxmox SSH host key was first-contact recorded, then strictly checked on
subsequent connections. It was not independently fingerprint-verified. Password
contents were neither printed nor copied into these artifacts; temporary
askpass helpers were deleted automatically. The user-owned password file was
left in place.

At the first node metrics sample: master memory working set 5,460MiB,
worker-01 10,958MiB and worker-02 19,526MiB. These are guest/container metrics,
not memory that the Proxmox host can automatically reclaim. They are not
sufficient evidence for reducing production VM allocations.

## Storage inventory

All **68 PVCs are Bound**: 62 use `nfs-pv`, four use static NFS PVs with empty
class, and two use `local-path`. The 66 NFS PVs use Retain; the two local PVs use
Delete. Exact claim/PV/backend/consumer/image/mount/node mappings are preserved
in [sanitized bindings](evidence/2026-09-20-storage-bindings.json).

The two local claims are:

| Claim | Live node | Actual role | Recovery consequence |
|---|---|---|---|
| `media/jellyfin-cache` | worker-02 | `/config/cache` on local ext4 | Disposable-cache placement pins the pod; earlier handoff's worker-01 statement is stale |
| `operations/filebrowser-data-pvc` | worker-01 | `/home/filebrowser/data` on local ext4 | Authoritative application metadata is not retained outside the replaced VM |

Shared PostgreSQL `/bitnami/postgresql` is actually mounted from
`10.9.8.30:/mnt/apps/pv/databases/data-postgres-postgresql-0` using NFSv4.2,
TCP and **hard**. The live `nfs-pv` class and dynamic PVs do not contain explicit
mountOptions, despite the source values listing them. Effective mountinfo is
the evidence for `hard`; source intent alone would not prove it. Server stable-
write behavior and current PostgreSQL durability settings were not rechecked.

## Database placement confirmed without opening databases

Existing pod reads used selected mount metadata, file metadata, 16-byte format
headers and database-only open-file symlinks. No SQL clients, PRAGMAs, database
copies, configuration changes or full environment dumps were used.

| Application/group | SQLite files observed on NFS | Evidence beyond file existence |
|---|---|---|
| Sonarr and Sonarr RU | `/config/sonarr.db`, `logs.db` | SQLite header and NFS mount |
| Radarr and Radarr RU | `/config/radarr.db`, `logs.db` | SQLite header and NFS mount |
| Lidarr | `/config/lidarr.db`, `logs.db` | SQLite header and NFS mount |
| Prowlarr | `/config/prowlarr.db`, `logs.db` | SQLite header and NFS mount |
| Bazarr | `/config/db/bazarr.db` | SQLite header and NFS mount |
| Autobrr | `/config/autobrr.db` | Active database/WAL descriptors |
| Navidrome | `/config/navidrome.db` | Active database/WAL descriptors |
| Audiobookshelf | `/config/absdatabase.sqlite` | Active database descriptor |
| Cleanuparr | `/config/cleanuparr.db`, `users.db`, `events.db` | SQLite headers and NFS mount |
| Seerr and Seerr RU | `/app/config/db/db.sqlite3` | Active database/WAL descriptors |
| Jellyfin | `/config/data/data/jellyfin.db`, `playback_reporting.db`, three IntroSkipper DBs | SQLite headers plus current Jellyfin SQLite error |
| Calibre-Web Automated | `/config/app.db`, `gdrive.db`, `cwa.db`; library `metadata.db` and `.calnotes/notes.db` | SQLite headers on config and media NFS mounts |
| Home Assistant | `/config/home-assistant_v2.db` | Active database descriptor |
| ntfy | `/var/lib/ntfy/user.db`, `webpush.db`; `/var/cache/ntfy/cache.db` | Active database descriptors |
| Excalidash | `/app/prisma/dev.db` | SQLite header and NFS mount |
| Karakeep | `/data/db.db`, `queue.db` | Active database descriptors |
| Bytestash | `/data/snippets/snippets.db` and a backup DB | Active database descriptor |
| ConvertX | `/app/data/mydb.sqlite` | Active database descriptor |
| CrowdSec | `/var/lib/crowdsec/data/crowdsec.db` | Active database descriptor |
| pgAdmin | `/var/lib/pgadmin/pgadmin4.db` | SQLite header and NFS mount |

Variants count separately in the 15 media workloads. A DB header proves format,
not integrity, journal mode or whether an old file remains authoritative.
Observed WAL descriptors are not a complete journal-mode inventory.

Grafana's 14,974,976-byte `grafana.db` is on its NFS claim, but header inspection
was unavailable: its image lacks `sh`, and the Filebrowser user cannot read the
file. Keep the engine classified as inferred, not live-verified.

Repository-configured PostgreSQL consumers include Authentik, Vikunja,
Paperless, Lingarr, Dispatcharr and Mealie; Immich uses its separate PostgreSQL.
Vaultwarden and Listmonk DB configuration is Secret-injected and was not read;
their PostgreSQL usage remains handoff-reported. Native SQL migration does not
preserve attachments, uploads or other files on their claims automatically.

## Immediate preservation concerns

- **Filebrowser:** its 131,072-byte main `database.db` has a non-SQLite header;
  its 243,220,480-byte `cache/sql/index_all.db` is SQLite. Both are on worker-01's
  ext4 `/dev/vda1` through local-path. The main metadata needs external
  persistence or a verified restore contract before destroying that worker.
- **Audiobookshelf:** `/metadata` is overlay-backed and has no volume mount.
  It contains logs, streams, cache and backups. Classify which contents are
  rebuildable and which must survive; the NFS `/config` database does not cover
  this path.
- **Mosquitto:** live configuration sets `persistence true` and
  `persistence_location /config/data/`. `/config` and `/config/data` do not
  exist. The NFS claim is mounted at `/mosquitto/data`, with no observed
  `mosquitto.db` there either. This verifies a path mismatch, not whether any
  particular retained message has been lost.
- **Calibre:** the shared library at `/mnt/main/media/library/books` contains
  SQLite metadata as well as books. A config-only block migration would leave
  database files on NFS. Review all writers and application-specific library
  sharing before choosing its migration scope.
- **Jellyfin:** Kodi Sync Queue files have non-SQLite headers. The handoff
  identifies LiteDB; preserve them alongside SQLite and plugin state.

## Incident evidence and limits

Current pod logs supplied 21,281 lines across 14 containers. The seven-day
request was limited to 15,000 lines/8MB per container and, more importantly,
the lifetime of the current pods, all created today. Prowlarr reached its line
cap. Raw logs were parsed in memory and not saved. See
[sanitized incident evidence](evidence/2026-09-20-storage-incidents.json).

Jellyfin's four matching log lines at **16:34:27.952–16:34:27.955 UTC** include
SQLite Error 5 / database-is-locked signatures. Category counts overlap; this
is one tight burst, not eight errors. A readiness-failure event series began
at **16:34:23 UTC**. The timing suggests a relationship but proves no direction
of causation and does not identify NFS as the cause.

| Application | Readiness failure count | Liveness failure count | Retained event interval, UTC |
|---|---:|---:|---|
| Jellyfin | 39 | 34 | 15:24–17:59 |
| Lidarr | 86 | 91 | 11:19–17:26 |
| Prowlarr | 52 | 40 | 10:44–17:49 |
| Radarr | 75 | 76 | 10:52–17:28 |
| Radarr RU | 61 | 47 | 16:42–18:02 |
| Sonarr RU | 187 | 149 | 10:44–18:02 |

These are aggregated failed checks, not counts of outages or restarts. Every
audited current application container was Ready with zero restarts. Probe
failure threshold 30 allows intermittent failures without container restart.
No matched SQLite busy/locked signatures appeared in the other sampled
application logs; no matched corruption/disk-IO/cannot-open/full signatures
were found. Missing signatures and limited historical coverage are not proof
that other databases are healthy.

### Historical follow-up through existing monitoring

Loki queries over the seven days ending approximately 18:13 UTC returned these
SQLite busy/locked **matching-line counts**: Jellyfin 370, Sonarr 2 and Sonarr
RU 8. Multiple lines can describe the same incident. Other selected application
labels produced no matches; label filtering and retention limit coverage.

There were also 24 Jellyfin lines with generic `Input/output error` between
September 18 00:00:12 UTC and September 19 00:00:36 UTC. None of those same lines
identified a database or matched the corruption-specific patterns; do not
classify them as database corruption.

Existing Prometheus history supplied 337 samples at half-hour intervals.
Sampled NFS RPC retransmission increases were zero, and sampled Kubernetes
MemoryPressure/DiskPressure/PIDPressure conditions were false. Coarse cluster
I/O-stall and failed-probe series did not show a positive contemporaneous
association. These observations do not exclude slow NAS responses or short,
per-node/per-application stalls. Guest block-device latency is not NFS operation
latency; NFS per-operation latency metrics were not exposed in metric discovery.

Guest memory extrema use all retained scrape samples in seven-day range
queries, not the half-hour sampling used for the separate pressure history:

| Guest | Minimum available over 7d, GiB | Available at query, GiB | Current OS total, GiB |
|---|---:|---:|---:|
| master-01 | 5.376 | 9.508 | 15.624 |
| worker-01 | 12.710 | 18.463 | 27.413 |
| worker-02 | 13.177 | 15.949 | 27.413 |

These guest observations inform a later memory arrangement but do not authorize
or by themselves validate shrinking production VMs. See
[sanitized historical evidence](evidence/2026-09-20-storage-history.json).

## Recovery dependencies outside the PVC inventory

This inventory does not certify recovery of Sealed Secrets private keys,
external credential/Vault material, application state outside declared mounts,
or the Kubernetes datastore. Source shows the bootstrap key-restoration path;
this audit did not verify the external key backup or decrypt/reconstruct a new
cluster. The intended fresh-cluster rehearsal regenerates Kubernetes identities
and may regenerate join tokens instead of restoring the old K3s datastore.
Prove that reconstruction path and externally retained secrets explicitly;
fixing the application gaps listed here alone is not whole-cluster acceptance.

A selected-field scan of Deployments, StatefulSets and DaemonSets found declared
hostPath mounts only for CrowdSec log collection, Falco host inspection,
the Intel GPU plugin and node-exporter. It does not cover all possible pod types
or prove that important application state cannot be written to container layers.

## Backup evidence

The NFS PostgreSQL backup directory contains nine gzip archives. One,
`pg_dumpall_2026-09-15_230144.sql.gz`, is 20 bytes. It passes `gzip -t` and
decompresses to **zero bytes**. It is not a usable SQL backup. The other eight
are roughly 32.2–45.4MB; size alone establishes neither completeness nor
restorability. The latest observed file is dated September 19.

The existing producer-pipeline bug was freshly reproduced locally with a
producer exiting 23: the shell reports success because gzip succeeds, leaving
valid empty gzip output. The temporary reproduction was removed. The production
script and retained backups were not changed.

The handoff reports one independent PostgreSQL restore on September 19. Its
retained evidence is unavailable here and no new restore was run. Backups and
restore evidence for the embedded-database applications remain to be verified
before migration. Preserve the invalid archive as diagnostic evidence.

## Proxmox lab feasibility

The user selected production host `10.9.9.20:8006` and explicitly accepted
temporary RAM overprovisioning. This supersedes the earlier separate-machine
assumption, but does not make production reboots, VM resizing or host tuning
part of the audit.

The user subsequently allowed a temporary runner shutdown and requested a
careful proposal for other VM reductions, using Terraform PRs for K3s VMs.
The [RAM proposal](../specs/2026-09-20-iscsi-lab-memory-proposal.md) recommends
keeping TrueNAS at 32 GiB and the master at 16 GiB, reducing each worker from
28 to 20 GiB, and stopping the runner after CI completes. The user approved
the allocation and then requested both workers in one PR, proposing full
destruction/recreation as the execution path. Terraform PR #222 had a verified
two-worker memory-only plan and passed CI before the execution-path decision.
The user subsequently selected and confirmed destroy/recreate, accepted
potential Filebrowser/Audiobookshelf state loss, and merged PR #222. All three
K3s VMs have been recreated and Terraform/Ansible passed; see the
[execution report](2026-09-20-cluster-rebuild-memory.md) for recovery progress.
The audit findings above describe the pre-rebuild inventory.

| Observation | Value |
|---|---|
| Host physical RAM | 125.55GiB |
| Host reported available RAM | 4.97GiB at 18:08 UTC; about 5.13GiB at 18:09 |
| Host swap | None |
| Configured max RAM of running VMs | 108GiB |
| Host ZFS ARC current/minimum | 12.45GiB / 3.92GiB |
| Potential ARC reduction to current minimum | About 8.53GiB; not already free and not a guaranteed instantaneous reclaim |
| Ballooning | Disabled for TrueNAS and all three K3s VMs; runner minimum 1GiB/max 4GiB |
| vm-pool allocatable space reported by Proxmox | 136.13GiB |
| vm-pool raw pool free reported by zpool | About 382GiB; do not use this in place of allocatable space/reservations |
| Root pool | 86% allocated; avoid putting lab VM disks there |
| Existing bridges | vmbr0 and vmbr1 both have physical uplinks |
| Active Proxmox tasks at sample | None |
| Recent host memory PSI averages | Zero at sample; not a capacity guarantee |

See [sanitized capacity evidence](evidence/2026-09-20-proxmox-capacity.json).

The original 18GiB guest budget exceeds current available RAM even if ARC
shrinks to its present minimum. A smaller 12GiB lab (8GiB NAS, 2GiB server and
two 1GiB workers) would still leave too little allowance for QEMU overhead,
production growth and host reserve under that arithmetic. That smaller guest
budget is a proposal, not a validated TrueNAS/K3s workload configuration.

The approved memory arrangement and subsequent rebuild are recorded in the
execution report linked above. No ballooning, swap, ARC-limit or NAS-memory
change was approved or performed. During lab execution, staged starts, resource
ceilings and an external shutdown guard supplement adequate initial headroom;
they are not a substitute for it.

Use a new test-only bridge without a physical uplink, unique test VM/disk IDs,
`onboot=0`, disks on vm-pool and no access to production NAS data. Review
management/installation access separately. Do not reload the existing host
network or use a production bridge as the storage-test network. Fault injection
must target test VMs/network only, never the shared hypervisor or physical NICs.

## Prioritized next work

1. Protect Filebrowser metadata and correct verified persistence-path gaps
   before any destructive cluster lifecycle. Prepare separate small reviewed
   changes with state-preserving migration where needed.
2. Correct PostgreSQL backup failure handling independently and verify a new
   restore. Do not expand PostgreSQL usage based only on job success.
3. Use Jellyfin plus Sonarr as the provisional application pilots: both now
   have historical contention evidence and represent different application
   stacks. Navidrome remains a simpler alternate with confirmed active SQLite/
   WAL usage, without demonstrated contention in the sampled logs. Keep the
   first platform test synthetic; application copies belong to the later phase.
4. Build the reusable isolated CSI rehearsal after settling the shared-host
   memory/network envelope. Preserve the full acceptance matrix in the design.
5. Only then perform separately scoped real-NAS/application comparisons and
   choose per-service native PostgreSQL versus retained block migration.

## Review and validation

A fresh reviewer checked binding counts, evidence limits and memory arithmetic.
The report now explicitly covers unaudited external recovery dependencies;
the historical evidence includes executed query expressions and time windows.
Local checks validate documentation links, JSON syntax, whitespace and absence
of conflict markers/placeholders. Pre-commit is unavailable in this environment.
No rollout test, new database restore or lab VM execution was performed.

This audit validates placement and identifies risks. It does not certify
database integrity, complete recovery, physical-NAS performance or a rollout.

Later phase: [isolated retained-iSCSI rehearsal](2026-09-21-retained-iscsi-rehearsal.md). Earlier measurements above remain historical.
