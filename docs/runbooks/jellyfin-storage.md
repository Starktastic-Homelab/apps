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
128GiB aggregate quota before expansion; raising quota is a separate reviewed change.

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
records the verified encrypted off-NAS backup and retained original ext4 UUID.
The [iSCSI cleanup plan](../superpowers/plans/2026-10-06-retire-jellyfin-iscsi.md)
removes unused export metadata, driver, old bindings and guards while preserving
the original ZVOL, snapshots and backup. Source-data deletion is not included.

## Historical tools

The old service-specific iSCSI/NFS migration and status/preflight scripts are
retired, along with their manual workflows and Ansible enrollment/fencing roles.
Use Git history and dated operational receipts for incident analysis; do not
reapply historical manifests or use old release records to authorize writers.

The original NFS claim `jellyfin-config` remains prune/delete-protected. The short
`jellyfin-storage-hold` admission policy denies mounting either archived claim
(`jellyfin-config`, `jellyfin-config-iscsi`) throughout retirement. It does not
match the active `jellyfin-config-block` claim. Removing archived data or this
protection requires a separate recovery/retirement decision.

Cleanup merges Ansible first. Keep the Apps cleanup PR draft until owned NAS
export retirement is verified, then merge Apps: its automatic pruning removes
the old alias/PV/IQN guards. Do not merge both cleanup PRs together.
