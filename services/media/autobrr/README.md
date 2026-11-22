# Autobrr retained configuration

Autobrr keeps SQLite and its private `config.toml` together on retained Proxmox CSI.
The image, Authentik/OIDC settings and session secret remain unchanged. Shared
media and downloads remain on NFS.

| Resource | Binding |
| --- | --- |
| Claim | `media/autobrr-config-block`, 1Gi, ReadWriteOncePod |
| Volume | `autobrr-config-block`, ext4, Retain |
| Image | `k3s-block:9999/vm-9999-autobrr.raw` |
| CSI handle | `homelab//k3s-block/9999/vm-9999-autobrr.raw` |
| Placement | One replica, Recreate, healthy k3s worker |

Owner9999 is reserved outside the VM lifecycle and must remain unused as a VM.
The static PV/PVC survive fresh Kubernetes metadata through Git; the image stays
on the NAS during VM replacement. The established Ansible VM-retirement fencing
and coupled worker replacement when the control plane is replaced remain required.

The read-only startup init container runs the generic marker guard (`infrastructure/base-configs/files/retained-startup/guard.py`, ConfigMap `retained-startup-guard`) as
`autobrr /config config`: `/config/.homelab-autobrr-config` must be a regular file
holding exactly `homelab/autobrr/config/v1` and a newline. It checks no config,
SQLite header or schema, and it does not create files or replace the stock
application's WAL recovery. A missing or wrong marker blocks startup pending
verified recovery.
Pod security overrides suppress a kubelet fsGroup rewrite, preserving numeric
ownership from the old directory; the application's existing root execution is
unchanged.

The stopped-writer cutover kept a cold backup outside the NAS and checked
restored bytes, metadata and SQLite integrity before opening the CSI writer.
Filebrowser's writable parent-directory access and the NFS provisioner were
stopped during the cold copy. The old `media/autobrr` NFS source, its Pod
admission hold and the cold backup were
[retired on 2026-11-16](../../../infrastructure/system/proxmox-csi/README.md#retired-migration-sources-2026-11-16);
recover from the CSI image and its backups, never from an old SQLite copy.

PostgreSQL enrollment remains available but unused by Autobrr. The pinned stock
release path saves each matching release before running actions; a database
write failure aborts that path. The February source history contains eight rows
with invalid UTF-8 that PostgreSQL rejects. Keeping SQLite avoids introducing
that backend-specific announcement failure while eliminating SQLite over NFS.
See the pinned [release processing](https://github.com/autobrr/autobrr/blob/v1.86.0/internal/release/service.go#L523)
and [release insert](https://github.com/autobrr/autobrr/blob/v1.86.0/internal/database/release.go#L49).

Qualification and live acceptance are separate: local guard tests and an isolated
stock application restore do not prove that production has moved. The cutover
receipt must identify the live target before final reconciliation and hold release.
