# Proxmox CSI disposable qualification proposal

Date: 2026-10-03. Status: stock-filesystem policy and qualification direction approved; bounded host changes below await approval.
Companion: [source assessment](2026-10-03-proxmox-csi-nfs-assessment.md).

## Question and success condition

Can unmodified Proxmox CSI recover the same SQLite data after Terraform destroys all three k3s VMs and their datastore,
using only the original external NFS images, Git declarations and externally recoverable secrets? Also prove normal
worker movement and PVC growth, and that ordinary Terraform updates leave CSI attachments alone. The user accepted
stock filesystem handling. No patched driver, custom attachment controller or Velero restoration participates.

## Proposed resources and host changes

Host: Proxmox `pve`, 10.9.9.20. The inspected inventory contains no guests 980–983 or 9980. Recheck these IDs, names and
storage paths immediately before creation. A collision aborts; never adopt or delete a pre-existing resource.

| ID | Name | Role | RAM | vCPU | Disks on vm-pool |
| --- | --- | --- | --- | --- | --- |
| 980 | csi-lab-storage | Debian NFS server and lab tooling runner; survives cluster destruction | 2GiB | 2 | 8GiB root plus 24GiB synthetic-data disk |
| 981 | csi-lab-server | Disposable k3s server | 2GiB | 2 | 8GiB root |
| 982 | csi-lab-worker-1 | Disposable k3s worker | 2GiB | 2 | 8GiB root |
| 983 | csi-lab-worker-2 | Disposable k3s worker | 2GiB | 2 | 8GiB root |

Use full clones of existing template 900, with distinct fresh identities and cloud-init. Total ceiling: 8GiB RAM,
8 vCPUs and 56GiB guest-disk capacity, plus small cloud-init disks. No GPU/PCI passthrough, production disks, production
Kubernetes credentials, production ArgoCD discovery, or modifications to template 900. Disallow host-start auto-boot.

All four VMs use DHCP on existing `vmbr0` (10.9.9.0/24). Discover addresses through their Proxmox guest agents and record
MAC, VMID, VM generation and guest identity before commands. No guessed static IP, host bridge, router or VLAN change.
If DHCP or guest-agent discovery fails, stop and request the missing network/access information. This is a separate
cluster on a shared management network, not a claim of physical network isolation. Restrict guest services to the
required lab peers and the Proxmox NFS client. Use generated lab-only SSH keys and bootstrap secrets.

Temporary host resources:

- Proxmox NFS storage entry `csi-assessment-nfs`, node-restricted to `pve`, pointing to VM980's `/srv/csi-lab/nfs` export.
  Permit NFS access only from 10.9.9.20. This does mount the lab export on the Proxmox host. No existing storage entry is
  edited. An existing entry with that name aborts the setup.
- Reserved CSI disk-owner ID 9980, with images exclusively under `csi-assessment-nfs:9980/`. No VM 9980 is created.
  Before use, check for existing image directories as well as VM/container ID collisions.
- A lab-only Proxmox API identity/token and ACLs limited to the lab guests, owner namespace and required storage.
  Begin with the upstream non-replication CSI privileges. Keep Terraform allocation authority separate from CSI
  runtime authority. If the intended ACL scope is insufficient, record the failed operation before considering wider
  scope; do not grant production VM disk-write permissions. Never pass passwords/tokens as command arguments.

The resource snapshot showed about 6GiB MemAvailable plus about 12GiB in ZFS ARC, with ARC minimum near 4GiB. This is
not reserved capacity. Start VMs individually and observe reclamation; require at least 2GiB host MemAvailable after
each start and no OOM events. If this cannot be maintained, stop lab VMs and ask for capacity; do not alter production
VM memory or host ARC settings. Require at least 70GiB free on vm-pool before creating the lab. No swap configuration
changes. The host resource check is a safety bound, not a performance benchmark.

## Execution boundaries

The workstation is only an editor and read-only/remote-command transport. No local Ansible deployment, privileged
containers, iSCSI session, mount, mkfs or systemd qualification. Install and run Terraform, Helm, kubectl and lab storage
tools only in VM980 or the explicitly identified lab VMs. Use separate Terraform state in VM980, preserved outside the
three-VM destroy scope; never initialize the production S3 backend or copy its credentials. Retrieve only sanitized
results to this documentation branch.

Pins: Proxmox CSI v0.20.0 / chart 0.5.10, Telmate provider 3.0.2-rc10 and the inspected VM module structure. Capture
resolved image digests and tool/package versions before tests. Use the homelab's declared k3s version after checking
its current upstream availability and compatibility; the inspected Ansible checkout declares v1.37.0+k3s1. Do not
silently substitute another Kubernetes version if this pin is unavailable. Terraform tooling must satisfy the repository's
version constraint; pin the chosen released binary and checksum in the lab evidence before executing it.

Prepare lab-only configuration from the inspected module with `startup_shutdown` and `disks[0].scsi` ignored, retaining
VirtIO boot and IDE cloud-init management. First run validate and inspect the plan inside VM980. No apply may reference
VMs outside 981–983 or existing production pools as managed resources. VM980, NFS registration, credentials and the
retained images are deliberately outside this cluster-only destroy state. Maintain a creation ledger for exact cleanup.

Use stock chart settings with `cache: none`, `Retain`, a reserved controller owner ID, an expandable StorageClass and
explicit static PV/PVC binding with the required parameters also present in the static PV volume attributes. Allocate and initialize one 2GiB synthetic filesystem separately from recovery. Record
its filesystem UUID, image handle and SQLite test records in the evidence. Keep these in lab-only Git declarations,
without plaintext secrets. Use no production app values or storage manifests. Rebuilding must use the same declarations,
not saved Kubernetes object exports. The runner provides shared bootstrap, not per-service recovery scripts.

## Tests and decision rules

1. Establish SQLite data with transaction sequence IDs, known committed records, checksums and `integrity_check`.
   Record storage identity and attached VM. Data exists only for this lab.
2. Refresh and plan with Telmate; expect no CSI attachment removal. Apply a bounded unrelated VM setting change,
   then test a boot-disk change/replacement. Keep boot/cloud-init ownership and CSI SCSI ownership distinct.
3. Move the workload between the two healthy workers. Verify detach/attach, unchanged filesystem identity and records,
   and absence of simultaneous writable mounts. Capture the actual QEMU image locks on NFS.
4. Delete the three k3s VMs through the provider, including root disks. Recreate them with a fresh datastore. Restore
   driver, secrets and static declarations; verify the same external image, filesystem and SQLite content. Repeat once
   with the workload active at destruction to exercise crash recovery rather than assuming graceful shutdown.
5. Increase the PVC request from 2GiB to 4GiB while attached. Verify usable filesystem capacity and old records. Test
   an interrupted expansion/retry, reconcile Git capacity after success, then repeat fresh-cluster binding. This tests
   the expansion mechanism, not large-volume performance or full-capacity behavior beyond 64GiB.
6. On separate disposable images, exercise missing-image, blank-image and wrong-filesystem cases. A missing image must
   fail without allocating a replacement. Record the accepted stock behavior for blank/signature-damaged images and
   automatic repair. Do not imply the driver enforces a filesystem UUID it does not check.
7. Simulate a worker becoming unreachable to the lab control plane while its VM remains running. Do not deliberately
   force a second filesystem mount. Record whether native attachment blocks; prove stop-and-confirm admits takeover
   only after that old VM is powered off. Repeat a partial cluster-destroy failure. Uncertain power state blocks release.
8. Interrupt only VM980's lab NFS service, then restart it/the storage VM. Record guest I/O and recovery behavior,
   SQLite integrity, committed records and lock ownership. Do not disrupt the production NAS, host bridge or VM storage.

A source expectation or an attempted test is not a pass. Preserve commands, exit codes and before/after observations
without credentials. Any unexplained data loss, concurrent writer, attachment of an image other than the declared handle, Terraform interference or
unrecoverable binding blocks selection. No attempt to fix a failure by silently introducing a driver patch or custom
per-service lifecycle machinery. Review material failures before changing the agreed approach.

## Cleanup and remaining production qualification

After evidence is captured, stop lab writers, detach lab CSI disks, and remove only resources in the creation ledger:
VMs 980–983, their own disks, the exact synthetic images under owner 9980, the temporary NFS registration and lab-only
API identity/ACLs. Cleanup is destructive only to this synthetic lab and must be included in allocation approval.
Do not delete all disks by an unverified prefix or touch an object that predates this run. Preserve sanitized evidence.

Passing this lab would qualify the tested Debian NFS configuration and the inspected Proxmox/Terraform integration.
It would not by itself prove the actual TrueNAS 25 export's flush, locking, outage or capacity behavior. The subsequent
bounded TrueNAS check needs a dedicated disposable dataset/export and its own access/scope authorization. Existing
Jellyfin migration, live placement, production volume initialization and release safeguards remain untouched.
