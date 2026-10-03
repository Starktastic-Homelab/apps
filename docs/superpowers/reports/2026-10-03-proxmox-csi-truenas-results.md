# Proxmox CSI on TrueNAS 25: qualification results

Date: 2026-10-03. Status: bounded runtime qualification and live-resource cleanup complete.
Scope: [approved disposable TrueNAS lab](2026-10-03-proxmox-csi-truenas-qualification.md).

## Outcome

Recommend **unmodified upstream Proxmox CSI over NFS** for the intended disposable-cluster architecture.
Two complete k3s cluster rebuilds recovered the same externally owned raw image, filesystem UUID and all observed
committed SQLite data using static declarations and external credentials. No old Kubernetes datastore, Velero backup,
custom adoption controller or driver modification was used. This complements the separate
[Debian NFS qualification](2026-10-03-proxmox-csi-lab-results.md).

The TrueNAS export-withdrawal test found a material operational limit: storage restoration alone did **not** restore the
writer. The guest received I/O errors, ext4 aborted its journal, and the writer exited. Scaling the synthetic workload
to zero, waiting for native CSI detach, then scaling it back to one recovered every acknowledged record. A production
runbook needs this storage-fault recovery path. This is distinct from the automatic healthy-worker move and successful
cluster-rebuild cases; it is not evidence of automatic recovery from arbitrary NAS failures.

No production application was migrated or reconfigured. Shared production integration and activation remain separate.

## Results

| Test | Observed result |
| --- | --- |
| Initial static binding | Stock CSI mounted the allocated 2GiB image; 1,000 deterministic SQLite records passed integrity/payload checks. |
| Terraform coexistence | No-op plan and a reviewed description-only update preserved the CSI disk and data. Boot/cloud-init ownership stayed with Terraform. |
| Healthy worker movement | Worker1 → worker2 → worker1 retained the same data/UUID with one configured attachment. |
| Interrupted expansion | Controller grew the image from 2GiB to 4GiB while the node plugin was absent. Restoring the stock plugin completed filesystem expansion by native retry. |
| Blank, wrong-type and missing images | Blank image formatted as ext4; declaring an existing ext4 image as XFS failed without changing its UUID; a missing image failed without allocation. |
| Failed-worker partition | The NotReady VM kept committing. Infinite NoExecute tolerations held its original pod; takeover followed confirmed VM power-off. The disk detached before the old VM restarted. |
| TrueNAS export withdrawal | Independent timer restored only the lab export. Writer exited on I/O error; manual workload restaging recovered all 2,359 records through acknowledged sequence100358. |
| First full rebuild | All three former VMs/datastore disappeared; fresh namespace/PVC UIDs, original filesystem UUID, identical 2,359 records and full hash. Terraform no-op. |
| Interrupted second destroy | With control-plane VM981 absent, the old writer advanced from 2,396 to 2,412 records. The test withheld replacement creation, confirmed VM982 stopped, then removed the remaining workers. |
| Second full rebuild | Fresh namespace/PVC UIDs; all 2,412 observed commits recovered with valid payloads, contiguous sequence and SQLite integrity. Same UUID, expanded capacity and image digests. Terraform no-op. |

The final filesystem UUID was `8a43dddb-dbad-491c-8020-d1f3e9467cc1`. The retained raw image was 4,294,967,296 bytes;
usable filesystem capacity was 4,152,066,048 bytes. Final data SHA-256:
`0f957956912847b5132f071abc419bec198aaee5d955246ef3bfe1c64b66cf4c`.
The original 1,000 records survived expansion. Another 1,000 records were added after growth; that resulting
2,000-record prefix remained unchanged through both rebuilds.

## Exact environment and evidence

TrueNAS **25.10.7**, pool `apps` GUID `9917900421692286909`; newly allocated dataset
`apps/csi-qualification-20261003`, GUID `11239987941870433523`, with an **8GiB quota**, no reservation, inherited unlocked
encryption and sync STANDARD. NFS share6 allowed only Proxmox `10.9.9.20/32`. The temporary Proxmox registration was
`csi-truenas-assessment`, served by `10.9.9.30`. CSI image ownership used reserved ID9980, outside cluster Terraform;
no VM9980 existed. Four disposable VMs980–983 used 2GiB RAM, 2vCPU and 8GiB boot disks each.

The driver was **v0.20.0/chart0.5.10**, Terraform **1.16.5**, Telmate **3.0.2-rc10**, k3s **v1.37.0+k3s1**, Helm **4.3.0**.
Release artifact checksums and running CSI/workload image digests matched the pinned Debian-lab versions. The data path
used NFS4.2 TCP, a hard host mount, cache-none virtual disk and guest ext4. No QEMU image lock appeared in the inspected
fdinfo or host lock records. Single attachment and RWOP are not proof of fencing an unreachable writer.

- [Runtime evidence and historical acceptance scripts](evidence/2026-10-03-proxmox-csi-truenas-results.json).
- [Resource identities, NAS journals and cleanup receipts](evidence/2026-10-03-proxmox-csi-truenas-ledger.json).
- [Original read-only preflight](evidence/2026-10-03-proxmox-csi-truenas-preflight.json).

The embedded scripts are historical synthetic-test evidence, not proposed production lifecycle scripts. Credentials,
Terraform state, private keys, kubeconfigs and private transfer payloads are excluded. Runtime testing and tool installation
ran on disposable VMs; VM300 supplied only its existing trusted NAS-management route, with pinned dependencies and
exclusive maintenance ownership. The workstation supplied editing and transport.

Installed TrueNAS share operations were inspected before changes: they call service reload; the installed systemd
ExecReload runs `exportfs -r`. NAS boot ID, NFS active-start timestamp and nfsd thread count remained unchanged across
export creation and withdrawal/restoration. No global NFS stop/restart, NAS reboot, pool export or production network
fault occurred. Relevant upstream references: [dataset API](https://api.truenas.com/v25.10.0/api_methods_pool.dataset.create.html),
[NFS share API](https://api.truenas.com/v25.10.0/api_methods_sharing.nfs.create.html), and
[share reload source](https://github.com/truenas/middleware/blob/TS-25.10.0/src/middlewared/middlewared/plugins/nfs.py).
Installed 25.10.7 code was checked separately; these links do not substitute for the runtime observations.

## Limits and production integration

The tested workload was synthetic Python/SQLite, not Jellyfin. There was no NAS reboot, hardware power-loss, full-pool,
volume above 64GiB, sustained-performance or multi-Proxmox-node qualification. Withdrawing an export is not the same
fault as a temporary packet drop. Data survived the tested interruption; that does not establish arbitrary-failure durability.

Failed-node takeover must retain native NoExecute holds until old-writer power-off is confirmed. The partial-destroy
harness explicitly withheld replacement creation; the current production pipeline has not yet been taught that order.
Neither RWOP, lost Kubernetes metadata nor a missing pod establishes that an old VM stopped writing.

Production PRs still need shared Proxmox/NFS registration and API scope, worker prerequisites, Terraform SCSI ownership
and replacement ordering, stock CSI installation, retained Apps bindings, and GitOps expansion sequencing. The lab
requested expansion on the PVC first, then reconciled successful PV/PVC capacity into Git. It does not prove that an
arbitrary simultaneous ArgoCD PV/PVC size edit follows the same sequence. Apps remains the sole per-volume inventory;
Ansible prepares shared infrastructure. No per-service Ansible inventory or Velero freshness gate is proposed.

## Execution deviations and cleanup

- A restricted dataset query omitted encryption fields after successful creation. Marker/full metadata and a separate GUID query reconciled the original object; creation was not blindly repeated.
- VM980 cloud-init completed with no fatal errors but exit2 warnings for a deprecated user field and deliberately absent password. Those warnings were inspected; SSH-key authentication remained in use.
- The first rebuild's evidence serializer shadowed its identity dictionary with an image-digest set. Data/UUID/digest checks passed before serialization failed. Renaming those sets and rerunning the full read-only verification passed; no infrastructure behavior changed.
- A local inspection accidentally displayed a private transfer script containing encoded temporary lab API tokens and the generated lab SSH key. Those lab-only credentials are excluded from committed evidence; cleanup revoked both API identities and removed all VMs accepting the key. That command did not print existing NAS, Proxmox administrator or VM300 credentials.

Cleanup verified VMs980–983, their boot/cloud-init disks, the three exact synthetic NAS images, temporary Proxmox
storage registration/mount, lab pool and both API users/tokens plus six temporary roles removed. Config hashes for
pre-existing VMs100/200/201/202/300/900 matched their baseline. TrueNAS share6 and its GUID-checked dataset were removed;
all pre-existing exports and global NFS configuration matched baseline, the pool remained healthy/ONLINE, and NFS service
start time, NAS boot ID and nfsd thread count were unchanged. The independent timer/helper were removed, this run's
original maintenance ownership was released, and its private nonce was deleted. Existing credential references and
historical maintenance receipts were retained. Proxmox private staging was removed after evidence export.

Generated local private staging was removed after checking the deliverables against actual secret values and their encodings. Both temporary API identities are revoked, and every VM accepting the temporary SSH key is deleted. The original user-provided Proxmox credential file was preserved.

Validation passed: JSON/evidence invariants, cleanup receipts, embedded Python parsing and Bash syntax, local documentation links/fences, README image references and `git diff --check`. Local PyYAML and pre-commit are unavailable; local YAML re-parsing/hooks were not run. The embedded manifests were successfully applied in each actual disposable cluster. No production rollout is claimed.


## Final review

A fresh read-only reviewer found no Critical or Important architectural issues. Two reported minor factual issues were
corrected before delivery: the obsolete next-step instruction could cause unnecessary repeat live qualification, and the
record-count sentence overstated which batch existed during expansion. The saved post-resize observation has 1,000
records; the later expanded baseline has 2,000. The final recovery hashes were independently recomputed and matched.
These are delivery-blocking factual corrections in this assessment, not new runtime changes. Source/evidence checks
were rerun after the corrections; no additional destructive tests were performed.

Review boundaries retained deliberately: current live state is supported by this run's cleanup receipts, not an independent
second live inspection; actual-secret exclusion was performed by the executor, while the reviewer inspected sanitized
artifacts only. Production integration/automatic fencing/GitOps resize sequencing, arbitrary NAS failures or power loss,
large-volume performance and Jellyfin workload qualification remain unproven. Historical test scripts are evidence,
not supported deployment tools. Treating any of those exclusions as a production guarantee would risk unsafe activation
or data loss; the next integration stage must preserve these limits. No review findings remain deferred.
