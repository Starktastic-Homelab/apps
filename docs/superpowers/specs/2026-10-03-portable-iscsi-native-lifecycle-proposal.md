# Portable iSCSI architecture and qualification proposal

Date: 2026-10-03. Status: static Git-managed bindings accepted; stock Proxmox CSI selected for disposable qualification, iSCSI retained as fallback.
Source assessment and synthetic probes only.

The user selected explicit Git-managed bindings with separate one-time volume allocation. The preserved iSCSI fallback
uses the existing `org.democratic-csi.retained` node-manual attachment model; no dynamic CSI provisioning controller or
private ID template is needed for that path. Proxmox CSI qualification is the current next step. The [recovery assessment](../reports/2026-10-03-democratic-csi-clean-cluster-recovery.md) records
why stock dynamic provisioning was not selected. The [Jellyfin audit](../reports/2026-10-03-jellyfin-static-storage-design.md)
traces the current implementation and proposed simplification.

The user confirmed keeping this design on October 3. Apps owns the per-volume declarations; Ansible prepares shared
infrastructure and consumes those declarations if needed for verification. There must be no second service inventory
or service-specific lifecycle code in Ansible. The alternatives recap below preserves this selection while recording
where the assessment is incomplete.

The user requires an unmodified upstream CSI driver. Supported configuration is allowed; driver forks, patched images
and locally maintained driver enhancements are outside the selected design. After completing the source comparison,
the user accepted stock filesystem handling and chose to qualify Proxmox CSI in a disposable lab. This supersedes the
previous exclusion based on format/repair behavior. The iSCSI design remains preserved as fallback; current deployment
and safeguards are unchanged until qualification and separate activation approval.

Current direction: disposable k3s VMs **and datastore**, with application data, Git-managed volume bindings and bootstrap
secrets outside the cluster. Rebuild without a final metadata backup or restoring the old Kubernetes database.
**Velero is removed from this plan.** External etcd or a retained control-plane disk is not the selected replacement.

Preserve application claim names when changing TrueNAS to Debian; backend allocation, endpoint changes and data transfer
are separate operations. CHAP removal remains a pending design choice and existing authentication is unchanged.
Current Jellyfin, VM300, ownership records and safeguards remain in place until equivalent behavior is qualified.
This document does not approve lab allocation, deployment, production changes, upstream messages or deletion.

## Requirements and evidence boundary

Adding a durable volume now permits one-time NAS allocation and an explicit Git binding record. Applications consume
ordinary existing claims. Reuse shared declaration/verification code; do not add service-specific Python, shell or
Ansible lifecycle programs. Routine cluster rebuilds require no hand-constructed identity or release receipts. All three k3s VMs must be replaceable while
external application data survives; all Kubernetes datastore state may also be discarded. Replacing the storage provider
must preserve application declarations, with a separately qualified data transfer. CHAP remains the baseline while a
no-CHAP alternative is assessed. Unreachable writers must be excluded before takeover; unattended failover
is not a requirement.

The four handoff documents were read from `/home/benf/Projects/homelab/apps/docs/superpowers/`, including the untracked
October 3 updates. They were preserved. This proposal adds findings rather than repeating their lifecycle inventory.
Some tracked copies in other worktrees predate those updates.

Remote main refs were queried directly on October 3:

| Repository | Verified main | Source observations |
| --- | --- | --- |
| Apps | `284563c65868fe838fef6a8fb239eb7225b04709` | This worktree starts at that merge. Existing node-manual CSI has no controller or StorageClass; Jellyfin has static bindings. |
| Ansible | `59a281327e4a04005178b2fbf2954fba37e51b1d` | Inspected worker/bootstrap source at `0fc25a3c90defc5b114be68e333c1592003cdc76`; GitHub comparison shows no changes in those paths, but runner files differ. Do not deploy that older checkout. |
| Packer | `840b56545fd99ec1ac36dc35feec18c3ffd7a2d7` | Image script explicitly installs NFS tooling but not the proposed iSCSI prerequisites. This does not assert packages are absent from every live guest. |
| Terraform | `50582000a7f6b873d2bb436f4850a3e62f56e2ce` | Primary checkout is older. Main has infrastructure/maintenance serialization added since the handoff anchor. Preserve it until replacement qualification. |

The subsequent Proxmox comparison used explicitly authorized read-only access to 10.9.9.20, including installed
source, filtered VM configuration and resource capacity. No host was modified. NAS and Kubernetes APIs were not
accessed. Historical VM300 health and TrueNAS 25.10.7 remain handoff evidence, not fresh runtime verification.

## New findings that affect selection

### Recovery decision: no backup dependency

The user rejected any interval in which a new volume binding could be missing from a completed metadata backup.
Velero schedules and event-triggered backups are asynchronous, so Velero is removed from the current plan, including
installation, scheduling, monitoring and bootstrap restore work. Earlier retained-PV restore findings remain historical
evidence in Git, not part of the selected architecture. Separate application-data backup remains necessary for data loss.
[Velero backup semantics](https://velero.io/docs/v1.18/how-velero-works/).

A clean rebuild must reconnect to existing data using Git, externally recoverable bootstrap secrets and durable storage
identity, without relying on prior Kubernetes object UIDs or a preserved datastore. Storage data and its identity remain
outside the cluster destroy scope. Standard `Retain` alone does not reconstruct the binding.
[Kubernetes retention](https://kubernetes.io/docs/concepts/storage/persistent-volumes/#retain).

### TrueNAS 25 is the current target

The user confirmed TrueNAS 25 as the current platform and deferred TrueNAS 26 compatibility. Qualify against the actual
25.x release used by the homelab; the handoff reports 25.10.7, which still needs verification before lab execution.
The REST-to-WebSocket transition is a future upgrade consideration, not a blocker for selecting or qualifying a driver
for the current platform. No TrueNAS upgrade is included in this plan.

The latest democratic-csi tag remains v1.9.5 (`b5be00c0748cbae251e661392cc7ab9fea335ac9`). GitHub's latest-release endpoint
returns 404 for this project; the version statement comes from tags. Its REST transition issue remains open. The
maintainer announced WebSocket work, including an intended TrueNAS 26 minimum. The inspected `next` HTTP client at
`a7e9101db04e924f5328573572f0294c89b4d37f` still constructs `/api/v2.0`. An announced plan is not a supported release.
[Issue 509](https://github.com/democratic-csi/democratic-csi/issues/509),
[inspected development client](https://github.com/democratic-csi/democratic-csi/blob/a7e9101db04e924f5328573572f0294c89b4d37f/src/driver/freenas/http/index.js#L60).

TrueNAS 25.10 retains REST; TrueNAS 26 removes it. Reassess driver compatibility as part of any future upgrade to 26.
The SSH TrueNAS driver still uses the API for export management; generic Linux targetcli must not be used to bypass
TrueNAS middleware.
[Vendor API notice](https://www.truenas.com/docs/scale/26/api/).

### Secret references do not eliminate argument exposure

The chart supports an existing configuration Secret and CSI node-stage Secret references. Use these instead of plaintext
Helm values, StorageClass parameters or PV attributes. On TrueNAS, shared platform setup owns the CHAP group; the driver
references its ID. On Debian, the controller configuration owns target-group CHAP. Neither requires app-specific code.
[Chart configuration](https://github.com/democratic-csi/charts/blob/democratic-csi-0.15.1/stable/democratic-csi/values.yaml).

However, v1.9.5 passes node CHAP passwords to `iscsiadm --value` arguments. Its Debian targetcli helper embeds CHAP in a
remote `sh -c` command. Both have command-log redaction, which does not remove the original arguments. The inspected
development targetcli helper still has this construction. Secret references therefore satisfy declarative storage of
credentials, but not the handoff's prohibition on credentials in command arguments. No real credential was used to test
this. Do not run the authenticated candidate until an upstream-supported credential path satisfies the requirement.
[Node helper](https://github.com/democratic-csi/democratic-csi/blob/b5be00c0748cbae251e661392cc7ab9fea335ac9/src/utils/iscsi.js#L96-L129),
[target helper](https://github.com/democratic-csi/democratic-csi/blob/b5be00c0748cbae251e661392cc7ab9fea335ac9/src/driver/controller-zfs-generic/index.js#L1027-L1090).

### Enumeration cannot be treated as proof of absence

In the inspected TrueNAS API `ListVolumes`, HTTP 403 falls through to an empty result. A synthetic probe reproduces this.
This establishes an enumeration failure, not that `CreateVolume` automatically destroys or replaces retained data. Do not
build recovery around an empty list, name-template guesses, or `_private.csi.volume.idTemplate`.
[Enumeration source](https://github.com/democratic-csi/democratic-csi/blob/b5be00c0748cbae251e661392cc7ab9fea335ac9/src/driver/freenas/api.js#L3827-L3975).

The focused recovery probes confirm that normal creation uses a direct dataset lookup and stops before mutation on the
representative permission/server/timeout failures tested. Keep the enumeration issue distinct from that creation path.

The [source probes](../reports/evidence/2026-10-03-democratic-csi-source-probes.cjs) verify file hashes, replace execution
and HTTP calls with mocks, and reproduce all three findings without network or subprocess execution:

```sh
node docs/superpowers/reports/evidence/2026-10-03-democratic-csi-source-probes.cjs /path/to/democratic-csi-v1.9.5
```

Result on October 3: all three assertions passed. These are demonstrations of upstream limitations, not passing storage
qualification. Command logs were redacted in the synthetic cases; full error/output leakage remains a runtime test.

Local validation also passed Node syntax checking and proposal link/whitespace checks. `pre-commit` could not run because
it is not installed. No YAML/Helm resources changed, so cluster-schema/render checks were not applicable. No runtime
storage, image build, Ansible deployment or infrastructure test was performed.

## Alternatives against the original SQLite and NFS goal

The original requirement is reliable SQLite storage with an operating model close to NFS, not iSCSI itself. SQLite
documents network-filesystem locking/sync risks and says WAL does not work over network filesystems. This does not mean
every SQLite database on NFS immediately fails; rollback-journal configurations can mitigate some problems, but are not
a generic guarantee for unmodified applications. Jellyfin currently recommends a local database and still documents
SQLite as its implemented database backend. NFS remains appropriate for its media files.
[SQLite network guidance](https://www.sqlite.org/useovernet.html),
[WAL limitations](https://www.sqlite.org/wal.html),
[Jellyfin storage guidance](https://jellyfin.org/docs/general/administration/storage/).

With ext4 on a single-writer remote block device, SQLite file locking and WAL coordination occur within the guest's
filesystem. The storage path must still honor flushes and exclude competing filesystem writers. Changing the transport
does not eliminate those requirements, and storage changes do not prove that application-level SQLite contention is fixed.

The following is an architectural comparison, not runtime qualification of every candidate. Prior detailed source
inspection concentrated on iSCSI drivers; it would overstate the evidence to claim that all alternatives were exhausted.

| Alternative | Assessment against this homelab's requirements |
| --- | --- |
| Direct NFS/SMB for SQLite, or mount/journal tuning | Does not establish a generic supported filesystem contract for these applications. Switching file-sharing protocols alone is not a demonstrated fix. Keep NFS for media and other suitable files. |
| Application-supported PostgreSQL or another database server | Good per-application option where officially supported, already a separate workstream. It does not cover Jellyfin today and the database server still needs durable storage. |
| Node-local SQLite plus backups or Litestream | Simple runtime storage, but asynchronous copies introduce a latest-write loss window when the source disks disappear. Litestream explicitly documents this limitation. It does not meet recovery from surviving original storage without backup freshness checks. |
| Retained virtual disks, including Proxmox CSI over NFS | Credible alternative that has not been ruled out. Gives the guest a block device and can keep the NAS protocol as NFS. Requires proof of disk survival during VM deletion, reconstruction of bindings and safe attachment to replacement VMs. Details below. |
| Longhorn or another replicated storage system inside the disposable cluster | Replication among disks that are all destroyed does not preserve data. Retaining those disks requires a qualified recovery path; Longhorn's documented backup-based DR is asynchronous. An external storage deployment changes this tradeoff but adds infrastructure. |
| External Ceph RBD | A viable architectural family providing block storage to Kubernetes, not rejected as SQLite-incompatible. Operating a separate Ceph storage system and preserving its bindings is a larger platform change than consuming the existing NAS. It has not been lab-compared here. |
| NVMe/TCP instead of iSCSI | TrueNAS 25.10 supports it. It changes block transport, while retaining allocation, stable bindings, growth and exclusive-writer requirements. No evidence yet that it reduces the total lifecycle work. |
| A loop-mounted filesystem image on NFS inside a worker | Changes the filesystem seen by SQLite, but requires qualified image locking, exclusive ownership, mount cleanup, flush behavior and growth. No supported drop-in lifecycle was established here; custom loop-device orchestration is not the selected simplification. |
| Run the application beside its data on a persistent NAS/VM | Can simplify storage attachment, but changes the workload-placement model and does not provide the requested movement among disposable Kubernetes workers. |
| Static iSCSI bindings | Accepted baseline: existing driver, external data, explicit Git identity and provider portability. Initial allocation and growth remain separate operations; complete unattended rebuild and simplified movement still require qualification. |

Sources for the additional candidates:
[Litestream data-loss window](https://litestream.io/tips/#data-loss-window),
[Longhorn backup-based DR](https://longhorn.io/docs/1.13.0/snapshots-and-backups/setup-disaster-recovery-volumes/),
[Ceph block devices with Kubernetes](https://docs.ceph.com/en/latest/rbd/rbd-kubernetes/),
[TrueNAS 25.10 NVMe-oF](https://www.truenas.com/docs/scale/25.10/scaletutorials/shares/nvme-of/).

### Proxmox CSI over NFS assessment and disposition

The [completed source comparison](../reports/2026-10-03-proxmox-csi-nfs-assessment.md) establishes a native disk-ownership
path that can preserve CSI images during worker deletion. The installed ownership/deletion functions match the pinned
source, and the isolated deletion-function probe passes. Upstream supports static disk bindings, normal attachment
movement and filesystem expansion. The Terraform VM module needs a qualified rule excluding CSI SCSI attachments from
its disk reconciliation. Real full-destroy/recreate behavior, failure recovery and expansion are not yet tested.

The user chose: "Accept stock filesystem handling; qualify Proxmox CSI in a disposable lab." This explicitly permits
the assessed upstream behavior for that candidate: reuse recognized filesystems, potential mkfs when a referenced image
has no recognizable filesystem, and automatic filesystem checking/repair. Missing disk images still fail attachment.
This is a prospective candidate-policy change, not permission to remove current Jellyfin safeguards or repair live data.
No custom driver, mkfs wrapper or service-specific mount program will be introduced.

Proxmox CSI is now the preferred candidate for qualification; static iSCSI remains the fallback. The data path is
SQLite -> guest ext4 -> virtual disk -> Proxmox -> NFS -> NAS. It preserves NAS-provider portability through NFS, adds a
Proxmox API dependency, and supplies native PVC expansion missing from the current node-manual profile. Both candidates
still use durable bindings in Apps, separate allocation, recoverable secrets and old-writer exclusion. Neither requires
Velero or changes to the user's routine Packer PR -> Terraform PR merge procedure after shared integration is qualified.

The [bounded lab proposal](../reports/2026-10-03-proxmox-csi-disposable-lab.md) fixes the proposed resources and test scope.
It is assessment preparation, not an executed lab. TrueNAS 25 qualification and activation remain separate from the
synthetic Debian NFS lab. No new upstream contribution or monitoring task is authorized.

## Dynamic-controller alternatives assessed before selecting static bindings

Removing CHAP eliminates its credential distribution and the CHAP settings in node login and target configuration. It does
not remove NAS API credentials, SSH credentials, storage identity, filesystem safeguards or old-writer exclusion.
The following explains earlier options; the selected static node-manual path does not require any of these provisioning
controllers. They are not current production selections:

| Choice | What dropping CHAP unblocks | Remaining gaps |
| --- | --- | --- |
| tns-csi on TrueNAS, another controller on Debian | tns-csi v0.18.1 lacks CHAP but documents native adoption and uses WebSocket management; it becomes a relevant clean-rebuild candidate. | TrueNAS-only, early development, adoption safety and equivalent Debian recovery remain unqualified. |
| Official TrueNAS CSI | CHAP-specific retry and secret-handling problems cease to block a deliberately unauthenticated profile. | TrueNAS-only; safe automatic recovery without the old Kubernetes metadata is not established. |
| democratic-csi family | No CHAP password needs to enter the inspected iscsiadm/targetcli argument paths. | Clean-cluster recovery remains unresolved; management credentials still need protection. Qualify on current TrueNAS 25; defer API migration until a future upgrade. |
| Debian ZFS/LIO with democratic-csi | Avoids the TrueNAS API dependency and the CHAP-specific argument issue. | Changes the backend architecture; native rediscovery and recovery still need proof. This is not a portable TrueNAS implementation by itself. |

The inspected driver releases are tns-csi v0.18.1, official TrueNAS CSI v1.3.0 and democratic-csi v1.9.5. Their source
findings do not imply runtime qualification. Different controllers may preserve ordinary application PVC declarations,
but that is a design objective until both providers pass the same recovery tests.

### tns-csi adoption: promising, with a concrete unresolved failure path

The pinned tns-csi documentation describes `markAdoptable` and `adoptExisting`, storage-side ZFS properties and recreation
of missing exports. Its README explicitly labels the project early development and not production-ready.
[Adoption](https://github.com/fenio/tns-csi/blob/v0.18.1/docs/ADOPTION.md#automatic-adoption-gitops),
[CHAP comparison](https://github.com/fenio/tns-csi/blob/v0.18.1/docs/COMPARISON-TRUENAS-CSI.md),
[README](https://github.com/fenio/tns-csi/blob/v0.18.1/README.md).

Source inspection adds an important limit: `checkAndAdoptVolume` searches by the requested CSI name; on a search error it
returns `(nil, false, nil)` and permits normal creation to continue. This does **not** prove an empty volume will be
created: later checks may stop creation. It does mean the adoption helper itself does not enforce the required policy
of stopping on an uncertain lookup. Stable identity across fresh PVC UIDs, namespace collisions, missing metadata and
full creation-path behavior need investigation before selection. A naming template alone is not evidence of safe adoption.
[Adoption implementation](https://github.com/fenio/tns-csi/blob/v0.18.1/pkg/driver/controller.go#L1605-L1638).

### Access policy for a possible no-CHAP profile

The tradeoff is loss of iSCSI initiator authentication. A dedicated storage network, enforced source restrictions and
appropriate target ACLs would become the access boundary. An IQN is an identifier and can be spoofed; an allowlist is
not cryptographic authentication. A permitted compromised node could access whatever the target exposes to it. CHAP
itself does not encrypt storage traffic. Evaluate actual network reachability and cross-volume access before selecting
this profile. Do not treat a VLAN label alone as isolation, and do not replace CHAP with custom credential machinery.
Existing authenticated storage is unchanged while this option is considered.

## Proposed application and platform contract

The platform owns one stable binding declaration for each pre-provisioned volume. It records namespace, PV/PVC names,
size, access mode, filesystem type, stable CSI handle and iSCSI portal/IQN/LUN, with an optional Secret reference. Store
non-secret verified filesystem/device identity durably alongside it; private credentials remain externally recoverable.
The current allocation-intent JSON is not sufficient: actual returned identities must be verified before enrollment.

Reuse the existing renderer where practical, removing hardcoded Jellyfin policy/Secret names rather than copying it for
each application. Generate static PV/PVC manifests with `Retain`, explicit empty `storageClassName`, a named claimRef
without a Kubernetes UID, and explicit PVC `volumeName`. Keep ArgoCD prune/delete protection for the bindings. App values
consume `existingClaim`. Existing NFS defaults stay intact. No dynamic allocation is enabled for these retained claims.

Keep the node-only democratic-csi deployment. Its routine attachment path needs no NAS provisioning credentials.
One-time allocation and exceptional NAS recovery remain separate from cluster bootstrap; this iSCSI fallback rebuild path never creates,
formats, repairs or redirects a volume. The accepted Proxmox candidate uses the stock filesystem policy described above. Existing format suppression remains until an equivalent supported protection is
qualified. PV volumeHandle and IQN are identifiers, not proof of filesystem/device identity.

Remove worker UID, namespace UID and SMBIOS generation from long-lived app values after shared bootstrap checks can
safely authorize the new generation. Use stable capability labels for placement, retaining the GPU requirement for
Jellyfin. Keep RWOP and Recreate for same-cluster scheduling; neither excludes an old cluster's writer. Shared rebuild
checks must still prove old-writer shutdown, correct target/filesystem and successful node preparation before services
start. Reuse narrowly scoped existing checks initially; do not build a permanent recovery controller or delete safeguards
before their replacement passes qualification. Exact bootstrap wiring is an implementation-plan item.

A backend migration changes the volume inventory and NAS allocation; the application claim contract remains the same.
Native TrueNAS object IDs remain in backend evidence, not in application values. Debian uses persisted ZFS/LIO exports.
Authentication and target ACL management are shared platform choices; no service-specific credential program is needed.

Packer installs `open-iscsi`, `e2fsprogs` and persistent `iscsi_tcp` loading in the guest. Prefer the distro's standard
`iscsi-init.service` / `iscsi-gen-initiatorname` chain, which creates an initiator name only when absent and precedes
iscsid. Verify those units in the exact Debian package before choosing image wiring; upstream availability is not proof
of Debian packaging. Image cleanup removes only build-instance identity/session state. If package wiring is absent,
evaluate the smallest per-instance cloud-init use of `iscsi-iname`; never rewrite an active identity.
[Upstream unit](https://github.com/open-iscsi/open-iscsi/blob/master/etc/systemd/iscsi-init.service.template).

CSI readiness replaces storage-ready enrollment only after clone/reboot/replacement tests pass. No per-worker review
JSON belongs in the new normal path. Existing enrollment continues to protect the pilot until its separate retirement.

## Recovery sequence and prevention of empty replacement volumes

### Clean-cluster recovery contract

Keep the existing Packer PR merge, generated Terraform PR review and Terraform PR merge procedure. No backup command,
pre-merge backup verification, new checkbox or separate recovery approval is required for a qualified routine rebuild.
Terraform owns VM lifecycle. Apps and Ansible install the platform and bootstrap a fresh cluster from declared inputs.
Neither Terraform nor bootstrap depends on Velero, an etcd snapshot or the old cluster API.

The required recovery sequence is a qualification contract; the complete sequence has not yet passed a lab rebuild:

1. Exclude old writers using verified Proxmox power state and VM generation. An uncertain stop keeps writers blocked.
2. Recreate the three Debian/k3s VMs with an empty datastore. Prepare initiators and apply the selected target access
   policy without reusing a live node identity. Recover bootstrap secrets independently and keep application writers held.
3. Install the existing node-only CSI driver. Reapply static PV/PVC declarations from Git. The namespace and claim names
   remain stable but their Kubernetes UIDs may change; those old UIDs are not restored.
4. Automatically verify the expected device/filesystem and binding before releasing services. Missing targets, missing
   records, conflicting identity and failed lookups stop recovery. No provisioning controller is available to create a
   replacement, and bootstrap has no allocation/formatting fallback.
5. Run applications with ordinary claim references and stable placement requirements. Full-rebuild authorization is a
   shared platform step, not a per-application manual release. Exceptional partial replacement and failed-node recovery
   remain held until the same old-writer exclusion can be established.

Acceptance: create and write a volume immediately before destroying all three cluster VMs, OS disks and datastore,
without a final backup. Reapply the declared static bindings from Git, bootstrap secrets and surviving NAS state. Recover the original data with no
new backend volume allocation. Repeat with interruptions during provisioning, failed lookups and deliberate missing
metadata. Separate data backups cover loss or corruption of NAS data; they do not replace this acceptance test.

## Writer exclusion and maintenance

Use RWOP for ordinary scheduling and a documented Proxmox stop-and-confirm procedure for unreachable nodes. Verify VMID,
SMBIOS/generation and stopped status against the expected old VM; an API timeout is an unknown outcome. Do not remove a
Kubernetes attachment or apply an out-of-service taint until shutdown is confirmed. No unattended failover or new custom
fencing daemon is proposed. Wrong-generation and interrupted-stop tests are mandatory.
[Kubernetes shutdown guidance](https://kubernetes.io/docs/concepts/cluster-administration/node-shutdown/).

For a planned pipeline rebuild, perform the stop-state/generation checks automatically as part of the authorized VM
replacement and recovery sequence. The documented operator procedure is for exceptional failure recovery, not an extra
step before every Terraform merge. An ambiguous outcome still stops the pipeline rather than releasing a writer.

Use separately prepared NAS snapshot clones mounted by Jobs for routine restore inspection; the node-only CSI path does
not provide a snapshot controller. A readOnly pod mount is not evidence that the
original avoided journal replay, repair or formatting. For a non-mutating original-volume investigation, retain the
existing exceptional path until equivalent semantics are demonstrated. Quiesced backups and application/database restore
checks remain separate from NAS snapshot creation. Start with stopped synthetic writers and a small SQLite fixture;
do not claim generic live database consistency.

Cross-provider transfer restores a verified data backup into a newly provisioned destination volume with the source
writer excluded. Expect new CSI handles/backend identities; verify hashes, permissions, ACLs/xattrs where used, and
database contents. Reuse the application declarations on a fresh destination cluster. Same-cluster provider switching
is a separate activation plan because StorageClass/PV fields and existing claims cannot simply be repointed. Original
retained rebinding and backup restoration are distinct acceptance tests.

## Bounded disposable qualification design

Proposed maximum footprint: six remote VMs, 11 vCPUs, 26 GiB configured RAM and 500 GiB aggregate virtual disk capacity.
This is a ceiling for planning, not verified available capacity: three k3s nodes at 2 vCPU/4 GiB each, TrueNAS at
2 vCPU/8 GiB, Debian ZFS/LIO at 2 vCPU/4 GiB, and a separate operator/backup VM at 1 vCPU/2 GiB. Both storage VMs survive
cluster destruction. Test data stays small. No production RAM reduction, runner shutdown, NAS upgrade or production pool
usage is implied. If capacity is insufficient, revise the lab proposal before allocation.

Before requesting execution approval, provide exact unused VMIDs, IPs, pool/disk paths, isolated network, pinned images,
Terraform plan, protected credential locations and operation limits from read-only preflight. Verify guest SMBIOS and
virtualization identity before every deployment. Ansible runs only from the approved disposable operator VM; review all
localhost delegation first. This workstation is limited to static/synthetic checks and read-only transport. VM300 is
not the proposed operator VM.

| Qualification | Required evidence |
| --- | --- |
| Shared setup and onboarding | Two services and a third use one-time allocation plus the same binding schema; same PVC name in different namespaces; no service-specific lifecycle code; compare actual steps with NFS. |
| Authentication and access | Baseline CHAP: wrong/missing secret refused and no credential exposure. If no-CHAP is selected: enforced network/target restrictions and cross-volume access tested. Management credentials remain protected in either profile. |
| Creation interruption | Interrupt after ZVOL, target, extent and mapping operations; inspect before retry; one correct volume, no export outside the selected access policy or empty replacement. |
| Identity and replacement | Distinct clone IQNs, stable reboot IQNs, node replacement without handcrafted enrollment, backend target configuration survives reboot. |
| Competing writers | Same-cluster RWOP refusal; isolated old writer excluded before replacement writes; wrong-generation stop refused; ambiguous stop remains closed. |
| Healthy node movement | Clean drain/unstage on one prepared worker, reschedule/stage on another eligible worker, original data intact; no per-move Git edit or manual release receipt. Qualify separately from unreachable-node fencing. |
| Capacity growth | Explicit growth of one disposable volume while preserving device/filesystem identity; verify NAS size, node size, filesystem size and declared/bound capacity agree. Include interrupted growth; ordinary bootstrap cannot resize or recreate on mismatch. Do not assume node-manual supports PVC-triggered expansion. |
| Full cluster loss | Write unique sentinels, remove all three lab cluster VMs/OS disks, discard the datastore, recreate from Git/secrets and recover the original backend filesystems/data without new volume allocation or metadata backup. |
| Unchanged merge procedure | Exercise Packer-to-Terraform-to-Ansible without backup hooks or checks. Static binding recovery must cover a volume enrolled immediately before cluster loss and interrupted one-time allocation; no empty replacement is allowed. |
| Recovery failures | Missing/stale metadata, duplicate backend identities, namespace collisions, HTTP 403/500/timeouts and missing storage leave affected writers held and allocate nothing. |
| Backup and maintenance | Interrupted capture stays incomplete; restore checks use clones/new volumes; verify source remains unchanged; compare file and SQLite contents independently. |
| Backend portability | Repeat the same declarations/recovery suite on TrueNAS and Debian; separately transfer verified data TrueNAS to Debian and reverse, with old-writer exclusion. |

Run access-policy and management-credential checks before provisioning. Authenticated profiles additionally require a
fixed supported CHAP credential path; a no-CHAP profile requires its access policy to be selected and qualified.
Use the actual TrueNAS 25.x release for current qualification; TrueNAS 26/WebSocket support is not an execution gate.
Preserve all historical production data/evidence and lab evidence; any lab cleanup must
name only the disposable resources explicitly authorized for removal.

## Removal and delivery boundaries

| Current responsibility and actual paths | Candidate replacement and removal gate |
| --- | --- |
| Apps `scripts/storage/onboard.py`, `node_credentials.py`, `render_storage.py`; `storage/services/jellyfin.json` | One-time allocation and reusable static-binding declarations, after onboarding/interruption/rebuild tests. Preserve existing Jellyfin identity and admission until replaced. |
| Apps `scripts/storage/initiator_probe.py`, `maintenance_cli.py:observe_release` | CSI staging/cleanup and verified stop procedure; exceptional original-device forensic semantics must pass separately. |
| Ansible `roles/iscsi_initiator`, `scripts/iscsi_generation.py`, `group_vars/workers/iscsi.yml` | Image prerequisites and standard unique identity, after clone/replacement and old-writer tests. |
| Ansible `scripts/proxmox_fence.py`, `roles/storage_fencing`, `storage-fencing.yml` | Native Proxmox stop-and-confirm, after wrong-generation/timeout/competing-writer tests. |
| Ansible `roles/maintenance_runner`, `maintenance-runner.yml`, `scripts/maintenance_{lock,requests,executor,install}.py`; Apps `scripts/storage/{supervised_readonly,storage_inspection,reconciliation}.py` | Jobs, external backups and documented recovery. Inventory workflow callers, including Terraform's current maintenance serialization, before removing any runtime or lock. |
| Apps backup/identity/cutover/release modules and `jellyfin_backup.py` / `jellyfin_stages.py` | Preserve until each safety property and application acceptance path has replacement evidence. No blanket deletion. |

After architecture approval, prepare source PRs in order: inert Apps lab fixtures and recovery configuration outside
ApplicationSet discovery; Packer guest prerequisites/identity wiring; then Apps platform configuration and
Ansible bootstrap verification and static-binding recovery after the shared verification design is reviewed. No Velero work is included. Existing
VM replacement safety remains in scope for qualification. Build, allocation and activation have
separate reviewed plans. Review merge-triggered workflows before calling any PR inert: Packer can trigger downstream
manifest updates, and Ansible main can deploy. Put active changes behind a later activation PR.

The current proposal/evidence files live only under `docs/` and do not change discovered apps or deployment workflows.
Merging documentation has no intended workload change. A future storage activation or provider migration requires
workload downtime; its duration cannot be estimated from source evidence. Existing Jellyfin migration is not restarted.

## Current decision and next assessment

Static Git-managed bindings with one-time volume allocation are accepted. Velero and dynamic original-volume adoption
remain outside the plan. TrueNAS 25 is the target; compatibility with 26 is deferred. CHAP removal is still unresolved
for the iSCSI fallback. Use unmodified upstream drivers only.

The user accepted stock filesystem handling and chose disposable qualification of Proxmox CSI. Prepare and approve the
bounded resource/test scope, then test native attachment, Terraform ownership, growth and complete cluster recovery.
Keep this iSCSI proposal and its evidence as fallback. No current Jellyfin placement, authentication or writer-admission
change is authorized by the candidate selection.
