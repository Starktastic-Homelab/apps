# Proxmox CSI cutover: backup blocked, original source recovered

The production cutover stopped before worker replacement or CSI activation. A
Proxmox NFS client stall interrupted the independent backup. Jellyfin was recovered
on its unchanged original iSCSI volume through reviewed PR1300; `/health` returned
`Healthy`, the original server identity/version12.1.0 matched, and its deployment
had one ready replica. Playback and final cleanup are tracked in the operation
receipt. LDAP scheduling resumes only after that observed health recovery.

## Completed gates

- External recovery of the actual encrypted CSI configuration and native driver
  TLS passed before downtime (PR1294 and Ansible run37243642764).
- PR1295 held both claims, scaled Jellyfin to zero and suspended LDAP. Argo synced
  that hold at00:14:56Z. Both negative admission probes passed, active writers
  ended, and workers201/202 and TrueNAS had no remaining Jellyfin iSCSI sessions.
- The cold source snapshot is
  `apps/iscsi/jellyfin-config@pre-proxmox-csi-20261005`.
- The entire68719476736-byte NAS copy matched the source SHA256:
  `db36b7cd6ee72fb54e14e0e48b1f05b1ffb3d11133b4d71f0c02b75ef8446c2d`.
  Original ext4 UUID `d3cc0be9-ad2f-4c67-a6fc-abc6104b7712` was preserved.
  Both read-only filesystem checks passed; the copy unit finished successfully
  at00:23:24Z. The final CSI filename was never published.
- Disposable VM980 downloaded and tested the exact image without networking.
  It was stopped before restoration. No production data reached that guest.

## Blocking observation

At about00:27Z, the verified-SSH gzip backup stopped after approximately8.4GB of
compressed output. Proxmox kernel `6.17.13-13-pve` showed the reader waiting in
`folio_wait_bit_common`, an RPC worker blocked in
`__lock_sock -> tcp_sock_set_cork -> xs_tcp_send_request`, and a subsequent GETATTR
probe waiting in `rpc_wait_bit_killable`. `pvestatd` also waited on the mount.
These are observed stacks, not a confirmed diagnosis of a particular kernel bug.

TrueNAS reported healthy pools, available memory and idle NFS threads. A new TCP
connection to2049 succeeded, but existing NFS reads did not recover. Proxmox had
only one NFS mount, `/mnt/pve/k3s-block`, and no VM/container configuration referenced
that storage. The owned backup reader and interruptible probes were stopped;
the incomplete owner-only workstation backup is preserved and is **not** a usable
verified backup. A kernel-blocked `ss` probe remained after a kill request.

A proposed exact-connection reset did not execute: its precondition rejected the
operation when the captured server-side connection disappeared. No broad socket
reset, NAS service restart, forced/lazy unmount, host reboot or kernel change ran.

## Recovery and retained boundary

PR1300 restored only the original iSCSI writer. Before release, checks reconfirmed
the source GUID/UUID, original worker VM and Node generation, retained authorization,
mutual PV/PVC binding, no other writers and absence of final target publication.
The new block claim remains denied. All original identity/fencing controls remain.
Argo synced recovery at00:43:42Z; health and one ready replica were subsequently
verified. No data was copied back from the target.

PRs1296–1299, Ansible285 and Terraform230 remain unmerged. The original ZVOL and
cold snapshot, verified unpublished NAS image, incomplete workstation transfer
and private operation evidence are preserved. The intended image path is still
absent. Resuming source writes makes the cold copy stale: a later attempt needs a
new cold snapshot/copy/backup rather than publishing this image.

The next decision concerns Proxmox host recovery and requalification under sustained
NFS reads. Host/kernel recovery is outside the approved worker-only replacement
scope. A host reboot would interrupt TrueNAS100, k3s200–202 and runner300; the
control plane would not remain online. Do not activate CSI or merge replacement
PRs merely because the original service has recovered.
