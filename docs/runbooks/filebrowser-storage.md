# Filebrowser private-state migration

Status: reviewed design, preparation only. Filebrowser currently uses the local
claim `operations/filebrowser-data-pvc`. The desired destination is the 4Gi
retained ext4 image `homelab//k3s-block/9999/vm-9999-filebrowser.raw`.

Read the [design](../superpowers/specs/2026-10-07-filebrowser-retained-csi-design.md)
and [implementation plan](../superpowers/plans/2026-10-07-filebrowser-retained-csi.md)
before authorizing an operation. This document does not certify a performed
backup, restore, cutover or rebuild. The two later PRs remain drafts until their
respective gates pass.

## Merge order

| Stage | Change | Gate |
|---|---|---|
| Protection | Existing local PVC gains Argo prune/delete protection; documentation and preflight receipt | Normal user merge; no outage or storage allocation |
| Maintenance | Filebrowser replicas0, old-source Pod admission guard, static 4Gi PV/PVC declarations | Separately approved Filebrowser window; fresh identities and verified backup/restore capability |
| Release | One replica on a CSI worker, new data claim and indefinite NoExecute tolerations | Accepted independent restore and target data/identity receipt; helper terminated and detached |

Do not merge release directly into main while skipping maintenance. Retain the
source protection and old-source guard after release. Neither draft PR is an
automation to copy files or allocate a Proxmox image.

## Source and destination preflight

Use VM300's existing maintenance installation and protected kubeconfig. Verify its
manifest hashes and VM identity first; never use the workstation as a deployment
or privileged-container host. Refresh all identities below at execution time:

- Source claim UID `2bbe10f6-bd7c-409e-96e5-428803b4a861`, PV
  `pvc-2bbe10f6-bd7c-409e-96e5-428803b4a861`, PV UID
  `e2e9c578-644b-4965-ab67-e5d05195c6a5`.
- Source directory on VM200:
  `/var/lib/rancher/k3s/storage/pvc-2bbe10f6-bd7c-409e-96e5-428803b4a861_operations_filebrowser-data-pvc`.
  Expected VM200 UUID `459b5ce3-d527-4edb-9617-206b50476a3f`.
- Target dataset `apps/k3s-block`, GUID `13918781591004512447`, export
  `/mnt/apps/k3s-block`, Proxmox storage `k3s-block`, reserved owner9999.
- Target filename `vm-9999-filebrowser.raw` must be absent before first allocation.
  Complete VM visibility must prove owner9999 is not an actual VM.
- Current source main database is Bolt/Storm; `cache/sql/index_all.db` is SQLite.
  Archive the complete data directory; do not run SQLite checks against the Bolt DB.
- OIDC Secret references, both browsing claims and their paths remain unchanged.

The October7 scan measured 239.54MiB. Capacity changes during operation require
rechecking the complete directory and dataset. A CSI quota or PVC request is not
proof of reserved free space. Budget full 4Gi growth, temporary staging/snapshots
and remaining Jellyfin growth; require at least 4Gi immediate headroom beyond the
new volume. Preserve the failed-transfer Jellyfin archive.

## Approved operation sequence

Before requesting execution approval, prepare a run-specific operation manifest
on VM300 with exact guest IDs/UUIDs, source identities, target identity, image size,
private backup paths, encrypted recipient, restore guest/resources, transfer and
restore commands, scratch path, cleanup list and rollback authority. Keep secret
values and database records out of Git and tool output. Any new credential transfer
requires explicit scope approval; no production CSI/admin token belongs in the
isolated application restore guest.

1. Inspect active transfers and every source consumer. Record private semantic
   baselines for user/share/access-rule counts and metadata, with sanitized counts
   in receipts. Confirm encrypted off-NAS backup and isolated restore capability.
2. After approval, merge maintenance and verify its desired/live replicas0 and
   source guard. Change the exact bound source PV reclaim policy to Retain under
   the approved mutation scope. Wait for Pod termination and clean source unmount;
   verify no writer remains. Do not replace VM200 during this operation.
3. Cold-archive the exact source directory with numeric ownership, permissions,
   ACLs, xattrs and all sidecars. Hash every file in a private manifest and hash the
   completed archive. Encrypt/transfer to a run-specific directory outside the NAS
   failure domain; verify full readback/hash. A live file copy is not a cold backup.
4. Independently restore that backup on a verified disposable guest. Check byte
   and metadata equality before startup, Bolt integrity and SQLite integrity on
   copies, and semantic counts. Run the pinned image loopback-only with production
   OIDC disabled and no production shares/network. Any local auth fixture changes
   only the disposable copy. Prove the app loaded existing state rather than
   initializing an empty database. Cleanup does not include the accepted backup.
5. Allocate the new 4G raw image using the qualified native Proxmox mechanism only
   after fresh identity/name/quota checks. Reject pre-existing names. Verify
   regular-file status, size and returned volume ID. Stock CSI may initialize this
   specifically approved blank image. A missing established image is an error.
6. Stage/restore through one approved CSI helper while Filebrowser is held. Verify
   all data/metadata against the accepted cold manifest before app startup; stop
   the helper, verify termination and clean unmount/detach, and record target
   image identity, filesystem UUID and size. No target is mounted concurrently by
   the lab guest. Reject incomplete copies, missing files or unknown writer state.
7. Accept the destination receipt before merging release. Verify one Ready writer
   on a worker using `operations/filebrowser-data-block`, correct handle, ext4 and
   a single attachment. Verify OIDC/admin mapping, existing users/shares/access
   rules and browse/read/download on both NAS sources. Write/rename/delete checks
   use only the run's separately approved scratch path.
8. Verify clean Pod recreation and movement between healthy workers. Do not force
   an unverified NotReady-node takeover. Preserve the old source and backup,
   remove only recorded lab-owned objects, and publish sanitized acceptance results.

Planning downtime is 30–60 minutes for Filebrowser alone; refine it from the
prepared/rehearsed operation. No production VM replacement or cluster rebuild is
included. Shared CSI integration already covers rebuild mechanics; this migration
must not claim its own unperformed production rebuild succeeded.

## Rollback and normal recovery

Before destination writes, verify all target helpers stopped and withdraw the
source guard only as part of a reviewed return to the original claim. Preserve the
new image for investigation. After destination writes, the source is stale:
rollback needs another stopped-writer backup and verified reverse copy/restore of
latest state. A simple Git revert must remain blocked from opening the old claim.

After cutover acceptance, use ordinary Packer/Terraform/Ansible PR flow. Git
reconstructs the static retained binding; verified Node retirement excludes old
writers, and control-plane replacement replaces the whole k3s cohort. No Velero
checkpoint or per-rebuild migration procedure is added.

Growth follows PVC-request, backend/filesystem verification, then PV-capacity
reconciliation. Existing NAS snapshots cover the new image after creation but are
not evidence of application-consistent off-NAS backups. Recurring backup policy
and archived-source retirement are later decisions. Keep the rare storage-fault
recovery procedure from the [CSI runbook](../../infrastructure/system/proxmox-csi/README.md).
