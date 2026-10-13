# Prowlarr production data cutover

Prowlarr 2.6.5.5623-ls161 now uses the existing PostgreSQL 18.6 service for both
native databases and retained 4GiB ext4 CSI for `/config`. The stock image and
upstream Proxmox CSI driver are unchanged. Activation PR
[#1351](https://github.com/Starktastic-Homelab/apps/pull/1351) merged, native
current-main desired/live equality passed, and the owned hold was released.
Reconciliation, the six-minute watch and disposable-resource cleanup completed
at 14:45 Israel time on October13, within the original 16:00 deadline.

## Accepted live and recovery evidence

- Enrollment PR [#1350](https://github.com/Starktastic-Homelab/apps/pull/1350)
  activated `prowlarr-main`/`prowlarr-log`. Both restricted database owners passed
  initial full-hook acceptance and one deliberate idempotent full-sync retry.
  The existing PostgreSQL Pod and physical database identity stayed unchanged.
- All three source/ancestor writers were stopped under the scoped hold. API,
  every node's running containers and NFS mounts, and NAS handles were checked
  before capture. Filebrowser and the NFS provisioner were restored after the
  cold recovery proof; Prowlarr stayed fenced through conversion.
- The complete 319,436,800-byte cold archive matched the native stopped-source
  fingerprint, file bytes, ownership, permissions, timestamps and hardlinks.
  SQLite integrity passed on a private full copy. Encrypted copies on VM300 and
  the operator computer passed full readback, with separate private keys outside
  Git. Original NFS data, old logs and backups remain retained.
- A new no-NIC VM980 independently restored the latest cold archive and ran the
  pinned stock SQLite app. Settings and entity counts matched. Fresh physical
  PostgreSQL recovery then verified both dumps, every table and sequence before
  stock app startup, a new write's allocator, Housekeeping and clean restart.
  Only fixture SQL credentials entered this isolated lab.
- Conversion preserved all 20 main tables, including 266,398 history rows, and
  all 19 historical sequence floors. Every typed field matched at PostgreSQL
  precision; the materialized SQLite source stayed unchanged. Old diagnostic
  database/filesystem logs remain in recovery and NFS; active logs start fresh.
- Production passed all five startup guards, exact original non-PostgreSQL XML
  values/order, canonical credential-bound PostgreSQL fields and API-key login.
  Counts matched: 20 indexers, five applications, one download client, one proxy,
  one notification, three tags, one app profile and one custom filter. Every
  protected configuration field matched after startup and Housekeeping.
- All five existing application tests and the download-client test succeeded.
  An ordinary Ubuntu search succeeded without a grab; a new Housekeeping command
  completed. Clean recreation and healthy-worker movement passed with the same
  filesystem/PV/PVC, retired old runtime and old-worker device, and restored
  original scheduling. There was no SQLite fallback.
- A uniquely owned post-acceptance Job from the unchanged `pg-backup` CronJob
  passed native gzip/completion-marker and both-database/role coverage checks.
  The existing schedule stayed enabled; PostgreSQL was not restarted.
- Prowlarr, Filebrowser, base-configs and nfs-provisioner reached Healthy/Synced
  with fresh successful operations at merged commit
  `8714255d78e61a118685d1958eff819fd3955a52`. A native Deployment watch started
  before hold release and ran for six minutes without an old-claim, zero-replica
  or image regression. Prowlarr retained the same Ready Pod through release.
- Exact owned helpers, policy, completed manual backup Job, VM980, temporary
  media and plaintext copies were removed. The maintenance owner and inactive
  nonce copy were released. Final read-only checks verified the unchanged Ready
  PostgreSQL Pod, retained CSI binding, protected original NFS claim, both
  encrypted recovery copies and separate keys. Unrelated deployments were
  unchanged.

## Durable recovery contract

Git declares `media/prowlarr-config-block`, RWOP/Retain, one replica/Recreate,
worker placement, retained configuration checks, both enrollment completion
checks and SQL startup checks. The image handle is
`homelab//k3s-block/9999/vm-9999-prowlarr.raw`. The old `media/prowlarr` NFS claim
and bound PV are retained and new Pods are denied from mounting that old claim.
Existing verified VM-retirement fencing remains required on rebuilds.

The first production target-write intent was recorded before startup. Original
SQLite is now a historical recovery source: a Git revert does not reverse the
conversion or preserve newer PostgreSQL writes. Preserve current PostgreSQL/CSI
state before choosing any reverse conversion or data-loss boundary.

## Native implementation corrections

Execution exposed environment details beyond fixture qualification: empty
successful guest-agent ping output, the cloud-init CD preceding the public ISO,
a GPG socket-path/daemon-output issue, API omission of empty ingress arrays,
stock XML reserialization and integer-valued Proxmox terminal flags. Each was
reconciled against native evidence before resuming only untouched steps. Frozen
before/after hashes and root-private receipts retain the corrections; no failed
clone/start/data-conversion mutation was replayed, no network policy was widened,
and the original recovery/absolute-time gates stayed in force. A transient NAS
read refusal was reconciled with a fresh held-source fingerprint before capture.

Two revisionless RollingSync operations had been queued while the hold was
active. Their captured UID, original operation/controller/start time and source
snapshots matched; neither had a resolved revision or resource result. An
explicitly approved bounded amendment terminated each once and atomically
replaced only that captured generation with the complete current source set,
resolved merged-main revisions and prune disabled. Desired/live equality was
rechecked before and after replacement. This is not permission to discard an
arbitrary unknown operation.

Cleanup's ownership check initially included descendants of the extracted
archive's source-check directory but omitted that directory itself. Its exact
UID1000 directory metadata matched the retained archive manifest; the corrected
boundary included only that verified root. The 1,028-entry inventory then exceeded
Linux's per-argument size limit before deletion started. All entries still matched
their hashes; sending the same inventory through stdin completed the unchanged
deletion checks. Already completed cleanup steps were not replayed.

The private packet and recovery credentials are excluded from Git. Cleanup is
limited to exact owned temporary helpers, policy, completed manual backup Job,
lab VM/media and plaintext working files; retained NFS/CSI/SQL state, encrypted
archives and separate keys are preserved.

## Activation validation

All 21 focused guard/composition/native PostgreSQL fixture tests passed with the
actual final layered Helm render. Formatting preserved every rendered object and
all eight activation source objects. Raw and rendered schemas, scoped pre-commit,
tracked-source YAML lint, Homepage coverage, Jellyfin compatibility and README
image checks passed. PostgreSQL enrollment's 25 tests and its retained-state
canary also passed. All five required hosted checks passed at the exact activation
head, and the Argo diff changed only the expected Prowlarr/base-configs resources.
Whole-directory lint additionally found generated private
rehearsal renders under ignored `.superpowers`; those are excluded from Git and
from the checkout used by hosted CI.
