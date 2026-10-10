# CloudNativePG retained rebuild qualification implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Determine whether stock CloudNativePG can automate service enrollment and
preserve the homelab's unattended retained-disk rebuild contract before migration step 3.

**Architecture:** One CNPG PostgreSQL instance on a dedicated retained Proxmox CSI
image in a disposable three-node k3s cluster. A fourth VM retains lab Git, sealed
credentials, Terraform state and acknowledged-write evidence across rebuilds.
Use synthetic data and isolated identities; production PostgreSQL remains running.

**Tech stack:** CNPG1.30.1, PostgreSQL18.6-system-trixie, k3s v1.37.0+k3s1,
Proxmox CSI v0.20.0/chart0.5.10, ArgoCD chart10.9.2, Sealed Secrets,
Terraform1.16.5/Telmate3.0.2-rc10, TrueNAS25/NFS4.2, ext4/cache-none.

**Spec:** [approved research direction](../reports/2026-10-10-postgresql-deployment-enrollment-research.md)
and [proposed migration workflow](../specs/2026-10-10-live-storage-migrations-design.md).

**Prepared inputs:** [established-state manifests](fixtures/cnpg-established.yaml.example)
are reviewable lab-only declarations; they require accepted existing PGDATA and
generated lab SealedSecrets before use. Never apply them to a blank image.

Status: the user approved CNPG qualification with the enrollment-Job fallback.
This document defines the new allocation and credential-transfer scope for review;
no lab has been allocated. Native execution continues in this session after that
scope is authorized. No production adoption or migration is authorized by the lab.

## Global constraints

- Keep one shared PostgreSQL instance with separate application databases and restricted roles.
- Use unmodified CNPG and Proxmox CSI; no custom recovery controller or upstream fork.
- Ordinary complete rebuilds must reuse current data without Velero, a manual backup checkpoint or recovery intervention.
- Verify old VM generations are gone before releasing any replacement writer.
- Preserve static Git PV/PVC prebinding, Retain, RWOP, ext4/cache-none and indefinite failed-node holds.
- Generate canonical lab passwords once, seal them, and recover the same values across rebuilds.
- CNPG1.30 lists Kubernetes1.37 as tested but unsupported: lab qualification is allowed; production compatibility remains a decision gate.
- Never initialize the production Terraform backend or bootstrap production Apps, VIP, certificates or secrets into the lab.

## Review focus

- A late/mislabelled PVC must not turn retained data into a fresh empty database.
- Operator interruption after Initialized status but before PVC ownership must recover without manual repair.
- Argo reconciliation must preserve CNPG ownership while recreating ownerless recovery declarations after metadata loss.
- Lost SQL-role CR status must not generate replacement identities/passwords or revoke needed memberships.
- A NotReady writer, missing image or incomplete replacement must stop recovery rather than authorize a second writer.

## Exact disposable scope

| Resource | Proposed allocation |
|---|---|
| VM980 `cnpg-lab-runner` | 2vCPU,2GiB RAM,8GiB root; outside cluster Terraform destroy scope |
| VM981 `cnpg-lab-master-01` | 2vCPU,2GiB RAM,8GiB root; control plane |
| VM982/983 `cnpg-lab-worker-01/02` | Each2vCPU,2GiB RAM,8GiB root; CSI workers |
| Template900 | Clone-only source; no template writes |
| NAS dataset | `apps/cnpg-qualification-20261010`, quota8GiB, no reservation, sync STANDARD |
| NAS export | `/mnt/apps/cnpg-qualification-20261010`, Proxmox10.9.9.20/32 only, NFS4.2/root mapping |
| Proxmox storage/pool | Both named `cnpg-qualification-20261010`; only lab images/VMs |
| Image owner | Reserved9980, never a VM/container |
| Primary image | `images/9980/vm-9980-cnpg-primary.raw`, initially2GiB; growth test to4GiB |
| Restore image | `images/9980/vm-9980-cnpg-restore.raw`, at most2GiB; isolated restore only |
| Operation records | VM300 `/var/lib/homelab-maintenance/operations/cnpg-qualification-20261010/` |

Ceiling:8vCPU,8GiB RAM,32GiB roots plus cloud-init disks, one temporary4GiB
template clone during disk movement, and at most6GiB synthetic data images under
the separate8GiB NAS quota. Require70GiB free on vm-pool before allocation and
at least2GiB host MemAvailable after each staged start; stop lab guests if that
floor cannot be maintained. Do not change production RAM, ARC or NAS quotas.

Use DHCP on vmbr0, no production VIP advertisement, passthrough or boot-on-host-start.
If the unchanged VM module requests boot-on-host-start, explicitly clear it on the
lab guests and disclose this lab-only adaptation. Confirm guest UUID/MAC/address
and SSH host keys before execution. Keep all destructive commands on lab targets.

Before allocation, refresh pool GUID9917900421692286909, ONLINE/unlocked state,
dataset/export absence, inherited encryption and recursive snapshot/replication
rules. Record the new dataset GUID/share ID. Use a supported non-disruptive export
reload; stop if global NFS restart would be required. No existing export edits.

## Credentials and privilege boundaries

Create these absent temporary users, separated `lab` tokens and unique roles;
apply grants to both user and token. No production VM write grants, production CSI
dataset write grants or root administrator login enter VM980, lab workers or containers.
Terraform's required allocation permissions on shared local-zfs/vm-pool storage
are not a per-file sandbox; commands remain restricted to recorded lab disks.

| Identity | Effective scope |
|---|---|
| `cnpg-qualification-csi@pve!lab` / `CNPGQualificationCSI` | VM.Audit,VM.Config.Disk,Datastore.Allocate,Datastore.AllocateSpace,Datastore.Audit on lab pool(inherited),lab storage and owner9980 only |
| `cnpg-qualification-tf@pve!lab` / `CNPGQualificationTF` | VM.Allocate,VM.Audit,VM.Config.CDROM,VM.Config.CPU,VM.Config.Cloudinit,VM.Config.Disk,VM.Config.HWType,VM.Config.Memory,VM.Config.Network,VM.Config.Options,VM.PowerMgmt on981–983 and lab pool; clone-only template900, local-zfs/vm-pool allocation, vmbr0 use, read-only node/storage/owner discovery |
| `cnpg-qualification-audit@pve!lab` / `CNPGQualificationAudit` | VM.Audit on/vms(inherited),Pool.Audit on/pool(inherited),Sys.Audit on/access(non-inherited), for complete retirement visibility |

Terraform additionally needs non-inherited Sys.Audit at `/` for Telmate's HA
discovery, as established in the previous lab. This exposes read-only metadata;
it supplies no production VM write rights. Verify effective permissions and deny
checks before use; insufficiency is a stop, not permission to broaden grants.

Use the existing administrator login over verified Proxmox SSH only to create
the bounded infrastructure/access objects and clone VM980. NAS management uses
the established verified VM100 guest-agent route. No administrator-login transfer
or VM300 setup container is required. The merged storage role is excluded because
its hardcoded production principal cannot safely serve this lab.

Transfer generated lab tokens privately from Proxmox to root-only VM300 operation
files, then to VM980 `/root/cnpg-qualification/private/` (0700; files0600).
CSI's token is sealed into lab Git and recovered only into the lab CSI namespace;
Terraform/audit tokens stay on the lab runner. Lab passwords, SSH private key and
sealing key originate outside981–983 and remain root-only on980/VM300 during the run.
Never export secret values, connection strings, Terraform state, plans or private
keys in public evidence. Delete generated token/key copies after cleanup; preserve
the user's persistent login files and all prior operation evidence.

## Verified preparation and files

Read-only preflight found IDs980–983/9980 absent, proposed storage/pool/dataset and
temporary identity names absent, maintenance ownership idle, about136GiB vm-pool
free and7.7GiB host available RAM. The live PostgreSQL Pod reports18.6 binaries
and PG_VERSION18; a SQL server-version query is still required before cutover.
These are observations on October10, not reservations or final mutation checks.

Source pins: Apps6db9609a96c7c60030f64e5172333ef64fa46cd1,
Ansible6d520867695f8d9b3071dec2ef53938abf808e04,
Terraform3331a4f058ae7ae7a4e8f70a060d60f9ecf39a4b,
CNPG2a35abb4628f209d149825ef3c38011e0701ff2f.
[Artifact pins and sanitized preflight](../reports/evidence/2026-10-10-cnpg-qualification-preparation.json)
record registry-verified image digests and upstream manifest hash.

Prepare public lab inputs outside application discovery under
`.superpowers/sdd/2026-10-10-cnpg-qualification/`:

- `scope.json`: exact resources, source/artifact pins, accepted ceilings and approval receipt.
- `terraform/`: backend-free local-state root using the pinned VM module for981–983, no GPU mappings.
- `inventory.yml`: exact lab hosts, single-interface overrides, explicit pool/region and retirement token references.
- `git/`: isolated Git repository with foundation, storage, CNPG and synthetic-client Applications only.
- `receipts/`: sanitized identity, acknowledgment, acceptance and cleanup records.

The primary uses `databases/cnpg-lab-1` and PV `cnpg-lab-data`; clients use
`cnpg-lab-clients`. The import/restore target uses namespace `cnpg-lab-restore`,
Cluster `cnpg-lab-restore` and a separate static claim/image. A synthetic source
uses local-path on a disposable worker root in namespace `cnpg-lab-source`.
Bootstrap fixtures and backup helpers therefore cannot be mistaken for the primary.

Private files never enter these public inputs. Runtime Terraform state and tools
live on980. Record lab wrappers/adaptations separately from unchanged module/helper
source; do not claim real GitHub Actions dispatch or production bootstrap coverage.

## Task 1: Prepare isolation and allocate

- [ ] Resolve/hash tooling and manifests, validate the backend-free Terraform root,
  inspect every Ansible target/delegation and create the exact public inputs above.
- [ ] Acquire the existing real maintenance operation before any mutation; hold it
  throughout allocation, tests and cleanup. Use its execution exclusion around
  each phase. Never steal a held operation; retain ownership on uncertainty.
- [ ] Refresh collisions/capacity, create bounded storage/access/VM980, and prove
  token denials on production VM changes and production CSI storage writes.
- [ ] Run native Terraform and Ansible on980 using a separate lab maintenance root.
  Inspect saved plans: only981–983. Skip production bootstrap and kube-vip;
  retain CSI topology, cohort replacement, retirement and drain-recovery tasks.
- [ ] Bootstrap lab Argo/Sealed Secrets/CSI with a generated external sealing key,
  strict Proxmox certificate trust, lab region and restored configuration. Prove
  no production App discovery, credentials or endpoint advertisements.
- [ ] Have trusted lab bootstrap verify current Proxmox UUID/Node systemUUID and
  old-generation retirement before applying the NodeRestriction-protected
  `node-restriction.kubernetes.io/cnpg-lab-approved=true` label. Verify the API
  forbids a kubelet from self-assigning it. Reapply this gate automatically on
  each rebuild; the manifest's selector is not writer-fencing proof by itself.

## Task 2: Establish synthetic PostgreSQL and enrollment

- [ ] Allocate the explicitly approved blank2GiB primary image, record its identity,
  and bind a static Retain/RWOP PV to `databases/cnpg-lab-1`. Let first CNPG
  bootstrap create that claim through its matching pvcTemplate and initialize once.
- [ ] Run CNPG `cnpg-lab`, instances1, PostgreSQL18.6 digest pinned, no dynamic
  claim fallback, worker generation affinity and indefinite failed-node tolerations.
  Record generated Pod/Job settings, filesystem UUID and PostgreSQL system identifier.
- [ ] Add `app_alpha` and `app_beta` roles/databases through DatabaseRole/Database
  declarations and identical once-generated credentials sealed into database and
  client namespaces. Verify login, ownership, cross-database restrictions and
  explicit retain behavior. Do not claim table isolation from database ownership alone.
- [ ] Exercise a synthetic same-major multi-database monolith import separately
  before the established-state guard, using a disposable source in this lab.
  Compare owners, memberships, extensions and representative records. No production
  database dump or source password is transferred in this qualification.
  Synthetic import qualifies the mechanism, not existing application compatibility;
  actual-data rehearsal and SQL catalog inventory remain production migration gates.
- [ ] Commit permanent lab recovery declarations: exact ownerless `<cluster>-1`
  PVC, CNPG labels/serial1, matching PV claimRef without old UID, sealed credentials
  and independent verified generation placement. Test Argo ownership reconciliation.
- [ ] Generate deterministic SQL rows with synchronous_commit on. Record only
  committed sequence/payload acknowledgments to an fsynced ledger on980.

## Task 3: Qualify startup safeguards and metadata-loss recovery

- [ ] After accepting initial data, establish native ValidatingAdmissionPolicies
  that forbid additional/unbound database claims and CNPG bootstrap Jobs/Job Pods
  for the established cluster. Qualify CREATE/UPDATE paths and policy readiness;
  an absent/mislabelled claim must not cause image allocation or initialization.
  Guards are Git foundation resources restored before Cluster reconciliation.
- [ ] Restore PVC metadata before creating a fresh CNPG Cluster; verify its exact
  name, serial, labels, ownerlessness and binding. Do not use a CNPG fencing
  annotation as the startup barrier: adoption clears that annotation.
- [ ] Destroy/apply all981–983 twice through the real VM module and maintenance
  helper, once with ongoing acknowledged writes. Verify every old generation is
  absent before bootstrap. Recreate only from lab Git, external keys/tokens and
  the retained image; no Kubernetes exports/status backups or last-minute dumps.
- [ ] Require new namespace/Cluster UIDs, same disk/filesystem/system identifier,
  all acknowledged rows and unchanged working app credentials. Healthy alone fails.
- [ ] Inject late/missing PVC, missing serial, invalid serial, stale owner reference,
  wrong image identity, missing image and invalid PGDATA on disposable cases.
  Restore the baseline disk between destructive cases. No empty initialization,
  extra claim, dynamic image or writable replacement is acceptable.
- [ ] Inject a temporary native admission policy denying the exact ownerless PVC's
  first ownerReferences assignment. Observe Initialized=True while ownership stays
  absent, restart the operator, then remove only the owned fault binding. Require
  recovery without manually fixing status/ownership. This exercises the real PATCH
  boundary with stock CNPG; an arbitrary restart that misses it does not count.
- [ ] Interrupt cohort replacement while an old worker survives; prove bootstrap
  remains blocked until verified retirement. Never force-remove CSI finalizers.

## Task 4: Remaining lifecycle and recovery cases

- [ ] Recreate/move the primary between healthy workers; verify placement, data
  and exclusive attachment. Replace one worker through verified retirement,
  preserving drain handoff and pre-existing cordons. Exercise default PDB behavior
  and the existing orchestration's eviction policy explicitly.
- [ ] Make an old lab writer unreachable to the API using guest-local isolation;
  verify no second writer. Before any takeover, verify that exact VM is off and
  use the qualified native shutdown recovery path. No host/network-global faults.
- [ ] Request2GiB→4GiB growth, verify backend/filesystem and acknowledged data,
  then reconcile Git PV capacity; prove CNPG ownership does not obstruct expansion.
- [ ] Rebuild enrollment metadata and client Secrets, add another service solely
  through declarations, test retain-on-removal, and coordinate password rotation
  with client restart. Compare existing-role memberships before/after adoption.
- [ ] Export a consistent synthetic logical backup to980's vm-pool-backed root,
  then restore to the separate2GiB image/isolated client endpoint. Compare content
  and authentication; do not expose the restore instance to the primary service.
  This proves a logical off-NAS restore, not CNPG WAL/PITR or host-loss recovery.

## Task 5: Evidence, cleanup and decision

- [ ] Export sanitized commands, source hashes, VM generations, image identities,
  ACK comparisons, admission denials, adoption boundary traces and app checks.
  Report attempted, passed, failed and untested cases separately.
- [ ] Stop/fence writers and confirm native detach. Remove only recorded lab VMs,
  images, registration/pool and temporary users/tokens/roles/ACLs. Verify dataset
  GUID/share ID and absence of unexpected children/snapshots before NAS deletion.
- [ ] Delete generated private copies and temporary staging after reconciliation;
  preserve public evidence and historical records. Release the real maintenance
  operation only when cleanup is verified. Confirm production VM/storage/ACL
  declarations remain unchanged.
- [ ] Write `docs/superpowers/reports/2026-10-10-cnpg-qualification-results.md` and
  sanitized evidence. Recommend production CNPG only if every required gate passes
  and Kubernetes compatibility is resolved; otherwise state the blocking case and
  return to the existing-server enrollment Job. Production adoption needs its own
  concrete reviewed migration plan and approval.

## Stop conditions

Unexpected production targeting, writer overlap, missing acknowledged data,
uncertain generation/identity, lost maintenance ownership or an ambiguous mutation
stops the phase and preserves receipts. Reconcile intent/native state before any
retry. Do not silently add broader permissions, a custom operator, backup freshness
requirements, routine manual recovery or additional allocations to obtain a pass.
