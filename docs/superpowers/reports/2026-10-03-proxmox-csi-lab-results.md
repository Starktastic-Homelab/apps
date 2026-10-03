# Proxmox CSI disposable lab execution

Plan: [approved scope](2026-10-03-proxmox-csi-disposable-lab.md).
Date: 2026-10-03. Status: waiting for approval of transient local-zfs cloning; no runtime qualification result yet.

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
- Pending user decision: allow one transient 4GiB clone plus cloud-init on local-zfs at a time, raising peak lab allocation to about 60GiB. No broader permission has been granted yet.
- Allocated only `csi-assessment-nfs:9980/vm-9980-lab.raw`, 2GiB sparse, still unformatted. Host mount verified NFS4.2 over TCP with hard mounting and network locking.
- Runtime recovery/attachment tests: not started.
- Cleanup: pending for recorded lab resources. No production resource changed.

No production code is being implemented. The lab performs the approved operational acceptance tests against stock
software; temporary setup commands are transport and lab configuration, not a new storage lifecycle framework.

## Current checkpoint

Only VM980 is running. VMs981–983 have not been created. The NFS registration, scoped lab API identities and one
unformatted 2GiB synthetic image exist and are recorded in the
[sanitized creation ledger](evidence/2026-10-03-proxmox-csi-lab-ledger.json). No production VM configuration or disk was changed.

The pinned CSI chart rendered successfully on VM980. Its digest is
`sha256:618944174ec6f568f1ef739a83d900ccc2bfd6c7130e5bac29e3ff66f27b8da4`; the generated StorageClass has Retain and
allowVolumeExpansion enabled. Lab YAML parsing passed there; PyYAML is unavailable on the workstation and was not
installed on it. No Kubernetes deployment, attach/detach, resize or destroy/recovery test has run.

The permission failure is a lab-provisioning issue, not evidence against Proxmox CSI. The pinned provider's full-clone
request omits destination storage; its later disk update moves storage before resizing. Requested scope adjustment:
allow allocation on local-zfs for one 4GiB transient clone plus cloud-init at a time, then move to vm-pool. Peak lab disk
capacity becomes approximately 60GiB; permanent disks remain on vm-pool. No production VM write ACL is requested.
[Provider clone request](https://github.com/Telmate/terraform-provider-proxmox/blob/c0d11566fd9027267862add89af0e6948ff0dfb0/proxmox/resource_vm_qemu.go#L580-L622),
[move before resize](https://github.com/Telmate/proxmox-api-go/blob/9cba66824699e24334db714e69237cf2a3b04d2e/proxmox/config__qemu.go#L722-L729).

Do not rerun cloning or widen permissions until that decision arrives. Existing lab resources remain available for
continuation; cleanup is still authorized under the original scope if the user chooses to stop qualification.
