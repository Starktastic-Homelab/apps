# Recoverable application state: storage policy and retained iSCSI rehearsal

Date: 2026-09-20. Status: platform design proposed; production RAM preparation
and cluster recovery completed. The later [execution report](../reports/2026-09-21-retained-iscsi-rehearsal.md) distinguishes passed checks from remaining production acceptance.

Live audit update: see the [September 20 report](../reports/2026-09-20-application-state-audit.md).
The user supplied working cluster/Proxmox access and selected the existing
Proxmox host for the lab, accepting temporary memory overprovisioning. This
replaces the separate-host assumption. Measured RAM headroom still requires a
concrete resource arrangement before starting the lab; no production guest
resizing, host tuning or reboot is implied by that choice.

The user subsequently authorized planning temporary production RAM reductions
and stopping runner VM 300, with a proposal first for the other VMs and
Terraform PRs for K3s changes. The [RAM proposal](2026-09-20-iscsi-lab-memory-proposal.md)
keeps TrueNAS/master RAM unchanged before a smaller 12 GiB synthetic lab. The
runner remained up through infrastructure CI and recovery, then was stopped. The user approved the RAM
arrangement, then requested both workers in one PR and proposed a full rebuild.
Terraform PR #222 had a verified plan for both memory updates. The destroy
option was subsequently selected and confirmed by the user, who merged the PR
and accepted potential Filebrowser/Audiobookshelf state loss. All three K3s VMs
were recreated; Terraform and Ansible passed. See the [execution report](../reports/2026-09-20-cluster-rebuild-memory.md)
for recovered application state and memory measurements.

## Outcome and boundaries

Critical application state across the Apps repository must reconnect after
complete Kubernetes/node recreation. Replacing all three K3s VMs from a new
Packer Debian image through Terraform is a normal lifecycle operation, not an
exceptional disaster. TrueNAS and its data remain outside that replacement
boundary. The fresh cluster must recover using retained NAS data, Git and
externally restored credentials, without old worker disks or Kubernetes state.
Jellyfin is the first intended block-storage pilot, not the scope of the issue.
SQLite contention predates Jellyfin 12 according to the supplied handoff;
neither the resolved GPU incident nor successful playback proves it fixed.
Block storage may improve storage behavior but does not remove SQLite's
single-writer constraint. Application-level performance acceptance remains a
separate gate.

This document authorizes no deployment. The requested next execution scope is
lab implementation and isolated rehearsal, followed by cleanup and a report.
Production NAS enablement, benchmarking, migrations, reboots, merges, and the
separate PostgreSQL backup correction are outside that scope.

## Platform policy clarified by the user

The user reports similar symptoms across SQLite-backed services on NFS. Treat
that as a platform-wide investigation hypothesis; configuration can identify
exposure but cannot establish that every service is failing for the same reason.
Collect service-specific database errors, journal modes, mount details,
transaction/IO latency and timestamps of probe failures before attributing them.
Check common NAS/network/resource problems alongside SQLite lock contention.

There are two independent choices: which database engine an application
supports, and where its durable files live. Native PostgreSQL adoption and
retained iSCSI can coexist; neither requires moving shared media off NFS.

| State or application capability | Proposed preference | Acceptance needed |
|---|---|---|
| Mature native PostgreSQL support and supported migration | Consider shared PostgreSQL, with per-service database/role | Migration fidelity, connection/resource budget, dependency recovery, backup restore |
| SQLite or another embedded DB without a suitable supported alternative | Rehearse retained iSCSI with a local filesystem and exclusive mount | Locking/latency behavior, fencing, explicit binding, complete rebuild and backup restore |
| Shared media, documents and other suitable file workloads | Keep NFS | Stable paths, ownership, consistent backup and application references |
| Disposable cache/transcodes | Local ephemeral storage where capacity permits | No authoritative state, no unwanted node affinity, bounded resource use |
| Critical data currently on worker-local storage | Include in recovery audit regardless of DB engine | External persistence or an explicitly accepted, tested restore contract |

[SQLite's network-filesystem guidance](https://www.sqlite.org/useovernet.html)
describes locking and synchronization hazards, and its
[WAL documentation](https://www.sqlite.org/wal.html) requires same-host access
and excludes network filesystems. That supports investigating this placement;
it does not prove the cause of each observed timeout.

With iSCSI, the node mounts a local filesystem on a remotely supplied block
device. This is materially different from opening SQLite files through NFS,
but network/storage durability, latency and exclusive ownership still matter.
SQLite still serializes writers. An ordinary ext4 filesystem must not be
mounted by two nodes concurrently. The recovery difficulty is addressed by
recording the actual backend identity and refusing fresh allocation on restore.

[PostgreSQL explicitly permits NFS](https://www.postgresql.org/docs/18/creating-cluster.html#CREATING-CLUSTER-NFS)
with hard client mounts and reliable server-side persistence of fsync writes;
it avoids reliance on NFS file locking. NFS interruption can still stall the
server. Moving applications to PostgreSQL changes the access protocol, but
does not remove the NAS dependency or the need to recover the server's own
volume. PostgreSQL could itself use retained block storage later if evidence
justifies that separate change.

Native support does not by itself establish a lossless SQLite migration.
Verify support for each pinned application version, plugin databases and its
official migration path. The official
[Sonarr](https://github.com/Servarr/Wiki/blob/master/sonarr/postgres-setup.md) and
[Radarr](https://github.com/Servarr/Wiki/blob/master/radarr/postgres-setup.md)
guides support PostgreSQL but call conversion of an existing SQLite installation
unsupported; their built-in backups do not cover PostgreSQL.
[Home Assistant Recorder](https://www.home-assistant.io/integrations/recorder/)
supports PostgreSQL, still recommends SQLite, and does not support history
migration. Moving Recorder does not preserve Home Assistant's other state.
Consequently, do not adopt a blanket "PostgreSQL wherever configurable" rule.
Jellyfin's third-party provider remains an optional
exception with additional compatibility/migration risk, not a prerequisite for
the platform. [Jellyfin's storage guidance](https://jellyfin.org/docs/general/administration/storage/)
still describes SQLite and recommends local database storage; it is not an
endorsement of this particular CSI implementation.

Before expanding shared PostgreSQL usage, resolve the independently tracked
false-success backup bug and prove restoration, reassess its 1 CPU/1GiB/100
connection limits, and validate single-server recovery. The current values
also remove `postmaster.pid` if present during initialization; file existence
alone does not prove an old server has stopped. Review that behavior against
the same fencing/exclusivity requirement before increasing dependency on it.
This finding is source-based, not evidence of a current duplicate server.

The broader decision sequence is: inventory all durable state, verify affected
services, identify native DB alternatives, prove shared block recovery, then
select and migrate each service deliberately. The isolated block rehearsal
below remains useful without committing every service to iSCSI.

## Evidence checked in this session

| Evidence | Finding | Confidence boundary |
|---|---|---|
| Apps checkout `f486e24` | Clean before this document; Jellyfin image matches handoff, config claim is NFS RWX/15Gi, cache is local-path RWO/50Gi | Source configuration, not live PV inspection |
| Jellyfin values and README | `/config`, separate `/config/cache`, body-aware readiness; README records cache pinning to worker-01 | Current node affinity requires a later live read |
| NFS values | Default class, Retain, stable namespace/claim path | No NAS state queried |
| Media static PV/PVC | Explicit `volumeName`, `Delete=false` | Existing example lacks `Prune=false` |
| ApplicationSets | Phased rollout, automated prune/self-heal, SSA, RespectIgnoreDifferences | No storage capacity ignore rule currently present |
| Ansible checkout `7a0ed65409bbe33caefe9a70ce3888a2d48ab95d` | Generic `k3s_common` exists; bootstrap pre-seeds Sealed Secrets key before Argo | GitHub API connection failed; remote freshness not verified |
| Old POC and September 19 plans | Not found at old paths or by filename search under local Projects, Copilot and attachments | POC results are handoff-reported, not independently revalidated |
| Execution environment | QEMU not found in PATH; `/dev/kvm` absent; `/tmp` is 16GiB tmpfs | Previous host's virtualization readiness does not carry over |
| PostgreSQL backup script | Producer pipeline still tests gzip's status | Separate correctness issue remains open |

The table above records the initial source-only assessment. Later user-supplied
access, live audit, authorized Terraform rebuild and runner shutdown are
recorded separately in the linked audit and execution reports; no production
NAS iSCSI configuration or application storage migration has occurred.

## Architecture choice

For the block-storage candidate, use the standard full `freenas-api-iscsi`
controller, with explicit retained
bindings after approved provisioning. This keeps native lifecycle operations
available while making recovery independent of fresh PVC UIDs. Node-manual
remains useful as historical evidence, but would leave expansion and lifecycle
work outside the controller. Fully dynamic recreation is rejected because a new
claim must not silently obtain new storage for an established application.

Pinned [driver source](https://github.com/democratic-csi/democratic-csi/blob/v1.9.5/src/driver/freenas/api.js)
advertises volume expansion, snapshots and cloning, with block node expansion;
publish/unpublish capability is commented out. These are source capabilities,
not accepted integrations or physical fencing.

Ownership remains:

- Ansible: generic initiator packages/identity, kubelet shutdown configuration,
  bootstrap key restoration, node-to-VM identity and fencing.
- Apps infrastructure: CSI, admission, reusable onboarding/export checks.
- Apps service directory: canonical retained mapping, PVC, startup checks,
  backup and migration requirements.
- NAS: external persistent volumes and their native identifiers.

No per-service Ansible inventory, private driver naming option, vendor patch,
custom operator, or default StorageClass change is needed.

## Preliminary repository inventory

This is a configuration inventory, not live database detection or a failure
report. `templates/common.yaml` defaults service `/config` to NFS/RWX;
ApplicationSet baseApp inheritance also reaches language variants.
Infrastructure charts need their own storage review.

| Group | Evidence and follow-up |
|---|---|
| Explicit PostgreSQL selection/endpoints | Authentik, Vikunja, Paperless, Lingarr, Dispatcharr and Mealie values; Immich uses its own PostgreSQL. Shared and Immich PostgreSQL storage remains NAS-backed. |
| Secret-injected DB configuration | Vaultwarden and Listmonk public values do not establish their DB engine/endpoint; handoff reports PostgreSQL, but confirm runtime configuration without exposing credentials. |
| Strong embedded-file DB evidence | Cleanuparr values explicitly mention SQLite; Excalidash declares a file database URL; ntfy declares auth/cache/webpush DB paths on NFS-backed mounts. Confirm actual engines/modes where not explicit. |
| Likely SQLite-on-NFS candidates | Jellyfin, Sonarr/Radarr/Lidarr/Prowlarr/Bazarr and variants, Seerr, Navidrome, Audiobookshelf, Calibre-Web Automated and Autobrr. Check persisted configs before declaring each engine or incident. |
| Additional audit targets | Home Assistant Recorder, Karakeep, Bytestash, ConvertX, Grafana, CrowdSec LAPI and pgAdmin metadata; default behavior is not proof of the live backend. |

The recovery audit must cover files outside SQL as well: documents, uploads,
attachments, photos/media, Home Assistant configuration and Matter identities,
Zigbee state, download sessions and any persistent queues. A PostgreSQL move
does not migrate these automatically.

Two concrete configuration concerns deserve follow-up independently of SQLite:

- `services/operations/filebrowser/manifests/templates/data-pvc.yaml` explicitly
  uses local-path; the adjacent ConfigMap puts `database.db` on that claim.
  This authoritative metadata must be classified and externally preserved for
  complete VM replacement. It is different from Jellyfin's disposable cache.
- Mosquitto's ConfigMap sets `persistence_location /config/data/`, while its
  values disable inherited config persistence and mount the claim at
  `/mosquitto/data`. Verify image/runtime path resolution; the declared paths
  alone do not show persistent coverage. Audiobookshelf likewise needs an
  actual data-path audit because no `/metadata` mount is declared.

For every candidate record engine/version, actual database path and journal
mode, PVC/PV/backend, other durable files, observed errors and supporting time
range, official alternative/migration support, backup/restore evidence and the
proposed target. Keep this inventory separate from claims of tested recovery.

## Provisioning, registration and first initialization

Use a non-default `iscsi-retained` class with Retain and expansion enabled.
The proposed name is new, not a claim that the class already exists.

1. An approved onboarding run identifies one new service/claim, requested size,
   unique operation ID, expected NAS/pool and dedicated provisioning identity.
   Deny onboarding if the service already has a retained mapping.
2. Permit dynamic creation only for that exact claim and identity. Provision the
   final service claim in its final namespace; do not copy between temporary
   claims merely to transfer ownership. Workload remains disabled.
3. Export the actual generated PV name, CSI driver and volumeHandle, necessary
   volumeAttributes, filesystem type, secret references, mount options and
   observed capacity. Correlate with NAS ZVOL path/GUID, target IQN, LUN and
   extent mapping. Preserve native driver metadata on the NAS.
4. Save one canonical service storage record in Apps and generate recovery
   manifests/policy expressions from it. Record controller instance identity
   and dataset parent configuration needed to interpret the handle. Allowlist
   export fields; reject inline credentials. Never fabricate identity from the
   friendly target name.
5. Persist/review the record outside the cluster before writing important data.
   Adopt the existing final claim/PV into GitOps without deleting/recreating
   them; test SSA adoption. Generated recovery PV reserves the claim by name
   and namespace, but omits old claim UID. Omit object UIDs, resource versions,
   managedFields, ownerReferences and status; let controllers rebuild runtime
   finalizers and binding metadata.
6. Disable the onboarding exception and its credentials after capture. Normal
   PVC creation now requires the recorded `volumeName`.
7. Initialization is a separate explicit operation. Record its authorization
   and consumption in an externally durable operation journal before writing.
   Verify backend identity and expected empty state. An interruption after
   consumption requires reconciliation; it never auto-reissues permission.
   No GitOps startup Job or recreated PVC UID grants initialization authority.
8. After initialization/migration, record filesystem identity and a service
   identity marker, verify the expected application data, then enable the
   workload. Normal startup can verify but cannot initialize or repair.

The operation journal is an execution receipt stored outside disposable VMs,
not a second manually maintained backend inventory. A retry resumes the same
claim/operation and inspects actual state. A missing claim after an ambiguous
provisioning response stops for NAS reconciliation instead of making a new PVC.

For Jellyfin, reject missing/empty `data/data/jellyfin.db`, mismatched service
marker and unexpected schema/catalog identity before the server starts. The
guard must not create a missing SQLite file. Full integrity/application checks
belong to migration/recovery acceptance rather than every health request.
A filesystem mount or marker alone is insufficient proof of correct data.

## Admission and GitOps ownership

Use native [ValidatingAdmissionPolicy](https://kubernetes.io/docs/reference/access-authn-authz/validating-admission-policy/)
with Deny bindings and fail-closed evaluation. Generate ordinary CEL conditions
from canonical records; no custom resource/controller is required. CEL is not
an arbitrary live PV/NAS lookup: backend correlation belongs to preflight and
data verification.

The lab must prove the following rules, including controller UPDATE requests:

- For registered claim names, enforce class, access mode and exact PV name,
  even if a request omits or substitutes the class.
- Other claims using the retained class are denied unless they match the exact
  currently approved onboarding identity, namespace/name and size bound.
  User-set labels and namespace membership alone grant no exception.
- Registered PVs enforce recorded CSI identity, Retain and claim reservation;
  ordinary users cannot replace them or switch reclaim policy to Delete.
  A trusted volume binder may populate the current claim UID. Resize sidecars
  may update capacity/status without changing backend identity.
- RBAC restricts PV/StorageClass, policy, onboarding-token and namespace
  administration. Ordinary pods cannot impersonate onboarding or create an
  alternate class for the same CSI provisioner. Cluster-admin remains trusted.
- Restore policy and bindings before workload/onboarding access is enabled.
  Test actual denied requests; Argo phase ordering alone is not proof that
  admission is enforcing.

Protect both PV and PVC with `Prune=false,Delete=false` and Retain. These Argo
options cover different deletion paths; direct privileged API deletion is a
separate control. See [Argo sync options](https://argo-cd.readthedocs.io/en/stable/user-guide/sync-options/).
Removal of a service is not backend retirement. Retirement needs an explicit
volume-specific operation, writer shutdown and backup/recovery-point decision.

Ignore only controller-owned differences for these registered PVs, scoped by
resource name: capacity and binder-owned claim UID metadata. Do not globally
ignore all PV specs, CSI identifiers or PVC requests. Preserve existing Argo
value layers and phase dependencies. Reconciliation must be tested on both
existing resources and fresh creation.

## Expansion and recovery after interruption

Git owns desired PVC request; CSI owns live PV capacity and resize status.
The recovery record stores last verified backend/filesystem capacity.

1. Record old verified capacity and larger requested capacity; reject shrink
   and insufficient NAS headroom before changing the PVC request.
2. Increase only the PVC request. Do not pre-edit PV capacity: Kubernetes warns
   that doing so can bypass actual expansion. See [volume expansion](https://kubernetes.io/docs/concepts/storage/persistent-volumes/#expanding-persistent-volumes-claims).
3. Verify NAS ZVOL, node block device, filesystem, PVC capacity and resize
   conditions, plus original data and acknowledged writes under load.
4. Update the canonical recovery capacity only after verification; generate
   refreshed recovery declarations. On an existing PV Argo respects CSI's
   capacity; on a fresh cluster the verified value seeds the new PV object.
5. A rebuild during an incomplete expansion stops workload startup for
   reconciliation. Inspect actual capacity at every layer, then resume native
   resize or finalize the record. Never shrink, invent success, or provision a
   replacement. Test interruption before backend grow, after backend grow and
   before filesystem/record completion.

## Credentials, bootstrap and workload placement

Restore the external Sealed Secrets private key before Argo; restore dedicated
NAS API and CHAP secrets through the existing mechanism. Preserve exact secret
names/namespaces in CSI references. Controller API credentials must not be
mounted in application pods. Use trusted/pinned NAS TLS, never silently disable
verification. Wrong/missing credentials must block access, not create storage.

In the lab, determine the minimal TrueNAS 25.10.6 permissions actually required
for provisioning, discovery, resize and snapshots. Test denied unrelated
operations. If API roles cannot restrict the controller to the desired dataset
scope, report that limitation as a production decision; naming prefixes are
not a permission boundary. Do not substitute the dashboard key.

Use a one-replica StatefulSet with a separately declared existing RWOP claim;
avoid volumeClaimTemplates that could dynamically allocate a fresh volume.
Render the actual app-template 5.2.1 layers and test every generated mount.
[RWOP](https://kubernetes.io/docs/tasks/administer-cluster/change-pv-access-mode-readwriteoncepod/)
requires compatible CSI sidecars; freeze their image digests and CSI version in
the lab bill of materials, then prove the negative control.

For the lab Jellyfin-shaped fixture, use disk-backed `emptyDir` for disposable
cache, with explicit ephemeral-storage requests/limits and measured headroom.
Proposed later Jellyfin adoption uses this pattern only after checking real
cache/transcode requirements. Keeping the current local-path PVC would retain
its node affinity and invalidate a claim of automatic cross-worker recovery.
Media stays separately NFS-backed. No production cache change is made here.

## Fencing contract

StatefulSet identity and RWOP do not fence another cluster or a partitioned
machine. [Force deletion](https://kubernetes.io/docs/tasks/run-application/force-delete-stateful-set-pod/)
can permit duplicate writers. For an unreachable node, require an approved
node-level operation that verifies cluster/node UID, VM identity and host,
prevents automatic restart, powers off the exact VM and independently confirms
shutdown before applying recovery actions. Revalidate those identities when
executing approval; reject a stale approval if the VM mapping changed.

Only after confirmed shutdown may recovery use out-of-service taint or remove
stale writer objects. NAS session evidence is supplementary, not a substitute
for fencing. Failure to prove shutdown means downtime. Return-to-service checks
keep the old machine unable to rejoin/write until stale mounts and workload
state are resolved. [Node shutdown guidance](https://kubernetes.io/docs/concepts/cluster-administration/node-shutdown/)
also requires explicit graceful-shutdown configuration and warns against
out-of-service treatment of machines that are still running.

Before full-cluster replacement, fence/stop every old potential writer and
disable its automatic return. A new cluster's RWOP cannot police the old one.
The local lab may use QEMU process/QMP identity and confirmed exit to exercise
this sequence. That is not live validation of a future Proxmox fencing adapter.

## Bounded implementation and rehearsal sequence

All lab artifacts live under a fresh, non-discovered directory such as
`tests/iscsi-platform/`; do not add an `app.yaml` beneath production discovery
paths. Secrets/runtime disks stay outside Git. Proposed execution stages:

1. **Host preflight:** use the user-selected Proxmox host `10.9.9.20`, with
   test-only VM/disk identities and private networking. Temporary configured-RAM
   overprovisioning is authorized. The original budget was approximately 18GiB;
   the separate RAM proposal instead starts with a constrained 12GiB synthetic
   lab and requires measured host headroom. Retain at least 80GiB disk headroom.
   Follow that proposal's launch gates and the live audit's capacity findings.
   Production worker resizing/restarts follow the separately reviewed
   procedure; swap and ARC tuning are not included. Download checksum-verified inputs.
2. **Fixture:** one disposable TrueNAS VM, one K3s control-plane VM and two
   workers concurrently; private control/storage networks, loopback management,
   no production bridge, physical disks or production data. Use fresh test IDs,
   dedicated credentials, two 2GiB service volumes (grow one to 4GiB), and
   immutable pins validated before execution. Start from handoff pins only if
   those exact artifacts are obtainable and verified.
3. **Shared lifecycle:** implement small onboarding/export/verify commands,
   canonical records, native policy, GitOps rendering and two synthetic SQLite
   StatefulSets. Test adoption, replay/partial failure and credential restoration.
4. **Failure and rebuild:** exercise drain, partition, approved fencing, active
   writes, NAS interruption and pristine cluster recreation with retained NAS.
5. **Resize and restore:** grow under load, interrupt each resize stage, rebuild
   again, restore snapshot to a distinct volume, and restore an application-
   consistent backup from storage outside the test NAS into another destination.
6. **Cleanup:** stop every test VM/process; remove disks, downloads, networks,
   listeners, private keys, tokens and kubeconfigs. Retain reusable source,
   manifests, checksums and sanitized reports. Stop after reporting results.

Public downloads may use a controlled egress path; lab storage/workloads cannot
reach production subnets. Every mutation verifies test ownership and exact VM,
disk and NAS identity. Resource ceilings and cleanup apply on failure too.

## Required acceptance evidence

| Test | Pass requirement |
|---|---|
| Two volumes | Distinct backend identities and datasets; swapped bindings/markers fail before application startup |
| Provisioning retry | Repeated same operation and lost-response cases produce one backend; ambiguous missing claim stops |
| Admission | Dynamic ordinary claim, class substitution, foreign PV binding, reclaim-policy change and spoofed onboarding denied; legitimate binder/resize operations succeed |
| Empty/wrong backend | Missing ZVOL, empty replacement, missing DB, changed marker and wrong credentials never initialize a catalog |
| RWOP | Second writer pod blocked; a second claim cannot alias an established backend through the ordinary workflow |
| Pod replacement/drain | Original contents and new committed writes persist after safe unmount/remount on the other worker |
| Partition | Worker loses control-plane access while retaining NAS access and active writes; no new writer starts until verified fencing |
| Fencing | Timestamped identity/approval/off confirmation precedes replacement; unavailable fence mechanism leaves workload blocked |
| Full rebuild | Old disks/cluster state destroyed; new CA/node/PV/PVC identities; same NAS objects and data; no CreateVolume for established services |
| Active writes | Deterministic transaction IDs/values; external ledger records acknowledgements only after commit; every acknowledged transaction survives; integrity_check passes |
| NAS interruption | Bounded outage/reconnect behavior recorded, no duplicate writer or lost acknowledged transaction; no fsync/stable-write relaxation |
| Resize | NAS/block/filesystem/PVC capacities increase; data survives load and interrupted resize; refreshed records recover after another rebuild |
| Snapshot/backup | Restored distinct volume passes key/value and integrity checks; independent backup restore succeeds with original NAS unavailable |
| Retention | App removal, pruning attempt, permitted PVC deletion and cluster destruction do not delete backend data |
| Credential bootstrap | Fresh cluster decrypts restored secrets without old Kubernetes state; missing key fails closed |
| Cleanup | No test VMs/listeners/private artifacts remain; disk/resource inventory reconciled |

The write ledger must fsync acknowledgements outside the destroyed cluster.
Transactions committed but not acknowledged may also survive; counts alone
are insufficient. A VM reboot or network interruption does not prove physical
NAS power-loss durability. Do not label synthetic fixtures as Jellyfin
application acceptance, or local QMP fencing as tested production fencing.

## Later gates

Phase B needs separate approval for production NAS iSCSI and disposable storage.
Use a consistent private Jellyfin copy with outbound integrations disabled;
compare actual NFS/iSCSI p95/p99 transaction and request latency, errors, probes,
playback-progress concurrency, browsing/background work and shared NAS load.
Agree measurable performance/RPO/RTO targets before that benchmark.

Production adoption requires a separate reviewed rollout: fresh size measurement,
new explicit claim, all writers stopped, complete cold `/config` copy excluding
disposable cache, plugin/SQLite/LiteDB/application validation and independent
backup restore. Preserve existing probes. After writes on iSCSI, rollback needs
validated copy-back/restore of new state, not a switch to stale NFS data.

The user-selected Proxmox node may host isolated test VMs; it is no longer
excluded solely because it also runs production. Settle the lab resource
envelope before starting VMs. Production NAS changes, fault injection against
production resources and host reboots remain outside the scope. Temporary
worker RAM changes follow the separately reviewed arrangement. The isolated lab
does not authorize production storage migration.
