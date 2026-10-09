# Filebrowser retained CSI migration proposal

Date: 2026-10-07. Status: proposal for review; no live mutation or allocation.

## Goal and scope

Preserve Filebrowser's users, permissions, share metadata and private application
state through the ordinary Packer/Terraform/Ansible cluster replacement flow.
Reuse the unmodified Proxmox CSI platform already accepted for Jellyfin, with
static Git bindings to an image owned outside disposable VM lifecycle. No Velero
checkpoint or manual backup-verification gate is added to ordinary rebuilds.

Move only `/home/filebrowser/data`. Keep `/config` supplied by its existing
ConfigMap, the existing Secret reference, OIDC configuration, image digest,
ingress and both NAS browsing mounts. No PostgreSQL conversion, Filebrowser
upgrade, shared-storage default change, NAS quota increase or source deletion.

This proposal includes a future Filebrowser-only maintenance window and isolated
restore rehearsal. Preparing this document does not authorize those operations.

## Fresh evidence

Remote `origin/main` was fetched and remains
`a60246b24e42fa8c77c56194f3542f0d44c7a620`. Filebrowser's declarations in this
checkout match that revision; live Filebrowser, base-configs, Proxmox CSI and
Jellyfin report Healthy/Synced at that revision.

Reads at 2026-10-07 17:14–17:15 UTC established:

| Item | Observation |
|---|---|
| Filebrowser | `gtstef/filebrowser:1.5.6-stable@sha256:7c5d7ac8ffda31294d278063cf9d2e04303b39e6dce1f4c691342240ca7703b8` |
| Current pod | `filebrowser-555569b4c5-mxq2b`, UID `9e6adf7d-f653-4291-a5df-eb4722864bb0`, Ready on `kube-master-01` |
| Existing restarts | 14 at preflight; this is a baseline count, not a storage diagnosis |
| Deployment | One replica, Recreate, UID `340eabb7-6b48-4ec3-8b78-b8fd1f91b35a` |
| Source claim | `operations/filebrowser-data-pvc`, UID `2bbe10f6-bd7c-409e-96e5-428803b4a861`, Bound, local-path, nominal request 20Gi |
| Source PV | `pvc-2bbe10f6-bd7c-409e-96e5-428803b4a861`, UID `e2e9c578-644b-4965-ab67-e5d05195c6a5`, reclaim Delete, affinity to control plane |
| Source directory | `/var/lib/rancher/k3s/storage/pvc-2bbe10f6-bd7c-409e-96e5-428803b4a861_operations_filebrowser-data-pvc` on verified VM200 |
| Directory contents | 251,173,380 logical bytes (239.54MiB), 19 files, 31 directories, no symlinks; bounded metadata/header scan complete without errors |
| Main database | `database.db`, 131,072 bytes, not SQLite by header; pinned source opens its main store with Storm/Bolt |
| Search index | `cache/sql/index_all.db`, 250,900,480 bytes, SQLite |
| CSI dataset | `apps/k3s-block`, GUID `13918781591004512447`, quota 128GiB, used 54.10GiB, available 73.90GiB |
| Existing images | Active Jellyfin image and preserved hidden partial image only; proposed Filebrowser filename absent |

The source's local-path request is not a measured per-directory quota. It does
not demonstrate a need for a 20Gi block filesystem. Scan sizes may change with
application activity. Header reads did not open a database engine, checkpoint,
repair, assess integrity or export database contents. No Secret values were read.

Evidence is held locally under `/tmp/filebrowser-csi-proposal-20261007/`:
`live-read.json`, `source-scan.json`, `quota-read.json` and `evidence-sha256.json`.
The checked-in companion receipt contains only sanitized identities and totals.

The version-specific [Docker documentation](https://filebrowserquantum.com/en/docs/getting-started/docker-v1.5.x/)
identifies `/home/filebrowser/data` as the persistent data location. The
[pinned storage implementation](https://github.com/gtsteffaniak/filebrowser/blob/v1.5.6-stable/backend/database/storage/storage.go)
opens the main Bolt store and writes during initialization. Startup therefore
must occur only on a disposable restored copy during rehearsal, never on the
original source or an archived backup.

## Recommended destination

Use a new 4GiB ext4 raw image, retaining the full data directory including caches
and sidecars on the first migration. This provides roughly 17 times today's
logical footprint; do not add cache relocation or rebuild behavior to this
storage change. Actual usable ext4 capacity is lower than the image's nominal
size. Monitor filesystem use and grow through the existing request/verify/
reconcile procedure before it fills.

| Declaration | Proposed value |
|---|---|
| PV and PVC name | `filebrowser-data-block` |
| PVC namespace | `operations` |
| Storage class | `proxmox-retained` |
| Image owner | Reserved external owner 9999; it must remain unused as a VM |
| Image | `k3s-block:9999/vm-9999-filebrowser.raw` |
| CSI handle | `homelab//k3s-block/9999/vm-9999-filebrowser.raw` |
| Driver | `csi.proxmox.sinextra.dev` |
| Capacity | 4Gi |
| Filesystem/cache | ext4 / none |
| Access/reclaim | ReadWriteOncePod / Retain |
| Prebinding | PV claimRef name/namespace without UID; PVC volumeName equals PV name |
| Argo protection | Prune=false, Delete=false on both PV and PVC |
| Topology | Region homelab, zone pve |
| Placement | Linux worker with CSI node plugin; preserve one replica and Recreate |
| Eviction behavior | Indefinite not-ready/unreachable NoExecute tolerations, as used by Jellyfin |

Allocate only after refreshed identity, ownership, complete VM visibility,
filename absence and capacity checks. Reuse the qualified native `pvesm alloc`
mechanism with owner9999 and 4G raw size. Reject an existing name; never overwrite
or replace a disk based on its filename alone. Verify returned volume ID,
regular-file status, byte size and storage identity. Stock CSI may format this
explicitly approved new blank image on first staging, under the filesystem
handling policy already accepted by the user. A missing or wrong existing image
is an error, not permission to recreate application state.

The 4Gi capacity is a maximum size for this volume, not a dataset reservation.
Budget conservatively for its full growth and temporary staging/snapshots. At
allocation, require enough available space for the full new volume plus at least
4Gi of immediate headroom, and review remaining Jellyfin growth against the
aggregate quota. Leave the hidden partial Jellyfin image untouched. This migration
must not silently use quota intended for later applications or raise quota.

Changing placement from the control plane to a worker is intentional: the CSI
node plugin currently runs on workers. Both broad NAS browsing mounts retain
their existing claim names and paths. No shared library or app-share files are
copied as part of this migration.

## Preparation and delivery sequence

Prepare small reviewed changes using current main, preserving unrelated work:

1. **Source protection and writer hold.** Protect the existing local PVC against
   Argo prune/delete. In the approved operation, change its exact bound PV reclaim
   policy to Retain and verify the readback. Retain cannot preserve a control-plane
   root disk through VM destruction, so a verified independent backup remains
   essential. Prepare a Git-visible zero-replica maintenance hold and native
   admission guard denying Pod use of the old claim. Keep it inactive until the
   approved window. The cold source reader uses verified VM200 filesystem access;
   no source-mounted application or helper Pod is exempted from the guard.
2. **Destination declarations.** Put PV/PVC templates in
   `infrastructure/base-configs/templates/filebrowser-block-storage/`, using the
   existing Jellyfin binding pattern. Add protections, static prebinding and
   attributes explicitly; do not rely on StorageClass parameters to populate a
   static PV. Keep Filebrowser held until the populated image is accepted.
3. **Writer release.** Update only Filebrowser's data existingClaim, worker
   placement and eviction tolerations, then remove its zero-replica hold after
   restore/copy acceptance. Preserve the source PVC and source admission guard.
   The original data-PVC template stays protected; no immutable claim fields are
   patched to disguise it as a CSI claim.

A PR must show the actual rendered value cascade and affected objects. A
preparation merge must not silently begin maintenance. A writer-release PR must
remain draft or otherwise unmerged until its data gates pass. User merge
approval remains required; earlier Jellyfin-only autonomous merge authority
has ended. Publication of this proposal is not a request to merge live manifests.

## Cold backup, isolated restore and cutover

Use one Filebrowser maintenance window after offline preparation. An initial
planning budget is 30–60 minutes, primarily for independently verified restore
and application acceptance, not for copying 240MiB. This is an estimate, not a
measured duration or a hard upper bound. Rehearsal may refine the estimate before
approval. No production VM replacement, whole-cluster outage or interruption of
Jellyfin/qBittorrent is included.

1. Refresh all identities and capacity. Inspect current effective configuration,
   outstanding uploads/downloads and all consumers of the exact source claim.
   Record sanitized user/share/access-rule counts without exporting credentials
   or password hashes. Establish whether any external Filebrowser backup exists.
   Stop if a consumer, identity or required backup capability is unknown.
2. Activate the reviewed hold and source admission guard. Wait for the sole
   Filebrowser Pod to terminate and its source volume to unmount. Verify the old
   Pod UID is absent and no remaining process has the directory open for writing.
   A zero replica count alone is insufficient. Do not replace VM200 before the
   independent backup and migration are accepted.
3. Cold-archive the entire exact data directory, preserving numeric ownership,
   permissions, symlinks, ACLs and extended attributes. Include SQLite WAL/SHM
   sidecars if present. Exclude neither the main database nor the search index.
   Record a private file/content manifest, archive hash and cold source identities.
   Encrypt the backup using an established recoverable recipient and transfer it
   outside the NAS failure domain. Verify a full readback/hash after transfer.
   The proposed private destination is a run-specific directory under
   `/home/benf/Backups/homelab/filebrowser/`; writing there needs the later operation
   authorization. Keep secrets and database contents out of Git/tool output.
4. Restore the off-NAS backup independently on an identified disposable guest,
   never on the workstation as a deployment target. Verify hashes and metadata
   before startup. Check the main store with a compatible upstream Bolt integrity
   tool; check every SQLite database with SQLite integrity checks on the isolated
   copy. Inspect sanitized semantic counts against the cold source baseline.
   Run the exact pinned Filebrowser image with restored state, loopback-only
   access, disabled production OIDC and no production browsing-share mounts or
   production network access. Lab-only settings and any fixture accounts affect
   this disposable copy only. Confirm no fresh empty database was initialized.
   Final OIDC and real share-access acceptance happen in production, not in this
   disconnected lab. Disposable VM selection/resources require a fresh unused-ID
   preflight and approval within the operation plan; no old lab identity is reused
   by assumption. Failure leaves the source held until controlled recovery.
5. Create and initialize the new image only within the approved allocation scope.
   Stage it through stock CSI for a single approved restore helper while the
   application remains held. Restore the accepted cold archive, preserve metadata,
   compare the file manifest before application startup, and close/unmount the
   helper cleanly. Prove helper termination, no active writer, correct image,
   filesystem UUID and attachment state before release. No concurrent mounts of
   a production target on a disposable lab VM are allowed.
6. Record a completed-data receipt containing source archive hash, target image
   ID, filesystem UUID, size, restore checks and helper termination. Merge/reconcile
   the release only with this receipt accepted. Start one Filebrowser on a worker.
   Verify Ready, correct PVC/PV/handle and attachment, existing user/share counts,
   OIDC login/admin mapping, browse/read/download on both existing NAS sources,
   and permissions. Check a write/rename/delete round trip only in a separately
   approved uniquely named scratch directory, never by altering an existing file.
   If human OIDC interaction is required, request it at that acceptance step.
7. Verify a clean Pod recreation and a controlled move between healthy workers,
   one at a time, preserving accounts and state. Do not force an unverified
   unreachable-node takeover. Retain source, off-NAS backup and receipts until a
   later explicit retirement decision. Remove only documented lab-owned resources
   after verified cleanup.

An isolated rehearsal or backup has not yet been executed. Its disposable guest,
resource budget, transport helpers and complete operation commands must be
prepared and reviewed before requesting execution approval. Do not transfer any
production credentials into a lab merely because this proposal describes it.

## Acceptance, rollback and routine recovery

Accept the migration only when byte/metadata verification, independent backup
restore, database integrity, semantic state, OIDC, source access and clean worker
movement have all passed. A healthy HTTP endpoint alone is insufficient. Do not
assert that the 14 historical restarts are fixed by changing storage.

Before the production target starts writing, a failed migration can return to the
held original source: terminate/verify target helpers, retain the new image,
explicitly withdraw the source guard and restore the reviewed source binding and
replica count. Do this as a coordinated action; an ordinary Git revert must not
bypass the guard.

After the target starts writing, the original source is stale. Rollback requires
another stop, cold backup of the latest target and verified reverse copy/restore,
with explicit approval. Never start both instances or restart the stale original
as an easy rollback. Any uncertainty leaves writers held; record it rather than
clearing protection to obtain a green deployment.

After acceptance, ordinary rebuilds reconstruct the static PV/PVC from Git and
reuse the surviving image. The existing verified Node-retirement and control-plane
whole-cohort replacement policy provide the fencing boundary. No new permanent
controller, per-rebuild migration script or backup-check step is introduced.
Shared platform rebuild qualification is existing evidence; this proposal does
not claim a Filebrowser-specific production rebuild has been performed.

Filesystem growth uses the existing CSI PVC-request, backend/filesystem-verify,
then declarative-PV-capacity sequence. NAS loss and storage-fault recovery still
require the accepted backup/manual recovery procedures. Existing dataset snapshots
include the new image after creation, but are not proof of application-consistent
backup. A recurring off-NAS Filebrowser backup policy remains a separate follow-up;
the accepted cold migration backup must not be described as a continuous backup.

## Verification before PR delivery

Validate the affected rendered Filebrowser and base-configs manifests with the
actual globals/common/service/manifest layers, including namespace/topology,
worker selector, RWOP prebinding, protection and writer hold. Run relevant YAML,
format/schema and compatibility checks from the repository instructions. Check
that the retained-source guard blocks old-claim consumers and allows unrelated
apps and the new approved target helper. Check that the final release still uses
the pinned image, existing OIDC/config/Secret references and existing NFS claims.

For this proposal, verification consists of current-main comparison, fresh
read-only identities/capacity/source metadata, sanitized receipt consistency,
source citations and document review. No application code, live manifests or
runtime settings were changed. Runtime backup, restore, attachment, login and
movement acceptance remain unperformed.
