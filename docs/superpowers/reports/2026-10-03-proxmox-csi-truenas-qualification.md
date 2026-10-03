# Proxmox CSI on TrueNAS 25: bounded qualification scope

Date: 2026-10-03. Status: approved scope executed; bounded tests and live-resource cleanup complete.
Companion: [completed Debian NFS lab](2026-10-03-proxmox-csi-lab-results.md).

## Fresh preflight

The existing credential reference on identity-verified VM300 worked with its existing hash-verified Python and websocket
wheel. Credentials stayed on VM300; the client validated the configured CA and independently recorded leaf pin before
authentication. No package installation, NAS configuration write, workload deployment or service restart occurred.
The system interpreter initially lacked websocket; the existing manifest-pinned wheel resolved that import.

[Sanitized observations](evidence/2026-10-03-proxmox-csi-truenas-preflight.json) confirm:

- TrueNAS `25.10.7`, pool `apps` GUID `9917900421692286909`, ONLINE and healthy.
- Pool free space about 338GiB; dataset-reported available space about 259GiB. These are observations, not reservations.
- `apps` is encrypted and unlocked, sync STANDARD, LZ4 and POSIX ACLs. `apps/pv` has local sync STANDARD.
- Proposed dataset `apps/csi-qualification-20261003` does not exist. No existing NFS share uses that path.
- NFS is running with NFSv4 enabled and binds to `10.9.8.30` / `10.9.9.30`; the lab will use `10.9.9.30`. It serves production exports and must not be restarted or stopped for this lab.
- No snapshot or replication task recursively targets the parent `apps` dataset. Recheck immediately before allocation.

## Exact proposed changes

Create one dedicated sibling of `apps/pv`: **`apps/csi-qualification-20261003`**, mounted at
`/mnt/apps/csi-qualification-20261003`, with **8GiB quota**, no reservation, explicit sync STANDARD, inherited encryption
and existing parent compression/recordsize defaults. Do not alter parent properties or application datasets. Recheck pool
GUID, available space, unlocked state, dataset/path absence and share collisions immediately before creation. A collision
aborts; never adopt an existing object.

Create one NFS share for that path, writable only by Proxmox **10.9.9.20/32**, with root mapping appropriate for Proxmox
image allocation. Preserve every existing export and global NFS setting. Use the supported share configuration operation;
if it requires a disruptive global NFS restart rather than a safe export reload, stop before that action.
Record the new dataset GUID and share ID before proceeding. Keep the new dataset outside existing application snapshot
or replication policies; inspect recursive ancestor policies first and stop if the lab would unexpectedly be included.

On Proxmox, reuse the now-free disposable identities **980–983** and image-owner namespace **9980** only after fresh
collision/identity checks. Create four VMs at 2GiB RAM / 2 vCPU / 8GiB root each: a tooling runner and a separate three-node
k3s cluster. Total: **8GiB RAM, 8 vCPU, 32GiB permanent VM disks**, plus cloud-init disks. Permit one temporary 4GiB clone
on local-zfs at a time before movement to vm-pool, as qualified in the first lab. Require at least 2GiB host MemAvailable
after each start; do not change production VM memory or ARC settings. Template900 remains unchanged.

Create a temporary Proxmox NFS registration **`csi-truenas-assessment`**, node-limited to `pve`, pointing to `10.9.9.30:/mnt/apps/csi-qualification-20261003`.
Create separate temporary CSI/Terraform identities and a persistent lab pool with the already qualified resource-scoped
permissions. Keep owner9980, NAS allocation and this NFS registration outside the cluster-only Terraform state.
Use DHCP and verified guest-agent identities, generated lab SSH keys and secrets. No production Terraform backend,
Kubernetes credentials, Apps discovery or service volume is used.

## Tests

Use the same stock CSI v0.20.0/chart0.5.10, Telmate3.0.2-rc10, k3s v1.37.0+k3s1 and cache-none ext4 setup as the successful
Debian lab. Verify release artifacts/digests before execution. Run Terraform, Helm, kubectl and workloads only on the new
disposable guests. VM300 is only the existing trusted route for NAS management, using the shared maintenance lock and
operation identity for mutations; it is not a lab worker or package-install target. Workstation use is limited to editing
and transport.

1. Allocate one 2GiB synthetic raw image under owner9980; commit non-secret static retained PV/PVC bindings in lab Git.
   Populate deterministic SQLite data using WAL and synchronous FULL. Record image identity, UUID and committed sequence.
2. Verify Terraform no-op/unrelated update and healthy worker movement preserve attachment/data identity.
3. Expand the attached PVC from 2GiB to 4GiB, interrupt/retry node expansion, then reconcile successful capacity in Git.
4. Destroy and recreate all three cluster VMs and their datastore, recovering only from static declarations and external
   credentials. Repeat with an active writer and confirmed abrupt old-VM power-off, including a deliberately interrupted
   destroy. Preserve every observed committed record and the same filesystem UUID.
5. Repeat missing/blank/wrong-filesystem tests using separately recorded disposable images within the 8GiB quota.
   Retain native failed-node pod holds and confirmed-off takeover. Do not force concurrent writable mounts.
6. Observe actual mount options, attachment state and available locking evidence. Exercise a bounded interruption by
   disabling/re-enabling **only the disposable export**, if supported without a disruptive service restart. Prepare an
   independent bounded restoration mechanism before interruption. Record client I/O and subsequent SQLite integrity.
   If safe per-export interruption is unsupported, leave this case explicitly untested rather than stop global NFS.

No NAS reboot, global NFS service stop, pool export, production network fault, full-pool test or power-loss test is included.
Results qualify the actual export configuration and tested failure cases, not arbitrary hardware failure or large-volume
performance. The user's ordinary Packer PR -> Terraform PR merge procedure remains the intended production interface;
shared pipeline integration and Jellyfin migration remain later work.

## Cleanup and approval boundary

Export sanitized results before removing guests. Stop lab writers and verify old VM shutdown, destroy only the current
lab VMs/disks, free exact recorded synthetic images, unmount/remove the temporary Proxmox storage registration, revoke
lab tokens/users/roles and remove the empty lab pool. Remove only the recorded new NFS share and dataset after checking
their native IDs/GUIDs and absence of unexpected children/snapshots. Preserve all pre-existing storage, exports, secrets,
maintenance history and production workloads. Remove generated lab credential material after evidence is saved.

The previous approval covered a synthetic Debian NFS server and its cleanup. This proposal adds allocation and export
changes on the production TrueNAS appliance and a new disposable VM run, and the user approved this concrete scope by instructing continuation after the approval request.
The existing credential reference removes the need to provide another password. Execution and the manual recovery required after export withdrawal are recorded in the [results report](2026-10-03-proxmox-csi-truenas-results.md).
