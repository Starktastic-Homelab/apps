# Proxmox CSI over NFS assessment

Date: 2026-10-03. Status: source assessment complete; stock Proxmox CSI selected for disposable qualification. Stock filesystem handling accepted; runtime qualification not performed.
The user approved this comparison and explicitly authorized read-only access to Proxmox at 10.9.9.20.
Package versions, installed source, storage configuration and filtered worker metadata were read. No host was modified;
no NAS or Kubernetes API was accessed.

## Finding

Stock Proxmox CSI is a credible challenger for the user's primary goal: disposable k3s VMs and datastore, surviving
NAS data, stable bindings from Git, and no Velero freshness dependency. The installed Proxmox deletion code supports
keeping images owned by a separate reserved ID when deleting workers. Static recovery, attachment and expansion are
implemented upstream. A driver fork is not required for that normal recovery design.

It does not meet the additional existing prohibition on formatting or automatic filesystem repair. The distinction
matters: an intact existing filesystem is reused after cluster loss; losing Kubernetes metadata does not itself cause
formatting. A missing image is rejected before attach. An image at the expected path with no recognizable filesystem
can be formatted, and a recognized writable filesystem can undergo automatic repair. No supported switch disabling
both behaviors was found in v0.20.0. Neither candidate's stock driver checks the expected filesystem UUID.

The user accepted ordinary upstream CSI filesystem handling and chose disposable qualification. Proxmox CSI is therefore
the preferred candidate because it keeps NAS-side NFS and supplies native attachment and PVC expansion. This selection
is for qualification, not activation or a claim of completed runtime proof.
Static iSCSI still has its own unresolved CHAP credential-handling and shared-bootstrap qualification gaps.

The user explicitly reopened the comparison after declining a patched driver. The earlier blanket exclusion of
Proxmox CSI is superseded by this conditional comparison. No service migration or production deployment is authorized; the lab direction is approved, with its concrete allocation scope to be reviewed. Apps remains the only per-volume inventory; Ansible prepares shared infrastructure.

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
NFS configuration. The driver advertises 24 volumes per node by default; the attach helper searches SCSI slots 1 through 29. A node-label override cannot create more hardware slots, and other SCSI devices consume slots too.
[Publish and unpublish](https://github.com/sergelogvinov/proxmox-csi-plugin/blob/a7aacee7a2144a43be08503068fe0b9caf3d0b4e/pkg/csi/controller.go#L512-L680),
[attachment helper](https://github.com/sergelogvinov/proxmox-csi-plugin/blob/a7aacee7a2144a43be08503068fe0b9caf3d0b4e/pkg/csi/utils.go#L382-L479).

ControllerExpandVolume resizes an attached VM disk and requests node filesystem expansion; node expansion is advertised
and implemented. An unattached volume currently returns an error from controller expansion. Unlike the baseline
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
   The pinned schema represents `disks` as a single-item list containing the `scsi` subtree. The candidate Terraform
   lifecycle entry is `disks[0].scsi`, alongside the existing `startup_shutdown` ignore. This is source-derived syntax,
   not a validated plan. Qualify no-op apply, an unrelated VM update and boot-disk changes; each must leave CSI SCSI
   attachments intact while retaining Terraform ownership of VirtIO boot and IDE cloud-init disks. Do not ignore every
   disk as a shortcut. Terraform is unavailable in this assessment environment; no provider plan was run.
   [Telmate schema](https://github.com/Telmate/terraform-provider-proxmox/blob/c0d11566fd9027267862add89af0e6948ff0dfb0/proxmox/Internal/resource/guest/qemu/disk/schema.go#L154-L240),
   [Telmate SCSI mapper](https://github.com/Telmate/terraform-provider-proxmox/blob/c0d11566fd9027267862add89af0e6948ff0dfb0/proxmox/Internal/resource/guest/qemu/disk/sdk_disks.go#L225-L303).
2. **Filesystem admission:** the CSI node code calls FormatAndMountSensitiveWithFormatOptions. Static provisioning
   alone does not make it mount-only or verify the expected filesystem UUID. The user has explicitly
   accepted stock handling for this candidate; it does not enforce the former format/repair prohibition.
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

## Comparison against static iSCSI

Both alternatives use one-time allocation and explicit retained PV/PVC bindings. Neither restores the correct data
merely by recreating a dynamically provisioned PVC. Both still need recoverable secrets, stable storage identity and
old-writer exclusion. NAS replacement entails a deliberate data transfer and infrastructure changes for either option.

| Requirement or routine operation | Stock Proxmox CSI over NFS | Stock democratic-csi node-manual iSCSI |
| --- | --- | --- |
| SQLite storage semantics | Guest ext4 on virtual SCSI; NAS serves image files to Proxmox | Guest ext4 on an iSCSI LUN |
| Empty Kubernetes datastore | Reapply exact retained disk handles from Git | Reapply portal/IQN/LUN and retained bindings from Git |
| Destroy all k3s VMs | Foreign-owned images survive according to installed source; reserve owner ID outside destroy scope | NAS LUN is outside Proxmox worker disk inventory |
| Healthy pod move | CSI detach/attach and node mount | Node logout/login and mount; no controller attachment |
| Unreachable old writer | Explicit old-VM stop-and-confirm still required | Same requirement; RWOP alone does not fence another cluster |
| Grow beyond 64GiB | Native controller and filesystem expansion, while attached; expandable StorageClass required | Separate NAS growth/rescan/filesystem growth procedure; ordinary PVC edits are insufficient |
| Retained filesystem policy | Can mkfs an unrecognized filesystem; automatic fsck; no UUID guard | Existing supported configuration suppresses ext4 formatting and checking; no driver UUID guard |
| NAS portability | Standard NFS; no TrueNAS management API in CSI | Standard iSCSI; backend-specific one-time allocation |
| Other infrastructure dependency | Proxmox API, hotplug, finite SCSI slots, Terraform attachment ownership | Guest initiator packages/services, target access configuration |
| Authentication | Recoverable Proxmox API token; restricted NFS export; no guest CHAP | Current CHAP credential argument exposure remains unresolved; no-CHAP policy not approved |
| Custom work remaining | Shared bootstrap/bindings and failure recovery; potential UUID check remains external | Same plus native NAS allocation/growth procedures and initiator preparation |

The existing iSCSI configuration is visible in
[retained-iscsi values](../../../infrastructure/system/retained-iscsi/values.yaml). Its ext4 `-n` format option is a dry run,
and filesystem checking is disabled. The inherited staging path nevertheless mounts writable storage and can grow the
filesystem. It is not a forensic, non-mutating mount. Expected UUID checks and writer exclusion currently come from
external safeguards, not the driver. Do not present iSCSI as fully turnkey or fully qualified while holding Proxmox CSI
to a stricter standard. Its remaining CHAP issue is documented in the
[proposal](../specs/2026-10-03-portable-iscsi-native-lifecycle-proposal.md).

For Proxmox, the existing-disk PV and PVC must name the same expandable StorageClass, with PVC `volumeName` and PV
claimRef fixed explicitly. The upstream chart includes the resizer and sets `allowVolumeExpansion: true` on its classes.
Increase the PVC request first and let CSI expand the image/filesystem; do not pre-increase PV capacity in a way that
makes Kubernetes believe expansion already happened. Reconcile the durable Git capacity after successful growth so a
fresh cluster declares the actual disk size. Interrupted expansion and retry still need testing. This sequence is part
of volume administration, not an extra pre-merge step for routine VM rebuilds.
[Chart StorageClass](https://github.com/sergelogvinov/proxmox-csi-plugin/blob/a7aacee7a2144a43be08503068fe0b9caf3d0b4e/charts/proxmox-csi-plugin/templates/storageclass.yaml),
[Kubernetes expansion](https://kubernetes.io/docs/concepts/storage/persistent-volumes/#expanding-persistent-volumes-claims).

## What clean-cluster recovery would actually do

1. Terraform stops and destroys the old k3s VMs, including their root disks and old Kubernetes datastore. NAS storage,
   the Proxmox NFS registration and separately owned CSI images remain outside that destroy scope.
2. Terraform creates replacement VMs with hotplug enabled and appropriate SCSI controllers. Shared bootstrap restores
   k3s, node identity/topology, externally recoverable API credentials and the stock CSI deployment.
3. ArgoCD reapplies static PV/PVC bindings naming the original image paths and the existing application claim names.
   No old PVC UID, backup checkpoint or Velero restore is needed.
4. CSI verifies the image exists, attaches it to the selected worker, and stages its filesystem. The filesystem-policy
   difference occurs here. Applications start after storage is mounted.

No service list is added to Terraform or Ansible. Terraform does need a shared rule leaving CSI SCSI attachments under
CSI ownership; that is VM configuration ownership, not backup orchestration. Ordinary image PR merges retain their
existing user-facing procedure once this setup and its tests pass. Old-writer stop verification must fail closed if a
partial destroy leaves a VM running. This is a proposed supported flow, not an assertion that today's pipeline already
implements or has tested it.

## Durability, permissions and qualification boundary

Use supported cache settings that preserve flushes, initially `cache: none`, and an NFS export whose server honors
synchronous writes. Do not use unsafe caching or disable NAS synchronous-write guarantees. The inspected Proxmox
block-device builder enables `no-flush` for the unsafe cache mode. QEMU documents exclusive image locking, with OFD
locks preferred and caveats for POSIX fallback. Actual NFS locking, server reboot and partition behavior must be observed;
these documented locks do not replace confirmed old-writer shutdown. No performance or durability benchmark was run.
[Proxmox cache mapping](https://github.com/proxmox/qemu-server/blob/a7b4240bba1dd493d6c76daad1e70af62b2ebcc8/src/PVE/QemuServer/Blockdev.pm#L260-L267),
[QEMU image locking](https://www.qemu.org/docs/master/system/images.html#image-locking).

The upstream non-replication role includes VM audit/disk configuration and datastore audit/allocation permissions.
Scope the token to required resources and qualify that scope; do not enable the broader replication role. Unlike
node-only static iSCSI, the CSI controller receives a management credential capable of changing VM disks. Keep that
credential outside Git plaintext and recoverable independently of the old cluster. Restrict the NAS NFS export to the
Proxmox client addresses. No new credential was created in this assessment.
[Upstream permissions](https://github.com/sergelogvinov/proxmox-csi-plugin/blob/a7aacee7a2144a43be08503068fe0b9caf3d0b4e/docs/install.md).

Read-only resource preflight found approximately 6.1GiB available RAM, no swap and 136GiB available on `vm-pool`.
A follow-up memory inspection showed about 12.3GiB in ZFS ARC, with a configured minimum near 3.9GiB. ARC can reclaim
memory, so the initial available-RAM number alone does not prove an 8GiB lab is impossible. Reclaim is not a guaranteed
reservation: the lab proposal requires staged startup and a host headroom stop condition. No production VM was stopped
or resized. No spare static IP addresses were established; the proposed lab uses DHCP on the existing management bridge.
The [filtered preflight evidence](evidence/2026-10-03-proxmox-qualification-preflight.json) records only relevant inventory,
capacity and bridge addresses; it does not authorize allocation or network changes.

With the filesystem policy accepted, the proposed bounded remote lab consists of one disposable storage VM
serving synthetic NFS images, one k3s server and two workers. Keep the storage VM outside the
three-VM destroy scope. Run stock Proxmox CSI against disposable SQLite data. Debian NFS results alone
would not qualify the actual TrueNAS 25 export. Required acceptance observations are:

| Case | Required observation |
| --- | --- |
| Normal Terraform apply and unrelated VM update | CSI disk remains attached; boot/cloud-init configuration remains managed |
| Destroy/recreate all three k3s VMs and datastore | Same image/LUN and filesystem identity, same SQLite content, restored entirely from Git and external secrets |
| Healthy worker movement | One writer at a time, original data mounts on replacement worker |
| Unreachable writer / interrupted destroy | No new writer until old VM power-off is independently confirmed |
| Missing image/LUN | Failed mount; no empty replacement provisioned |
| Blank or wrong filesystem at expected identity | Behavior recorded against the explicitly chosen policy; destructive tests use only disposable data |
| PVC expansion and interruption | Larger usable filesystem, preserved data, repeatable retry and correct subsequent fresh-cluster binding |
| NFS or iSCSI outage and storage-server restart | Defined I/O failure/recovery, no concurrent writers, SQLite integrity and committed test records checked |

These acceptance tests are expanded into a
[bounded lab proposal](2026-10-03-proxmox-csi-disposable-lab.md) with resource identity, networking, disk paths, allocation
limits and deletion scope for approval. No runtime proof is manufactured from a
passing source probe.

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

Validation is limited to documentation, sanitized evidence and the isolated Perl source probe. No deployment manifests
changed, and no runtime storage test, Terraform plan or Go integration suite ran. pre-commit is unavailable.

## Decision

The user selected "Accept stock filesystem handling; qualify Proxmox CSI in a disposable lab." Proceed with the stock
driver as the preferred candidate for qualification. The no-format/no-automatic-repair prohibition is explicitly relaxed
for this candidate. Preserve static iSCSI as fallback and retain existing live safeguards until an activation decision.

The lab must establish the Terraform SCSI ownership rule and full cluster-destruction/recovery behavior before any
production selection is called qualified. Stock handling does not mean silently switching to a newly allocated volume
when a declared image is missing. Keep explicit bindings and missing-image failure behavior.

The [lab proposal](2026-10-03-proxmox-csi-disposable-lab.md) is ready for review of its bounded host changes. No upstream
issue, PR or message has been sent. No VM was allocated, disk mounted or production resource changed.
