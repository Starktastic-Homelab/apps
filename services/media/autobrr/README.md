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

The read-only startup init container checks the retained identity marker,
preserved session-secret presence, SQLite header and established application
schema. It does not create files, format a database or replace the stock
application's WAL recovery. Its immutable SQLite connection inspects only the
main-file schema; it is not a latest-data integrity or backup check. A missing
marker, config or established database blocks startup pending verified recovery.
Pod security overrides suppress a kubelet fsGroup rewrite, preserving numeric
ownership from the old directory; the application's existing root execution is
unchanged.

The old `media/autobrr` NFS claim is blocked by the permanent Pod admission hold.
The stopped-writer cutover protects that claim and PV against deletion, preserves
a cold backup outside the NAS, and checks restored bytes, metadata and SQLite
integrity before opening the CSI writer. Never return to the old SQLite copy
once the target has accepted writes without preserving the current state first.
Filebrowser's writable parent-directory access and the NFS provisioner must be
stopped during cold copy. Existing NFS workloads keep running while provisioning
waits. The preserved claim is excluded from Argo's extraneous-resource comparison.
The admission hold prevents Autobrr Pods from mounting the old claim; it does not
make that NAS directory immutable to Filebrowser or other authorized access.

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
