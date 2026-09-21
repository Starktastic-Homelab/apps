# Jellyfin retained-storage pilot: preparation readiness

September 21, 2026. This report covers code preparation, not production qualification.
The approved design and plan remain on the evidence branch in Apps PR #1232.
No production storage, credentials, VM power or application deployment changed.

## Review groups and merge effects

| Group | Change | Effect of merge |
| --- | --- | --- |
| A — Apps NFS durability | Pinned NAS transport, identity/backup checks, durable intent and readback | Adds tools/tests; no automatic NAS update |
| B — Ansible | Persistent VM300 lock, opt-in worker enrollment, scoped fencing role/command | Changes subsequent deployment coordination; runner bootstrap is required first; no implicit token creation or fencing |
| B — Terraform | Shared lock around drain/apply/recovery | Changes subsequent deployment coordination; no Terraform resource settings changed |
| C — Apps platform | Native onboarding/reconciliation, worker verifier, CSI node plugin, generated admission/static bindings | Installs the node plugin on explicitly storage-ready workers; creates no target or app binding by itself |
| D — Apps tools | Cold backup/restore, source reader, stage generation, first-write receipt | Tools only; existing Jellyfin service remains unchanged |
| Source-held — Apps outage artifact | Zero replicas, ingress closed, LDAP suspended, source writer policy | Stops Jellyfin when merged/reconciled; keep draft until the approved outage |

Target-held/released are tested generators, not concrete production commits yet.
Actual native/filesystem IDs, sealed CHAP and a successful independent cold restore
are mandatory inputs. A concrete one-time format/copy command sheet and those two
commits are still required after real onboarding; no placeholder block device or
invented filesystem identity is approved for formatting.

## Design coverage and evidence

| Approved design section | Implementation / test | Required live evidence |
| --- | --- | --- |
| Intent and scope | Stock SQLite/image preserved; layered Jellyfin renders | Playback/catalog/plugin acceptance |
| Read-only findings and NFS durability | `nfs_sync.py`, `nas_rpc.py`; identity, transport, backup and lost-response tests | Fresh NAS GUID/version/policy reads, consistent critical-DB backups/restores, STANDARD readback and latency |
| Storage layout | Native identity verifier; static Retain/RWOP renderer; actual CSI and app chart renders | Returned IDs, clean ext4 UUID/marker, <70% occupied; real per-worker cache/eviction headroom |
| Repository boundaries | Ansible generic worker/fence helpers, Apps service lifecycle, Terraform coordination | Reviewed operator inventory and companion merges |
| Fencing account and qualification | Scoped account role; command tests for identity, pending changes, denial, ambiguous stop and receipts | Real user/token effective rights, protected-VM denials, approved diskless VM stop and cleanup; no production stop test |
| Persistent maintenance coordination | Multiprocess durable lock tests; actual workflow-step fixtures; Terraform executable orchestration | Runner filesystem/marker bootstrap; real container bind mounts, simultaneous workflows, cancellation/resume |
| Initiators and worker generation | Worker-only opt-in role, unique IQN/retirement validation and UID labels | Exact current/retired VM evidence, packages, route, Node UID/SMBIOS labels on both workers |
| Native lifecycle and rebind | Separate onboard/reconcile/verify commands; no create or repair in normal probe | Real target and CHAP, NAS service state, one-time initialization, external record recovery |
| Placement-specific writer authorization | Real disposable Kubernetes CEL tests; protected namespace stamp; exact node affinity; release evidence and bindings | Production RBAC/trust boundary, closed authorization, exact namespace/node/VM generation, clean old session or current exact fence |
| Independent cold backup | Synthetic producer/full-disk/metadata/hash/traversal/WAL/plugin tests; actual reader admission and UID deletion | Scheduled source hold, fresh source snapshot readback, laptop archive, full same-image isolated restore, sealing-key recovery |
| Git-held migration | Actual app-template 5.2.1 renders of all stages; source-held draft | Immutable target stage commits after real IDs/restore; one-time format/copy command review; no writable overlap |
| Rollback | Conservative durable first-release latch and stale-source rejection tests | Fresh latest target backup and new retained NFS rollback binding after any possible target write |
| Delivery and acceptance | Draft-only PRs, merge effects and dependency order | Direct play, hardware transcode, seek, progress writes, one clean move, >=24h observation, explicit iSCSI snapshots and restored independent target backup |

## Local validation

- Apps storage unit/fault tests: 64 passed.
- Actual disposable K3s v1.37.0 API: 24 admission/reader cases passed, including namespace recreation, wrong worker/generation, missing authorization, alias bindings, source writer denial and UID-precondition cleanup.
- Actual democratic-csi 0.15.1 chart: rendered assertions and all seven resource kinds passed server schema dry-run.
- Actual app-template 5.2.1 with globals/common/service layers: source-held, target-held and target-released passed image/probe/GPU/media/cache/placement checks.
- Source-hold raw manifests: kubeconform v0.8.0, six resources valid, none skipped.
- Jellyfin integration compatibility: passed. Existing PostgreSQL backup regression: four passed during implementation.
- Ansible: 76 tests passed with one existing opt-in upstream i915 live check skipped; offline ansible-lint/pre-commit passed.
- Terraform: six workflow/orchestration tests passed with the pinned helper interface. No `.tf` changed; no backend initialization or live state access was performed.

Temporary production credentials/CA files from the earlier investigation are no
longer available in this execution environment. Fresh live NAS/PVE checks and
inventory-backed Ansible execution were therefore not performed. Their absence
cannot be replaced by the synthetic tests above. The existing user-edited
`ansible/scripts/get-kubeconfig.sh` was not changed.

## Dependency and recovery order

Bootstrap and qualify the durable VM300 lock before enabling coordinated deployment
workflows. Publish immutable helper commits first, then review/merge A and B, C,
D in dependency order. Do not merge Source-held until the separate outage window.
Every cross-repository helper checkout is pinned. GitHub branches/PRs do not
waive the fixed runner marker, external owner/nonce or reviewed native records.

On any failed/cancelled/ambiguous operation, retain the lock and intent journals.
The original owner verifies actual state and uses the explicit reconciliation
path; never retry create/format/stop or steal ownership based on age. Ordinary
Terraform/Ansible applies remain blocked while storage maintenance owns the lock.
Manual Proxmox start/recreate must also be prohibited during that period.

The first proposed production change is the separate backed-up NFS `STANDARD`
correction. Before requesting that window: restore current access, qualify the
runner lock, inspect current native identities and produce a fresh reviewed
critical-database backup/restore coverage receipt. Account/test-VM qualification
and the Jellyfin outage remain later scoped operations.
