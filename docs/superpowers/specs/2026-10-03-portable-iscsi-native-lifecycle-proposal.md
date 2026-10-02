# Portable iSCSI architecture and qualification proposal

Date: 2026-10-03. Status: proposed architecture, awaiting review. Source assessment and synthetic probes only.

Recommend qualifying native CSI provisioning plus Velero recovery of retained PV/PVC metadata, with a single application
StorageClass contract across TrueNAS and Debian. democratic-csi remains the leading implementation family; its inspected
release is **not ready for selection under all requirements**. Remaining blockers are its TrueNAS REST dependency,
credentials entering process arguments, and guaranteed metadata recovery without Terraform backup hooks. Velero's
asynchronous backup alone does not establish the last property. Do not solve these by expanding the homelab maintenance
framework.

Approval requested is for this architecture and inert source preparation. It does not approve lab allocation, deployment,
production changes, upstream messages, or deletion. Current Jellyfin, CHAP, VM300, ownership records and safeguards remain
in place. No PostgreSQL or other application migration is included.

## Requirements and evidence boundary

After shared setup, adding storage means normal service values/PVC configuration. No service-specific Python, shell,
Ansible, manual login/mount commands, or identity/receipt construction. All three k3s VMs must be replaceable while
external application data survives. Replacing the storage provider must preserve application declarations, with a
separately qualified data transfer. Keep CHAP. Unreachable writers must be excluded before takeover; unattended failover
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

### Retained recovery has an existing implementation

Velero's maintainers describe restoring retained PV objects against their original storage when both snapshot backup and
filesystem backup are disabled for that backup. The same branch exists in v1.18.4: `handleSkippedPVHasRetainPolicy`
restores the PV, clears stale claim binding metadata, and the PVC path retains `volumeName` unless the PV was designated
for reprovisioning. This supplies a concrete supported candidate for rebinding without handwritten per-volume records.
[Maintainer explanation](https://github.com/velero-io/velero/discussions/8704),
[v1.18.4 restore implementation](https://github.com/velero-io/velero/blob/v1.18.4/pkg/restore/restore.go#L3035-L3050).

This is source evidence, not a completed restore. It needs an external metadata backup and preserved secrets/keys. It is
not automatic rediscovery from namespace/name alone, nor recovery after losing both Kubernetes metadata and its backup.
Metadata-only recovery preserves current backend data; separate data backups cover backend loss or corruption.

Do not substitute ordinary CSI snapshot restore: that creates a volume from a snapshot and does not prove rebinding the
original retained volume. Filesystem restore also has a separate provisioning path.
[Velero restore semantics](https://velero.io/docs/v1.18/restore-reference/).

### TrueNAS API longevity remains unresolved

The latest democratic-csi tag remains v1.9.5 (`b5be00c0748cbae251e661392cc7ab9fea335ac9`). GitHub's latest-release endpoint
returns 404 for this project; the version statement comes from tags. Its REST transition issue remains open. The
maintainer announced WebSocket work, including an intended TrueNAS 26 minimum. The inspected `next` HTTP client at
`a7e9101db04e924f5328573572f0294c89b4d37f` still constructs `/api/v2.0`. An announced plan is not a supported release.
[Issue 509](https://github.com/democratic-csi/democratic-csi/issues/509),
[inspected development client](https://github.com/democratic-csi/democratic-csi/blob/a7e9101db04e924f5328573572f0294c89b4d37f/src/driver/freenas/http/index.js#L60).

TrueNAS 25.10 retains REST; TrueNAS 26 removes it. A 25.10 lab can characterize legacy behavior, but is not a sustainable
production API path. The SSH TrueNAS driver still uses the API for export management; generic Linux targetcli must not be
used to bypass TrueNAS middleware.
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

## Architecture choices

| Choice | Benefits | Costs and decision |
| --- | --- | --- |
| democratic-csi family plus Velero retained metadata restore | Existing CSI family; TrueNAS and Debian implementations; standard PVC onboarding; native backup/rebinding candidate | Recommended qualification target, conditional on resolving credential transport and a released sustainable TrueNAS API path. No production driver selection yet. |
| Different controllers behind the same application StorageClass contract | Could use a WebSocket TrueNAS controller and democratic-csi on Debian without changing applications | More implementations to qualify. Official TrueNAS v1.3.0 still has unresolved CHAP recovery/secret handling; tns-csi v0.18.1 lacks CHAP. Not currently a complete authenticated alternative. |
| Standardize block storage on a separate Debian ZFS/LIO server | Removes TrueNAS management API dependency from future application storage | Changes the backend architecture and requires storage allocation/data migration; does not fix democratic-csi argument handling. It no longer demonstrates native TrueNAS provisioning. Requires a separate decision, not a silent fallback. |

The official TrueNAS release is still v1.3.0; [issue 66](https://github.com/truenas/truenas-csi/issues/66) and
[PR 48](https://github.com/truenas/truenas-csi/pull/48) remain open/unmerged. tns-csi remains v0.18.1. No candidate was
selected by dropping CHAP. If the first two choices cannot meet the gates without a driver fork or substantial local
orchestration, return to the third architecture decision rather than expanding VM300.

## Proposed application and platform contract

An application author selects `iscsi-state`, size and `ReadWriteOncePod` in ordinary persistence values. Existing NFS
defaults stay intact. A second service and then a third use the identical schema. There are no target names, NAS paths,
CHAP fields or recovery receipts in application values. Same-named PVCs in different namespaces must remain distinct.

Shared infrastructure owns a separate CSI release/driver identity, the non-default `iscsi-state` StorageClass with
`Retain`, ext4 and validated RWOP-capable sidecars, and backend configuration Secrets. It must not reuse or edit
`org.democratic-csi.retained`. Snapshot support is configured once. Fresh empty volumes may be formatted; existing
Jellyfin's format suppression remains unchanged. Recovery of an existing volume must reject missing/wrong filesystem
identity before opening a writer.

Use generated unique CSI handles. Backend annotations may aid inspection but are not an adoption mechanism. The Debian
profile uses ZFS/LIO with target configuration persisted across reboot. Its example enables generated initiator ACLs;
CHAP plus a storage-network allowlist is the proposed lab policy, not an asserted equivalent of per-IQN authorization.
Wrong or absent CHAP must fail; assess cross-volume access before accepting the platform threat model. Kubernetes app
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

### Cluster ownership of backup and bootstrap recovery

Requirement clarified on October 3: the user keeps the existing Packer PR merge, generated Terraform PR review and
Terraform PR merge procedure. No manual Velero command, pre-merge backup verification, new checkbox or separate recovery
approval is required for an already-authorized routine rebuild after qualification.

Backup is a cluster-platform responsibility. Deploy shared Velero schedules and backup-health monitoring through Apps,
write metadata to protected storage outside the replaceable k3s VMs, and alert on failed backups, missing coverage and
excessive age. Terraform owns VM lifecycle and does not invoke Velero, wait for a backup, or carry a backup reference.
This supersedes the proposed per-apply Terraform recovery checkpoint.

Fresh-cluster bootstrap installs the recovery components, discovers externally stored backups and restores the selected
complete inventory before service ApplicationSets or new volume provisioning can run. Existing-cluster bootstrap must
not restore over surviving bindings. Recovery checks remain automatic. Preserve writer exclusion through VM replacement
and bootstrap; removing Velero from Terraform does not remove that independent safety responsibility. An unavailable
old API or missing backup is not evidence of an empty first installation.

The requested property is durable recoverability of metadata for every active volume. A native Velero schedule is
asynchronous and cluster-object backups are not atomic. A newly bound PVC may be absent from the latest successful
backup; frequent schedules, alerts or event-triggered asynchronous backups do not eliminate that window. No acceptable
metadata-loss window has been agreed. Do not claim that this design currently guarantees arbitrary-time full rebuilds.
[Velero backup semantics](https://velero.io/docs/v1.18/how-velero-works/).

Before selecting Velero as the sole recovery source, resolve this freshness gap with supported mechanisms: assess
preserving authoritative metadata outside the replaceable VM lifecycle or supported native retained-volume discovery.
Do not add a custom backup watcher, admission controller or provider adapter by default. A bounded backup-age policy is
an alternative only if the user explicitly accepts its recovery limits. Velero remains a candidate for backup/restore;
its necessity and sufficiency for binding recovery remain conditional on this requirement.

### Recovery operations

1. Keep protected Velero metadata backups outside k3s, including every bound retained PV/PVC, namespaces and the secret
   recovery material. A metadata schedule may cover the whole cluster to avoid per-service enrollment; restore only the
   platform resources needed for storage recovery. Keep data backups separate. These backups are maintained by the
   cluster independently of Terraform. Their freshness limitation above must be resolved before claiming the required
   rebuild guarantee.
2. Exclude all old writers using verified Proxmox power state and VM generation. For an uncertain stop, remain closed.
   For full replacement, prove all old cluster VM generations are stopped; reused VMIDs alone are insufficient.
3. Recreate three Debian/k3s VMs with distinct initiator identities. Bootstrap recovery infrastructure without service
   ApplicationSets and with the iSCSI provisioner disabled. No ordinary fresh-cluster auto-bootstrap may open writers.
4. Restore retained PV/PVC metadata from a completed backup using Velero's metadata-only path. Restore credential access
   and driver identity. Require exact `volumeHandle`, attributes, claim mapping and existing backend objects. Bound status
   alone is insufficient. Missing backup/PV, duplicate mappings, permission errors and timeouts stop recovery.
5. While provisioning and workloads remain held, verify backend existence and filesystem/data identity using the
   qualified recovery procedure. A missing device must never trigger a create or format fallback. If standard tools
   cannot enforce this before staging, the candidate fails qualification; do not add an adopter controller.
6. Only after the complete expected inventory agrees, enable CSI operations and release restored services. Enable new
   volume provisioning last. Test a deliberately missing PV backup and denied backend lookup: neither may allocate an
   empty replacement. If a backup predates a PVC, that service remains held until its mapping is recovered.

Backup runs continuously on the cluster's configured schedule; recovery runs during bootstrap after replacement.
The merge procedure remains unchanged. External metadata durability and restore-before-GitOps ordering remain necessary.
Independent k3s datastore snapshots do not by themselves close the asynchronous-backup freshness gap.

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
| Authentication and access | CHAP/mutual CHAP as configured; wrong/missing secret refused; no secrets in arguments/logs/Helm state/PVs; unauthorized initiator/network refused. |
| Creation interruption | Interrupt after ZVOL, target, extent and mapping operations; inspect before retry; one correct volume, no unauthenticated partial export or empty replacement. |
| Identity and replacement | Distinct clone IQNs, stable reboot IQNs, node replacement without handcrafted enrollment, backend target configuration survives reboot. |
| Competing writers | Same-cluster RWOP refusal; isolated old writer excluded before replacement writes; wrong-generation stop refused; ambiguous stop remains closed. |
| Full cluster loss | Write unique sentinels, remove all three lab cluster VMs/OS disks, recreate, restore metadata, recover the original handles/filesystems/data without new backend volume allocation. |
| Unchanged merge procedure | Exercise Packer-to-Terraform-to-Ansible without manual Velero commands/checks or Terraform backup hooks. Cluster-owned backups and automatic bootstrap recovery must cover a volume created immediately before cluster loss, including an interrupted/in-flight backup; no empty replacement is allowed. |
| Recovery failures | Missing/stale metadata, duplicate backend identities, namespace collisions, HTTP 403/500/timeouts and missing storage leave affected writers held and allocate nothing. |
| Backup and maintenance | Interrupted capture stays incomplete; restore checks use clones/new volumes; verify source remains unchanged; compare file and SQLite contents independently. |
| Backend portability | Repeat the same declarations/recovery suite on TrueNAS and Debian; separately transfer verified data TrueNAS to Debian and reverse, with old-writer exclusion. |

Run authentication/argument checks before authenticated provisioning. A fixed supported credential path is an execution
gate. TrueNAS 25.10-only results do not clear the production API gate; repeat against the selected supported WebSocket
release/version when available. Preserve all historical production data/evidence and lab evidence; any lab cleanup must
name only the disposable resources explicitly authorized for removal.

## Removal and delivery boundaries

| Current responsibility and actual paths | Candidate replacement and removal gate |
| --- | --- |
| Apps `scripts/storage/onboard.py`, `node_credentials.py`, `render_storage.py`; `storage/services/jellyfin.json` | CSI allocation and restored PV metadata for new services, after onboarding/interruption/rebuild tests. Existing Jellyfin identity and admission stay. |
| Apps `scripts/storage/initiator_probe.py`, `maintenance_cli.py:observe_release` | CSI staging/cleanup and verified stop procedure; exceptional original-device forensic semantics must pass separately. |
| Ansible `roles/iscsi_initiator`, `scripts/iscsi_generation.py`, `group_vars/workers/iscsi.yml` | Image prerequisites and standard unique identity, after clone/replacement and old-writer tests. |
| Ansible `scripts/proxmox_fence.py`, `roles/storage_fencing`, `storage-fencing.yml` | Native Proxmox stop-and-confirm, after wrong-generation/timeout/competing-writer tests. |
| Ansible `roles/maintenance_runner`, `maintenance-runner.yml`, `scripts/maintenance_{lock,requests,executor,install}.py`; Apps `scripts/storage/{supervised_readonly,storage_inspection,reconciliation}.py` | Jobs, external backups and documented recovery. Inventory workflow callers, including Terraform's current maintenance serialization, before removing any runtime or lock. |
| Apps backup/identity/cutover/release modules and `jellyfin_backup.py` / `jellyfin_stages.py` | Preserve until each safety property and application acceptance path has replacement evidence. No blanket deletion. |

After architecture approval, prepare source PRs in order: inert Apps lab fixtures and recovery configuration outside
ApplicationSet discovery; Packer guest prerequisites/identity wiring; then Apps-owned backup scheduling/monitoring and
Ansible bootstrap recovery after the metadata-durability decision. No Velero integration belongs in Terraform. Existing
VM replacement safety remains in scope for qualification. Build, allocation and activation have
separate reviewed plans. Review merge-triggered workflows before calling any PR inert: Packer can trigger downstream
manifest updates, and Ansible main can deploy. Put active changes behind a later activation PR.

The current proposal/evidence files live only under `docs/` and do not change discovered apps or deployment workflows.
Merging documentation has no intended workload change. A future storage activation or provider migration requires
workload downtime; its duration cannot be estimated from source evidence. Existing Jellyfin migration is not restarted.

## Review decision

Approve this native architecture for **inert source preparation**, including Velero metadata recovery as a shared
platform candidate, while retaining CHAP and keeping credential transport, sustainable TrueNAS API support and complete
metadata recoverability without Terraform backup hooks as deployment gates. Approval does not waive either blocker or allocate the lab. If those gates cannot be met with
supported upstream mechanisms, return a concrete backend-architecture decision before building more local orchestration.
