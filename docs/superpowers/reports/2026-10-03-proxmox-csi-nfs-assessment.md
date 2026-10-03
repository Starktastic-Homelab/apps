# Proxmox CSI over NFS assessment

Date: 2026-10-03. Status: credible challenger to the accepted static iSCSI proposal; not selected for deployment.
The user approved this comparison and explicitly authorized read-only access to Proxmox at 10.9.9.20.
Package versions, installed source, storage configuration and filtered worker metadata were read. No host was modified;
no NAS or Kubernetes API was accessed.

## Finding

Proxmox CSI over NAS-hosted NFS has a plausible native path for retained disks to survive worker VM destruction.
It supports static bindings and implements controller/node expansion. This makes it worth qualifying against the iSCSI
baseline. It is not ready to activate: Terraform disk reconciliation conflicts with CSI attachment, and automatic
formatting/writer exclusion need explicit qualification. The installed Proxmox ownership/deletion functions match the
inspected upstream functions; actual VM-destruction behavior has not been tested.

The existing iSCSI proposal remains intact. No service migration, deployment or lab allocation is authorized by this
assessment. Apps remains the sole source of per-volume declarations; Ansible does not gain a second service inventory.

## Source anchors

| Component | Inspected revision |
| --- | --- |
| Proxmox CSI | v0.20.0, `a7aacee7a2144a43be08503068fe0b9caf3d0b4e` |
| Terraform repository main | `50582000a7f6b873d2bb436f4850a3e62f56e2ce`; remote providers.tf, VM module and apply workflow read |
| Telmate Terraform provider | Configured 3.0.2-rc10, tag resolves to `c0d11566fd9027267862add89af0e6948ff0dfb0` |
| Telmate API dependency | `9cba66824699e24334db714e69237cf2a3b04d2e`, from the provider's go.mod |
| CSI API dependency | sergelogvinov/go-proxmox v0.4.0, `fbd3a30de42e9ddcafa4161b916137a5ebcc8f1a` |
| Proxmox qemu-server | Upstream `a7b4240bba1dd493d6c76daad1e70af62b2ebcc8`; installed 9.2.8 destroy_vm function matches exactly |
| Proxmox pve-storage | Upstream `f1a6ef435f53c957bad542db2b7b401c7b46c191`; installed libpve-storage-perl 9.1.10 parse_volname function matches exactly |

The [sanitized host observations](evidence/2026-10-03-proxmox-readonly-results.json) record installed file hashes and
function comparisons. pve-manager is 9.2.20; pve-qemu-kvm is 11.0.3-3. Worker VMs 201/202 and master 200 run on `pve`,
with disk hotplug enabled, virtio-scsi-pci controllers and no SCSI disk attachments in the inspected configs. Their
boot disks use VirtIO. No NFS storage is currently registered in Proxmox. Owner ID 9999 has no VM/container in the
queried inventory; this does not reserve it or prove no orphaned disk already uses it. No storage pool was changed.

## Data path and ownership

The NAS exports NFS to Proxmox. Proxmox stores a disk image there, presents it as a SCSI disk to a worker VM, and the
worker mounts ext4 for the pod. SQLite sees guest filesystem semantics. QEMU, NFS and the NAS still need correct flush
behavior; using a virtual disk does not excuse unsafe write caching or simultaneous mounts.

The CSI controller uses `controllerVmID` (default 9999) when allocating disk names, separately from the worker VM ID.
For NFS, a normal raw image has a form such as `9999/vm-9999-pvc-<id>.raw`. This is an illustrative source-derived name,
not an allocated homelab resource. Shared-storage handles omit the Proxmox node zone: `region//storage/image-path`.
Reserve the owner ID outside disposable-worker IDs and do not use its default without checking for collisions.
[Allocation and shared handles](https://github.com/sergelogvinov/proxmox-csi-plugin/blob/a7aacee7a2144a43be08503068fe0b9caf3d0b4e/pkg/csi/controller.go#L284-L429),
[volume paths](https://github.com/sergelogvinov/proxmox-csi-plugin/blob/a7aacee7a2144a43be08503068fe0b9caf3d0b4e/pkg/utils/volume/volume.go#L39-L101).

The inspected NFS plugin inherits the file-storage parser, which extracts ownership from the image directory. The
inspected QEMU VM-destruction code frees referenced disks only when their owner matches the VM being deleted. This
includes attached, unused and pending entries. Consequently a worker-owned boot disk can be deleted while a CSI image
under a different owner survives. Deleting the owning VM or its storage remains destructive.
[NFS plugin](https://github.com/proxmox/pve-storage/blob/f1a6ef435f53c957bad542db2b7b401c7b46c191/src/PVE/Storage/NFSPlugin.pm),
[ownership parser](https://github.com/proxmox/pve-storage/blob/f1a6ef435f53c957bad542db2b7b401c7b46c191/src/PVE/Storage/Plugin.pm#L804-L816),
[VM destruction](https://github.com/proxmox/qemu-server/blob/a7b4240bba1dd493d6c76daad1e70af62b2ebcc8/src/PVE/QemuServer.pm#L1838-L1926).

The configured Telmate provider calls its Guest.Delete API. The pinned dependency stops a running VM before deletion
and issues the VM DELETE request, optionally with purge for HA cleanup. That path does not request
destroy-unreferenced-disks. This is stronger source evidence than relying on the CSI keep annotation, which concerns
CSI volume deletion and cannot control Terraform or arbitrary NAS deletion.
[Provider deletion](https://github.com/Telmate/terraform-provider-proxmox/blob/c0d11566fd9027267862add89af0e6948ff0dfb0/proxmox/helper_guest.go#L14-L32),
[guest stop/delete](https://github.com/Telmate/proxmox-api-go/blob/9cba66824699e24334db714e69237cf2a3b04d2e/proxmox/config__guest__delete.go),
[DELETE request](https://github.com/Telmate/proxmox-api-go/blob/9cba66824699e24334db714e69237cf2a3b04d2e/proxmox/vmref.go#L133-L152).

## Recovery, movement and growth

The driver documents PV/PVC bindings for existing disks. Preserve the real disk handle in Git, use explicit claimRef
name/namespace without an old UID and explicit PVC volumeName, retain the PV, and protect GitOps deletion. Recreating a
normal dynamically provisioned PVC does not establish recovery: creation still derives its image name from the CSI
request name. Static binding remains the proposed recovery mechanism for this candidate.
[Existing-disk example](https://github.com/sergelogvinov/proxmox-csi-plugin/blob/a7aacee7a2144a43be08503068fe0b9caf3d0b4e/docs/faq.md).

ControllerPublish checks that the referenced image exists before attaching it; errors return without an allocation
call in that path. Shared volumes can be located via an eligible Proxmox node. Normal unpublish removes the disk from
the worker, and publish attaches it to the next worker. This is source evidence for native movement, not proof of
safe takeover from an unreachable worker. Its attach helper checks the destination VM; do not infer a global writer
fence from this or from Kubernetes access modes. QEMU image locking and failure behavior must be tested on the actual
NFS configuration. The pinned attach helper searches SCSI slots 1 through 29, another capacity constraint to consider.
[Publish and unpublish](https://github.com/sergelogvinov/proxmox-csi-plugin/blob/a7aacee7a2144a43be08503068fe0b9caf3d0b4e/pkg/csi/controller.go#L512-L680),
[attachment helper](https://github.com/sergelogvinov/proxmox-csi-plugin/blob/a7aacee7a2144a43be08503068fe0b9caf3d0b4e/pkg/csi/utils.go#L382-L479).

ControllerExpandVolume resizes an attached VM disk and requests node filesystem expansion; node expansion is advertised
and implemented. An unattached volume currently returns an error from controller expansion. Unlike the selected
democratic-csi node-manual profile, this provides a normal expansion path to qualify with an expandable StorageClass.
Verify it for recovered static claims, including Git capacity reconciliation and interrupted growth; advertised support
is not an end-to-end result for this homelab.
[Controller expansion](https://github.com/sergelogvinov/proxmox-csi-plugin/blob/a7aacee7a2144a43be08503068fe0b9caf3d0b4e/pkg/csi/controller.go#L959-L1026),
[node expansion](https://github.com/sergelogvinov/proxmox-csi-plugin/blob/a7aacee7a2144a43be08503068fe0b9caf3d0b4e/pkg/csi/node.go#L455-L520).

## Integration gaps

1. **Terraform reconciliation:** the current VM module declares IDE cloud-init and VirtIO boot storage, and only ignores
   startup_shutdown changes. The Telmate disk mapper marks omitted SCSI slots for removal. CSI uses those SCSI slots.
   Separate ownership of CSI attachments from Terraform-managed boot/cloud-init disks; qualify a narrowly scoped
   SCSI ignore rule with this provider instead of copying the upstream example for bpg/proxmox. The source establishes
   an attachment-removal conflict, not that every ordinary apply deletes the foreign-owned image itself.
   [Telmate SCSI mapper](https://github.com/Telmate/terraform-provider-proxmox/blob/c0d11566fd9027267862add89af0e6948ff0dfb0/proxmox/Internal/resource/guest/qemu/disk/sdk_disks.go#L225-L303).
2. **Filesystem admission:** the CSI node code calls FormatAndMountSensitiveWithFormatOptions. Static provisioning
   alone does not make it mount-only or verify the expected filesystem UUID. Preserve the original identity/no-format
   requirement, and establish an enforceable supported guard before activation. No claim that stock defaults meet it.
   [Node staging](https://github.com/sergelogvinov/proxmox-csi-plugin/blob/a7aacee7a2144a43be08503068fe0b9caf3d0b4e/pkg/csi/node.go#L133-L206).
   The pinned mount-utils v0.36.3 dependency reuses a recognized filesystem but runs mkfs when no filesystem signature
   is found, and invokes fsck -a for an existing writable filesystem. Format-probe errors return without formatting.
   The driver's format options expose block/inode sizes; no existing-filesystem-only setting was found in this release.
   Read-only mounting avoids formatting but cannot serve Jellyfin's writable database. A bootstrap check alone does not
   remove these later staging behaviors.
   [Dependency staging behavior](https://github.com/kubernetes/mount-utils/blob/v0.36.3/mount_linux.go#L490-L594).
3. **Shared platform setup:** register NAS NFS storage in Proxmox, reserve disk-owner identity, configure CSI API access
   and secrets, set region/VM identity and attachment prerequisites. This trades guest iSCSI/CHAP setup for Proxmox
   integration. It keeps NAS-provider portability but depends on Proxmox; neither setup is service-specific Ansible code.
4. **Runtime evidence:** installed ownership/deletion source matches, but still qualify safe cache/flush settings,
   NFS loss, healthy rescheduling, failed-writer exclusion, Terraform apply and
   full destroy/recreate, missing/wrong images, and expansion. Preserve the existing user-facing merge procedure.

## Synthetic verification

The [source probe](evidence/2026-10-03-proxmox-destroy-probe.pl) checks the upstream file's SHA-256, extracts its actual
destroy_vm function and executes it with in-memory storage/config mocks. Eight assertions passed: source hash, worker
config deletion and foreign-image preservation in attached/unused/pending cases, plus an owning-VM deletion negative
control. Storage ownership resolution itself is mocked, with its real parser inspected separately. No Proxmox modules,
network operations, mount commands or real deletion run in this probe. The installed function was separately read and
matched exactly to the probed function. This does not verify a real Terraform destruction or data durability.

```sh
perl docs/superpowers/reports/evidence/2026-10-03-proxmox-destroy-probe.pl /path/to/qemu-server/src/PVE/QemuServer.pm
```

Whitespace, local Markdown links, fences and Perl syntax checks pass. pre-commit is unavailable. No deployment manifests
changed and no runtime storage test or Go integration test ran. No production switch should be inferred from the
positive ownership result. The next design work should settle enforceable existing-filesystem admission and scoped
Terraform disk ownership before preparing a bounded disposable qualification plan. Shared platform setup must include
a Proxmox NFS storage entry; applications continue using Git-declared claims.

## Decision before implementation

Preserving the strict recovery contract with this driver would require supported filesystem admission or a driver
enhancement. The narrow candidate enhancement is an opt-in retained-volume mode that requires the declared filesystem
type/UUID, returns an error on missing/mismatched/uncertain identity, and mounts without mkfs or automatic fsck. New-volume
initialization stays a separate explicit operation. Existing expansion behavior would need regression qualification.
This is a design option, not implemented code or a claim of upstream acceptance.

Decide whether maintaining a pinned driver build while seeking upstream support is acceptable. If only unmodified
upstream drivers are acceptable, retain iSCSI as the implementation baseline while this feature remains unavailable.
Do not silently relax the no-format/no-repair requirement, wrap mkfs binaries, or add custom per-service mount scripts.
No upstream issue, PR or message has been sent.
