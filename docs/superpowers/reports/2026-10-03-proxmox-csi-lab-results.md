# Proxmox CSI disposable lab execution

Plan: [approved scope](2026-10-03-proxmox-csi-disposable-lab.md).
Date: 2026-10-03. Status: Debian NFS qualification passed; cleanup complete. TrueNAS 25 export qualification remains open.

## Authorization and ledger

The user approved the exact four-VM allocation, temporary NFS/API resources, synthetic-data tests and cleanup.
Production application and storage changes remain out of scope.

- Release preflight passed: k3s v1.37.0+k3s1, Proxmox CSI v0.20.0 and Telmate 3.0.2-rc10 releases exist upstream.
- Host identity/resource/collision preflight passed: IDs 980–983/9980 unused, no matching orphan disks; about 6.2GiB MemAvailable and 136GiB free on vm-pool before allocation.
- VM980 created: csi-lab-storage, 2GiB RAM/2 vCPU, 8GiB root and 24GiB synthetic data; DHCP 10.9.9.186.
- VM980 generation: `89e4186e-c941-43c8-8aec-75feda4dd4c1`; SMBIOS UUID `38632e2d-3769-4b11-9713-97fe139b7766`.
- Initial configuration failed because the clone already had a cloud-init disk at ide0. Inspected stopped VM, reused that disk, then continued. No clone retry.
- Ruling: VM980 keeps its inherited ide0 cloud-init disk; the tested worker module still uses ide2. This affects only the lab runner, not the integration under test.
- An early package install encountered cloud-init's apt lock. It stopped before disk initialization; cloud-init subsequently completed with no fatal errors. Resumed only after the process exited.
- Tools verified by upstream checksums: Terraform 1.16.5 and Helm 4.3.0. Lab state is local to VM980.
- Blank synthetic disk initialized once: UUID `b69cc03c-fa81-4ca4-9227-c50a67b61a66`; NFS export restricted to Proxmox 10.9.9.20 with synchronous writes.
- Created temporary storage registration csi-assessment-nfs, CSI/Terraform API users and scoped ACLs. Exact host resource ledger is `/var/tmp/csi-lab-20261003/ledger.json`; tokens stored privately and excluded from evidence.
- Ruling: disable Telmate's supported global minimum-permission precheck for this lab, because resource-scoped ACLs intentionally do not grant global authority. Proxmox still enforces each API operation's permissions. No production VM disk-write ACL is granted.
- Terraform init/validate and initial plan passed: only VMs981–983 to be created.
- First VM981 apply failed with 403 Datastore.AllocateSpace on local-zfs. Fresh host inventory confirmed no VM981 or orphan disk was created. Provider source confirms CloneQemuFull omits target storage, so it clones onto template900's datastore before the subsequent config update moves disks.
- User approved one transient 4GiB clone plus cloud-init on local-zfs at a time, raising peak lab allocation to about 60GiB. The lab Terraform user received allocation permission on that datastore.
- Allocated only `csi-assessment-nfs:9980/vm-9980-lab.raw`, 2GiB sparse, still unformatted. Host mount verified NFS4.2 over TCP with hard mounting and network locking.
- Runtime recovery/attachment tests proceeded after the storage-scope approval; results below.
- Cleanup complete: VMs980–983 and their disks, all three synthetic images, lab NFS mount/registration, API users/tokens, six roles and the pool were removed. No production resource changed.

No production code is being implemented. The lab performs the approved operational acceptance tests against stock
software; temporary setup commands are transport and lab configuration, not a new storage lifecycle framework.

## Result and architecture recommendation

Choose **unmodified Proxmox CSI over NFS** for the intended design; retain static iSCSI as a fallback. The Debian NFS
lab proved the essential behavior rather than only inferring it from source. It retains ordinary NFS on the NAS,
adds native attach/detach and PVC expansion, and recovers from complete cluster metadata loss through Git bindings.
This recommendation does not activate production storage or qualify the actual TrueNAS 25 export.

| Test | Observed result |
| --- | --- |
| Terraform coexistence | No-op plan and unrelated description update preserved the CSI attachment; final post-recovery plan also returned no changes |
| Healthy worker move | Same image and ext4 UUID, original data, exactly one configured attachment after movement |
| Full rebuild 1 | All three VM/root disks and datastore deleted; fresh namespace/PVC UIDs recovered all 1,000 initial records |
| Expansion and retry | Image 2GiB -> 4GiB while node expansion deliberately unavailable; stock retry later grew ext4, retaining data |
| Failed worker | Disconnected VM kept writing; original pod held, old VM confirmed powered off before takeover; data survived |
| Negative identities | Missing image refused without allocation; blank image formatted; ext4 image declared as xfs refused without changing its signature |
| NFS interruption | Writes stalled during the service outage, then resumed automatically |
| Storage VM reboot | New boot ID, automatic NFS and writer recovery, valid contiguous record sequence |
| Partial destroy and rebuild 2 | Paused after deleting control plane, observed old writer alive, confirmed abrupt power-off before replacement; fresh cluster recovered all 5,284 observed committed records at 4GiB |

Final filesystem UUID: `3dca49c8-66c3-44b0-8e3b-7eacb379fd59`. Usable filesystem capacity: 4,152,066,048 bytes.
Final SQLite `integrity_check`: `ok`; all payloads validated and append sequence contiguous, ending at 103283.
Canonical full-record SHA256: `d64cbdf1e341ce91c7fb956c562fcf1a4cd42af148983aa02f10fc9178a1acbf`.
The final attachment was worker1/scsi1; CSI and workload image digests matched the original run.

The [sanitized evidence bundle](evidence/2026-10-03-proxmox-csi-lab-results.json) contains the observations, actual
non-secret declarations, provider configuration and acceptance probes. Its embedded lab scripts are historical evidence,
not a supported deployment tool. It excludes Terraform state/full plans, credentials, private keys and kubeconfigs.
The [resource ledger](evidence/2026-10-03-proxmox-csi-lab-ledger.json) records the exact cleanup scope.

## Conditions the production integration must preserve

- Keep NFS registration, independently owned image paths, allocation and recoverable credentials outside disposable
  cluster state. Apps holds explicit retained PV/PVC bindings; no second per-service inventory in Ansible or Terraform.
- Use a persistent Proxmox pool for scoped permissions across VM deletion. VM-specific ACLs disappear with the VM.
  Separate Terraform allocation and CSI runtime identities. The lab discovered that Terraform updates also need audit
  access to the NFS datastore and disk configuration permission on the foreign owner ID.
- Keep VirtIO boot/IDE cloud-init ownership in Terraform and the SCSI subtree in CSI. The qualified provider rule is
  `ignore_changes = [startup_shutdown, disks[0].scsi]`; the supported global permission precheck was disabled while
  Proxmox enforced scoped permissions. This is shared infrastructure configuration, not backup orchestration.
- Use RWOP and indefinite not-ready/unreachable NoExecute tolerations for these workloads. **NotReady is not fencing**:
  the test proved an unreachable VM can still write. Stop and independently confirm the old VM before out-of-service
  release or forced pod deletion. Restart it only after the old disk attachment is gone. Native tolerations deliberately
  trade unattended failed-node availability for safety; ordinary healthy movement still works.
- Retain stable handles, ext4 policy, cache `none`, expandable StorageClass and explicit bindings. Request growth through
  the PVC first; reconcile Git's PV capacity only after successful CSI growth. Rebuild is independent of Velero freshness.

The failed-node release used the documented [Kubernetes non-graceful shutdown procedure](https://kubernetes.io/docs/concepts/cluster-administration/node-shutdown/#non-graceful-node-shutdown).
The workload hold and explicit power-off procedure are required conditions of this result, not stock automatic fencing.
Neither fdinfo nor `/proc/locks` showed a QEMU image lock in this lab; no global exclusion guarantee is claimed.

## Qualification limits and next gate

This was one Proxmox host and a synchronous Debian NFS 4.2 export over TCP, with synthetic SQLite data and stock
Proxmox CSI v0.20.0 / chart 0.5.10, Telmate 3.0.2-rc10, Terraform 1.16.5 and k3s v1.37.0+k3s1.
The chart digest was `sha256:618944174ec6f568f1ef739a83d900ccc2bfd6c7130e5bac29e3ff66f27b8da4`.
It did not test the TrueNAS 25 export, multiple Proxmox hosts, large/full volumes, torn NAS power loss or performance.
The 2GiB -> 4GiB test establishes the expansion path; it is not a capacity benchmark above 64GiB.
Blank-image and wrong-filesystem behavior was exercised; automatic repair policy is source-reviewed, not a deliberately
corrupted-filesystem repair qualification. No concurrent writable mount was deliberately forced.

The two fresh clusters were bootstrapped by lab tooling and applied non-secret manifests committed to a separate lab Git
repository. No old Kubernetes objects/datastore were restored. This proves the storage recovery primitive; production
ArgoCD discovery, external secret restoration and the complete Packer/Terraform pipeline still need shared integration.
The interrupted destroy was deliberately staged, not an observed provider crash. The first immediate post-crash image
probe returned Resource temporarily unavailable; a later read-only probe passed before replacement creation. Its cause
was not established and is not presented as a durability or locking guarantee.

The next live gate needs a dedicated disposable dataset/export on **TrueNAS 25**, its exact parent/path and access
scope, before repeating the relevant storage tests. Production datasets, services and existing Jellyfin safeguards remain
untouched. This is the remaining approval/access boundary; no TrueNAS mutation was included in the Debian lab approval.

## Execution after clone-storage approval

- Telmate then failed on its HA read with missing global Sys.Audit. Added only Sys.Audit at `/` for the lab Terraform user; production VM write permissions remain excluded.
- Terraform deleted its recorded partial VM981. Proxmox removed the VM-specific ACL too, so the next clone failed authorization. Host ACL and sanitized request inspection established this cause before retrying.
- Ruling: use a persistent Proxmox pool `csi-lab-20261003` for the three disposable cluster VMs and scope Terraform/CSI VM permissions to that pool. This is native Proxmox configuration, not a custom recovery controller. The pool survives cluster VM destruction and is in the cleanup ledger.
- Staged creation resumed: VMs981 and 982 succeeded, their root/cloud-init disks moved to vm-pool, and local-zfs had no remaining disks for either ID before the next clone. Host available memory stayed above 6GiB at those checkpoints.
- k3s v1.37.0+k3s1 binary verified against upstream SHA256 `39eed8f53f277497dfc2542f66eab0ed68a94dfc598946dbebfb50366916c7a2` inside VM980.


- All three cluster VMs created successfully; full Terraform plan after creation reports no changes. VM983 checkpoint had 7.37GiB host memory available. Final boot and cloud-init disks are all on vm-pool.

- Stock k3s and Proxmox CSI installed successfully. The static retained RWOP claim mounted a 2GiB ext4 filesystem on worker1 with UUID `3dca49c8-66c3-44b0-8e3b-7eacb379fd59`.
- Initial SQLite acceptance: 1,000 records, integrity_check=ok, canonical record SHA256 `93aaa7459e4a1fb4c53bfb6c901b2c3b3d81ea1a0f2b9c1e32ca44ac9691ccc4`.
- Recorded resolved CSI/workload image digests. Pinned the workload digest and committed only non-secret declarations in the lab Git repository before data tests.
- The no-op Terraform plan with a CSI disk passed. A description-only update preserved the SCSI subtree in the plan, but Proxmox demanded additional scoped permissions at apply: Datastore.Audit on the lab NFS datastore and VM.Config.Disk on reserved owner9980. These were granted without owner-VM allocation permission or production VM write permissions; the successful apply is recorded below.
- Lock observation: the lab QEMU process has the raw NFS image open, but neither its fdinfo nor /proc/locks showed an image lock. No automatic stale-writer protection is inferred; explicit old-VM stop-and-confirm remains required.

- Terraform coexistence PASS after scoped permissions were complete: description-only apply succeeded and all initial SQLite records remained readable.
- Healthy movement PASS: worker1 -> worker2, exactly one configured image attachment afterward, unchanged ext4 UUID and unchanged 1,000-record digest/capacity.
- First full destroy PASS: Terraform deleted VMs981–983 and their root disks. VM980 independently verified no old cluster VMs remained and the original 2GiB image retained UUID `3dca49c8-66c3-44b0-8e3b-7eacb379fd59`.
- A repeatability bug in the temporary staging helper inserted a duplicate pool attribute after terraform fmt aligned spacing. Terraform refused parsing before resource mutation. Removed the duplicate and removed configuration mutation from that helper; validation passed before rebuilding.
- First fresh-cluster recovery PASS: new namespace/PVC UIDs, unchanged image/UUID, all 1,000 initial records recovered from static Git declarations.
- Interrupted growth PASS: controller expanded the image to 4GiB while the deliberately unavailable node plugin left the filesystem at 2GiB. Restoring the stock plugin completed filesystem expansion automatically. Reconciled Git capacities to 4GiB and added a 2,000-record baseline.
- Negative cases PASS: blank image formatted as ext4; declared xfs on existing ext4 failed mounting without changing the signature; missing image returned NotFound and was not recreated. Adjusted an overly specific test assertion to check actual mount-error text plus the independently observed ext4 signature.
- Failed-worker test PASS: native indefinite not-ready/unreachable NoExecute tolerations kept the original pod on the disconnected, still-writing VM. Verified power-off through Proxmox before out-of-service release and replacement scheduling. Records survived; original VM restarted only after its image attachment was removed. A temporary nft syntax error was rejected before fault injection and corrected with syntax validation.
- NFS service outage PASS: commits stopped during the bounded outage and resumed after restoration, with integrity and payload checks passing.
- Storage VM reboot PASS: changed boot ID, automatic NFS/writer recovery, all payloads valid and append sequence contiguous.
- Second destroy exercised a deliberate pause after control-plane deletion, with the old writer still committing. Held replacement creation, abruptly powered the writer off, independently confirmed stopped, and deleted remaining cluster VMs. This simulates an interrupted destroy; it is not a newly observed Terraform provider failure.
- The immediate post-destroy blkid probe returned Resource temporarily unavailable. A later read-only probe succeeded with unchanged UUID before replacement creation. Cause not established; no lock or durability guarantee is inferred from this transient result.

- Second fresh-cluster recovery PASS: all 5,284 observed committed records, same UUID, 4GiB filesystem, new namespace/PVC UIDs and unchanged container digests. Final Terraform plan returned exit 0 with no changes.

- Cleanup PASS: Terraform removed the three cluster VMs; exact ledger-checked host cleanup removed VM980, remaining synthetic images, NFS registration/mount and all lab API resources. Verified no lab disks remained on vm-pool/local-zfs.

## Final documentation verification

A fresh read-only reviewer checked the recorded observations, declarations, limits and cleanup, independently recomputing
the final deterministic record checksum. It found no Critical/Important evidence or architecture issue. A final status
consistency pass corrected obsolete source-only and in-progress wording. Markdown links/fences, JSON parsing, embedded
Python syntax, exact credential-value exclusion, README image references and `git diff --check` passed. pre-commit was
unavailable. No additional runtime test is inferred from these documentation checks.

The reviewer did not independently access live infrastructure; the executor's recorded cleanup commands supply that
verification. Production integration remains unqualified, and embedded scripts remain historical evidence rather than
standalone supported tools. These limits are retained, not silently treated as passes.

## TrueNAS follow-up

Read-only NAS preflight now confirms the existing access route and healthy `apps` pool. The
[concrete TrueNAS test scope](2026-10-03-proxmox-csi-truenas-qualification.md) proposes an 8GiB disposable sibling dataset
and a separate export, with exact resource limits and cleanup. Its new NAS mutations await approval; the Debian lab
results above remain unchanged.
