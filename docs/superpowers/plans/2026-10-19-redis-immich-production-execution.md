# Redis and Immich production execution proposal

Status: proposed; production execution is not authorized. This follows the approved
[design](../specs/2026-10-18-redis-immich-retained-csi-design.md) and preparation
[plan](2026-10-18-redis-immich-retained-csi.md). The checkpoint-only21-writer pause
and existing Dispatcharr DVR startup reset are already accepted decisions.

## Requested authority

After the inactive preparation PR passes exact-head checks, approve merging it,
then completing **Redis first, Immich PostgreSQL second**, including each scoped
activation PR's creation, exact-head validation, merge and held production sync.
Allow native ownership/Argo holds, the described outages, source ACL/AOF change,
immutable snapshots, private real-data/key transfers and disposable local restore
containers, exact target allocations and helper cleanup. Stop for an unresolved
change of direction, unknown writer/outcome, changed safety contract, unavailable
capacity, expired original window or missing access. This proposal does not grant
permission to bypass those gates, force detach, remove retained data, modify the
installed runner, add a VM or migrate another application.

## Impact and original windows

Redis downtime affects Immich-main, both Dispatcharr controllers and Paperless.
Filebrowser and the NFS provisioner are held only as source ancestors. Idle workers,
scheduled producers, global BullMQ flags and Celery active/reserved/scheduled jobs
are included. Shared PostgreSQL and Authentik are outside the operation.

Immich's database operation pauses21 writable-mount workloads at its checkpoint:
Immich-main, Filebrowser, Audiobookshelf, Bazarr, cross-seed, Jellyfin, Lidarr,
Lingarr, MeTube, Navidrome, both qbit-manage instances, both qBittorrent instances,
both Radarr instances, Shelfmark, both Sonarr instances, subgen and Unpackerr.
The NFS provisioner is an additional ancestor. Resume the19 unrelated media
workloads as soon as **both immutable database/photo snapshots are confirmed**;
they do not wait for full restore testing. Filebrowser and the provisioner resume
after the cold database archive and independent recovery; Immich remains down
through target acceptance. Mounts stay unchanged.

For each serial app, acquire a fresh owner with a **four-hour original limit**.
Prepare the reviewed activation diff and green exact-head CI before outage.
Before the first frontend hold, record the original outage clock. Require target
authority within **90minutes**, and complete the cutover within **three hours**
of that same outage start. Both monotonic and UTC clocks apply; no continuation,
RPC retry, helper or phase renews them. These are stop limits, not outage estimates.
Synthetic recovery times are listed in the preparation report; they are not a
measured production outage. A successful Redis release is required before fresh
Immich ownership.

## Media and capacity

| Target | New static retained image | Contract |
| --- | --- | --- |
| Redis | `k3s-block:9999/vm-9999-redis-data.raw` |2GiB ext4, cache none, RWOP, Retain |
| Immich PostgreSQL | `k3s-block:9999/vm-9999-immich-postgres.raw` |10GiB ext4, cache none, RWOP, Retain |

Do not create VM9999. Its stable external image ownership remains outside
Terraform. Use the unchanged upstream CSI driver and bidirectional static
prebinding; missing images cannot fall back to dynamic provisioning. The CSI
quota stays288GiB. Preserve the historical Jellyfin partial image.

The last read-only full-growth proof required207,074,251,264bytes against
216,523,108,352bytes dataset availability and273,150,525,440bytes physical free,
including both pending images,512MiB staging and8GiB spare. Refresh all images,
quota, pool health, NAS dataset GUID, PVE export/mount and space inside each actual
allocation action. Do not use this older observation as execution authority.

Retain source PVC/PV/data and all recovery snapshots. Redis snapshots are
`apps/pv@homelab-redis-retained-csi-20261018-{historical,live-aof,cold}`.
Immich's cold barrier is
`apps/pv@homelab-immich-retained-csi-20261018-cold` plus
`main/media@homelab-immich-retained-csi-20261018-cold`.
The media snapshot can retain unrelated changed blocks; no full46TB media copy
is planned. Never roll back the entire media dataset after other apps resume.

## Identity and recovery gates

Refresh source Pods/containers, workload/Application/PVC/PV UIDs, node and VM
UUID/boot generations, services, connected/configured consumers, local descriptors
and NAS clients before execution. Read-only preparation observed Redis8.10.2,
runID`2af2415c100f3cbb692e05ecd1d7ebabf557fea2`, about9.5MiB used memory and AOF off;
Immich uses PG17.6 with physical identifier`7614955115223928876`. Those observations
must be refreshed; an unrelated or newly initialized database is never adopted.

For Redis, keep the original process alive until full current-memory and live-AOF
independent recovery pass. Historical disk state cannot satisfy that gate. Enable
native ACL restrictions and AOF on that same source process; never undo AOF to
recover from a later failed phase. Require the full frozen target state before
any consumer starts. The accepted DVR exception covers only later evidenced stock
web startup behavior. Previously paused Immich queues require additional startup
qualification before outage; the current19 original flags are all unpaused.

For PG, export every database/role/schema/extension/sequence/record proof and
logical artifact while quiesced, then stop cleanly. Prove native writer retirement
on all three nodes and both immutable snapshot generations. Independently restore
the physical cluster and all logical data into a different disposable cluster.
Preserve UID/GID, modes, nanosecond timestamps, hardlinks, ACLs and xattrs; compare
before writing the retained marker. No foreign tables, external WAL or tablespaces
are included silently.

After population, verify target binding, raw inode/device/size, WWN, cache mode,
ext4 UUID and helper retirement, then record authority **before** any production
target writer request. Start only the database; perform full native comparison,
recreation, healthy-worker movement and normal-placement restoration. Release
consumers, verify recreated native queue definitions and original BullMQ flags,
restore frontends and reconcile complete current Git vectors with existing sync
options. Remove only owned holds under a six-minute continuous native watch,
including healthy AOF/ACL/exporter behavior. Check an existing original photo via
its API and checksum.

## Sensitive payloads and destinations

Infrastructure logins remain in their existing private files on this computer.
Use them in place for SSH to10.9.9.20 and10.9.9.10; do not copy them into VM300,
NAS, Kubernetes helpers or Docker fixtures. Use VM300's existing root-only native
runtime and kubeconfig in place, without installing or modifying that runtime.

Transfer the following application payloads only within the approved owner:

- Redis's full binary checkpoint/current-memory RDB, live/cold AOF archives, and
  Immich's complete cold database and logical exports. They can contain app data,
  job arguments, credentials/verifiers and roles. Stage source archives in the
  exact root-only operation spool under `/mnt/apps/pv/.homelab-<operation>/`, then
  stream through credential-free read-only helpers into VM300. No recovery key
  is put on NAS. Full original photos are not copied to those stages.
- Encrypt on VM300 with a fresh operation key. Retain ciphertext under
  `/var/lib/homelab-maintenance/operations/<operation>/recovery/` and
  `~/.local/share/homelab-recovery/<operation>/` on this computer. Retain the
  separate root-only VM300 key under that operation's `keys/`, and its private
  desktop copy under `~/.config/homelab-recovery-keys/<operation>/`, outside Git.
  Verify both ciphertext copies, separately decrypt the desktop copy and use the
  actual native engine to prove recovery before destructive boundaries.
- Read the existing Redis default password **verifier**, not its plaintext,
  privately to this computer. Generate one new maintenance password in the
  separate desktop key root. Seal with the repository's exact `scripts/seal.sh`
  and public certificate; only ciphertext enters Git. Create/verify the strict
  `redis-server-acl` SealedSecret/Secret on the cluster before outage. Existing
  default app passwords do not rotate. Retain only the separate maintenance
  password and recovery key after sealing cleanup. Private audit receipts can
  retain the verifier and metadata; they are not public artifacts.
- Keep the existing temporary Immich key at
  `~/Projects/homelab/immich.key` on this computer. Use only its existing
  asset.read/download access against`photos.benplus.app`; refuse redirects, stream
  the existing original into a checksum and save no photo. Revoke this temporary
  key after final acceptance; if its permissions cannot revoke it, request that
  final user action instead of broadening the key's permissions.

Desktop plaintext staging is only the ignored0700
`.superpowers/sdd/2026-10-18-redis-immich-retained-csi/production/<app>/private/`.
Remove exact owned plaintext, binary staging-log hardlinks and NAS spools after
acceptance; preserve private audit receipts, ciphertext and separate keys until
separately authorized retention cleanup. Nothing sensitive is committed to Git.

## Disposable resources and final definitions

Use this computer's existing Linux/x86_64 Docker runtime, about31GiB RAM. Restore
containers have exact operation labels, pinned engines, disconnected networking
or a narrowly owned internal fixture network and scoped data mounts. No production
application entrypoint or infrastructure credential is mounted. Each independent
restore uses one engine at a time and exact owned volumes; remove only those
labeled resources after its proof. VM300's850MiB RAM hosts transport/encryption,
not PG restore. Temporary cluster helpers are bounded; the Redis client is1GiB,
copy helper512MiB and read-only archive reader128MiB, with no API tokens.

Only the separately tested active diffs may change Redis values/manifests,
Immich values/manifests and the two static bindings under
`infrastructure/base-configs/templates/redis-immich-block-storage/`.
Redis requires exact replacement of its stopped StatefulSet when the immutable
claim template is removed; retain its old claim. Immich starts only the reviewed
PG Deployment imperatively while its main consumer remains paused. Then reconcile
those final definitions by full Argo sync. Do not change other app storage or
shared PostgreSQL/enrollment.

A failed or lost reply preserves the original native child, before-intent and
clocks. Inspect; never replay unknown/completed work or start a second owner. After
recorded target authority, CSI owns new writes: never reopen stale NFS data.
Use the [Redis](../../runbooks/redis-storage.md) and
[Immich](../../runbooks/immich-storage.md) runbooks for the recovery boundaries.
