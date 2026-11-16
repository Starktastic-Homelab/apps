# Jellyfin retained block storage

Jellyfin consumes `media/jellyfin-config-block`, statically prebound to the same
named PV in shared infrastructure. Stock Proxmox CSI attaches the ext4 raw image
`homelab//k3s-block/9999/vm-9999-jellyfin.raw`. Owner9999 is reserved outside VM
lifecycle; deleting/replacing a worker must not delete that image.

## Normal operation and rebuilds

Use the normal Packer, Terraform and Ansible PR flow. Git reconstructs the binding;
verified Node retirement and CSI topology handle fresh VM generations. Replacing
the control plane replaces all workers as the accepted fencing boundary. No
Velero checkpoint or manual backup verification gates routine rebuilds.

The PV/PVC are Retain, RWOP and protected from Argo prune/delete. Do not remove
those protections to resolve an attachment problem. The accepted rare storage-fault
recovery procedure is in the [CSI runbook](../../infrastructure/system/proxmox-csi/README.md).

For growth, increase the PVC request through Git, verify backend/filesystem
expansion, then reconcile the declarative PV capacity. Account for the NAS dataset's
aggregate quota (current value in the [CSI README](../../infrastructure/system/proxmox-csi/README.md)) before expansion; raising quota
is a separate reviewed change. Remeasure available space before growth.

## Backup and recovery

The dataset has six-hour snapshots with one-week retention. These are storage
snapshots, not proof of application-consistent backups. A cold backup requires a
Git writer hold, stopped Jellyfin, suspended/completed LDAP jobs, clean unmount
and absence of writers before snapshot/copy. Protect private API/LDAP credentials;
preserve the entire filesystem including plugin state and SQLite WAL files.

A backup is accepted only after completed off-NAS transfer, full hashing,
independent restore and application acceptance on a disposable isolated guest.
The workstation stores/transports bytes only. Never restore stale source data
as an ordinary rollback after target writes.

The [October6 cutover report](../superpowers/reports/2026-10-06-proxmox-csi-jellyfin-cutover.md)
records the verified encrypted off-NAS backup and original ext4 UUID taken at cutover.
The [iSCSI cleanup plan](../superpowers/plans/2026-10-06-retire-jellyfin-iscsi.md)
removed unused export metadata, driver, old bindings and guards. The ZVOL
`apps/iscsi` and TrueNAS snapshot task 2 were deleted on 2026-11-15. The October
backup of the pre-cutover iSCSI source was most likely among the
[recovery copies deleted on 2026-11-16](../../infrastructure/system/proxmox-csi/README.md#retired-migration-sources-2026-11-16); treat it as gone.

## Historical tools

The old service-specific iSCSI/NFS migration and status/preflight scripts are
retired, along with their manual workflows and Ansible enrollment/fencing roles.
Use Git history and dated operational receipts for incident analysis; do not
reapply historical manifests or use old release records to authorize writers.

The original NFS claim `jellyfin-config`, its PV and the `jellyfin-storage-hold`
admission policy were retired on 2026-11-16. The archive under
`/mnt/apps/pv/media/jellyfin-config` (unchanged since June 2026) is deleted on
TrueNAS after the retirement. Until they age out, copies remain in the `apps/pv`
snapshots, the `usbbk` replica and the off-site restic `daily` snapshots under
`/srv/backup-src/pv/media/jellyfin-config`; the longest-lived is the 2026-11-15 weekly.
The [CSI README](../../infrastructure/system/proxmox-csi/README.md#retired-migration-sources-2026-11-16)
states when the restic copies age out (about 2027-01-10, not pinned).

Cleanup merges Ansible first. Keep the Apps cleanup PR draft until owned NAS
export retirement is verified, then merge Apps: its automatic pruning removes
the old alias/PV/IQN guards. Do not merge both cleanup PRs together.
