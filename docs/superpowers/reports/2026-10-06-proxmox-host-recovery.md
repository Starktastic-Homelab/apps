# Proxmox host recovery before the Jellyfin cutover retry

The approved normal host reboot completed without a manual reset. All five
original VMs returned with unchanged identities. The three Kubernetes nodes are
Ready, application workloads recovered, and Jellyfin remains on its original
iSCSI volume. Its original server identity/version, an8MiB HTTP206 video sample
and five decoded frames passed recovery checks. This is not a new GPU encoding
qualification.

The old blocked socket tasks are absent and Proxmox's status service is active.
A read-only full64GiB read and gzip compression run over NFS passed in611.7seconds,
matching raw SHA256`db36b7cd6ee72fb54e14e0e48b1f05b1ffb3d11133b4d71f0c02b75ef8446c2d`.
The kernel remains6.17.13-13-pve. The test proves this completed read; the stall's
root cause and permanent resolution are not established.

The owned maintenance lock and temporary runtime override were released/removed.
Receipts remain under `/var/lib/homelab-maintenance/operations/proxmox-host-recovery-20261006`
onVM300 and `/root/proxmox-host-recovery-20261006` onProxmox.

The first attempt's unpublished image, source snapshot and incomplete workstation
backup remain preserved incident evidence. Resumed source writes make that image
stale. A separately approved fresh attempt must create a new cold snapshot/copy,
complete its independent backup and isolated restore, and pass the existing
activation gates before replacing workers or releasing a CSI writer. Temporary
migration-only PR merge authority was renewed for that attempt.
