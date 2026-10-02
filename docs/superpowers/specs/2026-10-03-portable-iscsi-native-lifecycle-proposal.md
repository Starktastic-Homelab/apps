# Portable iSCSI architecture and qualification proposal

Date: 2026-10-03. Status: proposed architecture, awaiting review. Source assessment and synthetic probes only.

Current direction: disposable k3s VMs **and datastore**, with application data and sufficient durable volume identity
outside the cluster. Rebuild from Git and bootstrap secrets without a final backup or restoring the old Kubernetes
database. **Velero is removed from this plan.** External etcd or a retained control-plane disk is not the selected
replacement. Native volume rediscovery/adoption remains an unqualified requirement, not an implemented capability.

Keep one application StorageClass contract across TrueNAS and Debian. No inspected driver currently satisfies every
requirement. The user is considering dropping CHAP; the comparison below assesses that option, but does not authorize
changing existing authentication. Current Jellyfin, VM300, ownership records and safeguards remain in place.
This document does not approve lab allocation, deployment, production changes, upstream messages or deletion.

## Requirements and evidence boundary

After shared setup, adding storage means normal service values/PVC configuration. No service-specific Python, shell,
Ansible, manual login/mount commands, or identity/receipt construction. All three k3s VMs must be replaceable while
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

No production host, storage server, or credential was accessed. Historical VM300 health and TrueNAS 25.10.7 remain
handoff evidence, not freshly verified runtime facts.

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

## Architecture choices if CHAP is removed

Removing CHAP eliminates its credential distribution and the CHAP settings in node login and target configuration. It does
not remove NAS API credentials, SSH credentials, storage identity, filesystem safeguards or old-writer exclusion.
The following are candidates for assessment, not production selections:

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

An application author selects `iscsi-state`, size and `ReadWriteOncePod` in ordinary persistence values. Existing NFS
defaults stay intact. A second service and then a third use the identical schema. There are no target names, NAS paths,
CHAP fields or recovery receipts in application values. Same-named PVCs in different namespaces must remain distinct.

Shared infrastructure owns a separate CSI release/driver identity, the non-default `iscsi-state` StorageClass with
`Retain`, ext4 and validated RWOP-capable sidecars, and backend configuration Secrets. It must not reuse or edit
`org.democratic-csi.retained`. Snapshot support is configured once. Fresh empty volumes may be formatted; existing
Jellyfin's format suppression remains unchanged. Recovery of an existing volume must reject missing/wrong filesystem
identity before opening a writer.

Use driver-supported handles and a durable identity scheme that survives new PVC UIDs. Storage-side metadata is an
adoption mechanism only when the selected driver implements and qualifies that contract. The Debian
profile uses ZFS/LIO with target configuration persisted across reboot. Its example enables generated initiator ACLs.
The baseline CHAP profile includes a storage-network allowlist; this is not an asserted equivalent of per-IQN authorization.
Wrong or absent CHAP must fail in that profile. A possible no-CHAP profile uses the access policy above. Kubernetes app
accounts cannot create PVs, driver Secrets, privileged pods or host-network storage clients.

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

The required recovery sequence is a qualification contract; no selected driver has demonstrated it yet:

1. Exclude old writers using verified Proxmox power state and VM generation. An uncertain stop keeps writers blocked.
2. Recreate the three Debian/k3s VMs with an empty datastore and distinct initiator identities. Recover bootstrap secrets
   independently, including sealing keys and backend management credentials. Keep application writers held.
3. Install the qualified CSI controller and recover bindings through its native storage identity/adoption mechanism.
   Controllers may need to run to perform adoption; an entirely disabled provisioner is not a universal recovery design.
   Require the original backend data and correct application mapping; old Kubernetes UIDs need not survive.
4. The driver must distinguish an intentional first allocation from recovery of an existing volume using durable inputs.
   Missing expected storage, uncertain lookups or ambiguous identity must stop recovery without creating an empty
   replacement. This distinction must survive loss of Kubernetes state; do not infer first installation from its absence.
5. Verify existing filesystem/data identity before opening writers, using the supported recovery path. Release a service
   only after its binding is proven. An unsupported helper controller or per-service receipt is not the default solution.

Acceptance: create and write a volume immediately before destroying all three cluster VMs, OS disks and datastore,
without a final backup. Rebuild from Git, bootstrap secrets and surviving NAS state. Recover the original data with no
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

Use CSI snapshot clones mounted by Jobs for routine restore inspection. A readOnly pod mount is not evidence that the
original avoided journal replay, repair or formatting. For a non-mutating original-volume investigation, retain the
existing exceptional path until equivalent semantics are demonstrated. Quiesced backups and application/database restore
checks remain separate from CSI snapshot creation. Start with stopped synthetic writers and a small SQLite fixture;
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
| Shared setup and onboarding | Two services and a third added by values only; same PVC name in different namespaces; no lifecycle code edits; compare actual steps with NFS. |
| Authentication and access | Baseline CHAP: wrong/missing secret refused and no credential exposure. If no-CHAP is selected: enforced network/target restrictions and cross-volume access tested. Management credentials remain protected in either profile. |
| Creation interruption | Interrupt after ZVOL, target, extent and mapping operations; inspect before retry; one correct volume, no export outside the selected access policy or empty replacement. |
| Identity and replacement | Distinct clone IQNs, stable reboot IQNs, node replacement without handcrafted enrollment, backend target configuration survives reboot. |
| Competing writers | Same-cluster RWOP refusal; isolated old writer excluded before replacement writes; wrong-generation stop refused; ambiguous stop remains closed. |
| Full cluster loss | Write unique sentinels, remove all three lab cluster VMs/OS disks, discard the datastore, recreate from Git/secrets and recover the original backend filesystems/data without new volume allocation or metadata backup. |
| Unchanged merge procedure | Exercise Packer-to-Terraform-to-Ansible without backup hooks or checks. Native recovery must cover a volume created immediately before cluster loss and interrupted provisioning; no empty replacement is allowed. |
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
| Apps `scripts/storage/onboard.py`, `node_credentials.py`, `render_storage.py`; `storage/services/jellyfin.json` | CSI allocation and native recovery of bindings for new services, after onboarding/interruption/rebuild tests. Existing Jellyfin identity and admission stay. |
| Apps `scripts/storage/initiator_probe.py`, `maintenance_cli.py:observe_release` | CSI staging/cleanup and verified stop procedure; exceptional original-device forensic semantics must pass separately. |
| Ansible `roles/iscsi_initiator`, `scripts/iscsi_generation.py`, `group_vars/workers/iscsi.yml` | Image prerequisites and standard unique identity, after clone/replacement and old-writer tests. |
| Ansible `scripts/proxmox_fence.py`, `roles/storage_fencing`, `storage-fencing.yml` | Native Proxmox stop-and-confirm, after wrong-generation/timeout/competing-writer tests. |
| Ansible `roles/maintenance_runner`, `maintenance-runner.yml`, `scripts/maintenance_{lock,requests,executor,install}.py`; Apps `scripts/storage/{supervised_readonly,storage_inspection,reconciliation}.py` | Jobs, external backups and documented recovery. Inventory workflow callers, including Terraform's current maintenance serialization, before removing any runtime or lock. |
| Apps backup/identity/cutover/release modules and `jellyfin_backup.py` / `jellyfin_stages.py` | Preserve until each safety property and application acceptance path has replacement evidence. No blanket deletion. |

After architecture approval, prepare source PRs in order: inert Apps lab fixtures and recovery configuration outside
ApplicationSet discovery; Packer guest prerequisites/identity wiring; then Apps platform configuration and
Ansible bootstrap recovery after selecting a supported identity/adoption mechanism. No Velero work is included. Existing
VM replacement safety remains in scope for qualification. Build, allocation and activation have
separate reviewed plans. Review merge-triggered workflows before calling any PR inert: Packer can trigger downstream
manifest updates, and Ansible main can deploy. Put active changes behind a later activation PR.

The current proposal/evidence files live only under `docs/` and do not change discovered apps or deployment workflows.
Merging documentation has no intended workload change. A future storage activation or provider migration requires
workload downtime; its duration cannot be estimated from source evidence. Existing Jellyfin migration is not restarted.

## Current decision and next assessment

Velero is removed by user direction. Recovery must tolerate loss of all cluster VMs and Kubernetes datastore state,
without a final backup, while retaining external application data and identity. CHAP removal is under consideration;
existing authentication remains unchanged. TrueNAS 25 is the current target; compatibility with 26 is deferred. Prioritize
democratic-csi recovery on TrueNAS 25 and Debian, including uncertain lookups and durable volume identity. tns-csi remains
a TrueNAS-specific alternative that would require changing driver projects for Debian. Resolve these source-level gaps before proposing lab execution or a driver
selection. Do not expand the local maintenance framework to compensate for missing upstream guarantees by default.
