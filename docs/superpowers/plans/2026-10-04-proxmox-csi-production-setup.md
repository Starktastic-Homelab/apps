# Proxmox CSI production shared setup

Status: proposed for approval; read-only preflight completed on 2026-10-04 at
20:59 UTC. No production allocation or activation has run.

**Goal:** Prepare persistent NAS storage and scoped CSI API access before the
coordinated worker-replacement and Jellyfin migration window.

**Architecture:** Use the already qualified manual Ansible shared-storage role
from VM300. Keep the storage, resource pool, reserved image owner and credential
record outside disposable cluster Terraform state.

**Tech stack:** TrueNAS 25.10.7, PVE 9.2.20, NFS4.2; merged Ansible
`913941f2610681d048587f30b0984453c7b768af`. Later controller activation retains
upstream driver v0.20.0/chart0.5.10.

**References:** [accepted architecture](../specs/2026-10-03-portable-iscsi-native-lifecycle-proposal.md),
[shared integration](2026-10-03-proxmox-csi-shared-integration.md), and
[completed integration results](../reports/2026-10-04-proxmox-csi-rebuild-results.md).
Execute inline using `superpowers:executing-plans` after approval.

## Why shared setup comes first

The first transition to `rebuild_workers_with_control_plane=true` replaces both
existing workers to establish their persisted control-plane marker. Jellyfin's
current Git declaration requires worker-01 generation
`8b2aa6c7-b54f-4323-9900-bdbb85098f62` and Node UID
`ed4cb64c-0c87-414e-9538-110650ba2f34`. Fresh workers cannot satisfy that release
gate. Rebuilding now would require re-enrolling the old iSCSI arrangement and
reviewing a new writer release before the later migration replaces it.

Prepare shared infrastructure now; coordinate the first worker replacement with
the separately reviewed Jellyfin migration. CSI installation, pool enrollment,
topology/retirement enablement and cohort-policy activation remain pending until
that rollout is concretely reviewed. No CSI-backed service may be released before
the cohort and retirement safeguards are active and verified.

## Exact proposed allocation

| Resource | Proposed setting |
| --- | --- |
| NAS dataset | `apps/k3s-block`, mount `/mnt/apps/k3s-block` |
| Capacity | Initial **128GiB aggregate quota**, no reservation; quota can later be raised independently of individual PVC sizes |
| Dataset properties | Inherit encryption and LZ4 compression; `sync=STANDARD`, POSIX permissions, root ownership; no parent property changes |
| NFS export | Only `/mnt/apps/k3s-block`, read/write, source `10.9.9.20/32`, maproot user/group `root`; existing NFS4.2 service |
| PVE storage | `k3s-block`, server `10.9.9.30`, images only, node `pve`, options `vers=4.2` |
| Persistent pool | `k3s-csi`, initially empty; later restricted to k3s VMs200–202 |
| External image owner | Reserve unused9999 in the pool comment; **do not create VM/container9999** |
| Runtime identity | Separated `kubernetes-csi@pve!retained`, role `HomelabCSI` |
| Role privileges | `Datastore.Allocate`, `Datastore.AllocateSpace`, `Datastore.Audit`, `VM.Audit`, `VM.Config.Disk` |
| ACLs for user and token | `/pool/k3s-csi` inherited; `/storage/k3s-block` and `/vms/9999` non-inherited |
| Persistent credential | VM300 `/var/lib/homelab-maintenance/private/proxmox-csi.json`, mode0600; container path `/maintenance/private/proxmox-csi.json` |
| Operation history | VM300 `/var/lib/homelab-maintenance/operations/csi-production-setup-20261004/` |

The quota is a pool-space ceiling, not a 128GiB reservation or a per-service
capacity limit. No service image, PV, PVC or synthetic workload is allocated in
this step. No production VM enters the new resource pool yet, so its inherited
runtime grants cover no current VM.

## Fresh read-only observations

- PR1290 merged as `cdcc3469e6e735d793dc8e1851f3a45cd1b46fb9`; its Refresh ArgoCD
  workflow passed. The CSI descriptor remains disabled.
- The proposed dataset/export, storage, pool, owner9999, CSI user/role/ACLs and
  external credential record are absent.
- NAS apps pool GUID `9917900421692286909` is ONLINE and healthy; the parent is
  encrypted and unlocked, with about257GiB dataset-available space. Existing
  shares are unchanged; NFS is running. No recursive apps ancestor snapshot or
  replication task was returned. This setup does not establish a data backup.
- VM300 identity matches `cc1aeeb7-4827-466c-9d4b-5dc6c881f193`; no maintenance
  operation is held. Its private directory is owner-only mode2700.
- Current PVE VM201 UUID matches Jellyfin's Git generation. VM200, VM202 and
  VM300 identities were recorded; no current config lock was returned.
- PVE's on-disk node certificate includes IP10.9.9.20 and expires2027-06-14.
  Verify the certificate actually served on port8006 and its CA before token
  use; inspecting this file alone does not establish endpoint trust.

Sanitized local observations are in
`/tmp/proxmox-csi-production-scope-20261004/{pve,nas,runner}.json`. Repeat identity,
space, collision and maintenance checks immediately before execution.

## Execution and credential scope

- [ ] Revalidate source pins and preflight, then acquire the existing VM300
  maintenance operation. Hold ownership through setup, verification and removal
  of temporary credentials. Never take over an unrelated operation.
- [ ] Record current production VM configurations, exports and NFS state. Create
  only the dataset and export above through the existing authenticated NAS route
  on VM300. Preserve dataset GUID/share ID receipts. Use a supported export reload;
  stop if a disruptive global NFS restart is required.
- [ ] Use a temporary nonprivileged setup container on VM300, pinned to the
  qualified image `python@sha256:cd8244b7983b30cac72c85fa63c43672f1ce193c784c217fb5611f5753b60ce8`.
  Install dependencies inside that container only. Run the exact merged manual
  `proxmox-csi-storage.yml` with an explicit single-host inventory and the values
  above; no cluster playbook or workflow dispatch.
- [ ] The proposed authorization includes temporary transfer of the existing
  login in `/tmp/proxmox_pass.txt` over verified SSH to a root-only inventory under
  the operation's `shared-setup/` directory on VM300. Only the setup container may
  consume it. That temporary container has administrator access to Proxmox during
  setup. Remove this copy and the container immediately after setup; preserve the
  original user file. No administrator credential goes to a k3s guest or Git.
- [ ] Retain only the generated scoped CSI token in the protected external
  record. Read the public PVE CA over the authenticated management connection and
  verify the live API's certificate. Authenticate the generated token with TLS
  verification; inspect effective user/token privileges and read-only denial for
  unrelated VMs. Do not perform negative-test writes or change existing API users.
- [ ] Run setup again: require zero resource changes and the same token. Confirm
  storage/export identity and availability, the empty pool and unused owner9999.
  Verify production VM configurations and existing exports remain unchanged.
- [ ] Remove temporary source/admin files and tooling; retain protected receipts
  and the scoped credential. Release ownership after successful reconciliation.
  Deliver sanitized results and persistent setup settings through a documentation
  PR; never publish secret values.

An unexpected existing object, uncertain ownership, failed credential persistence
or validation failure retains the maintenance operation for reconciliation.
Never rotate a token silently or delete an object merely because its name matches.
Rollback before any use may remove only this operation's recorded empty resources;
once data exists, removal needs a separately reviewed retention decision.

## Later activation window

This approval does not cover worker replacement, k3s restarts, CSI activation,
production synthetic writes or application migration. Before that window, prepare
the coordinated migration procedure and PRs, including:

1. Trusted API CA and complete read-only Proxmox visibility for Ansible retirement;
   enable verified retirement before replacements and native CSI topology before
   controller release. Do not give the CSI runtime token retirement audit powers.
2. Recoverable sealed CSI configuration using the existing sealing-key path and
   `scripts/seal.sh`; confirm decryption with the external bootstrap key and keep
   the driver unmodified. Use matching region `homelab`, owner9999 and storage
   `k3s-block`, with TLS verification.
3. Exact Terraform plan for pool membership and initial cohort-marker activation;
   account for both worker replacements, old-writer exclusion and Jellyfin's
   current generation gates. Preserve original drain/dispatch payloads.
4. Cold application-data migration and rollback, final static retained bindings,
   native controller activation, data/health acceptance and writer release.
   Existing iSCSI guards stay in place until their replacement is verified.

The accepted normal merge/rebuild flow remains the target. No Velero check or
fresh-metadata-backup gate is added. Existing exceptional failure recovery limits
from the qualification report still apply.
