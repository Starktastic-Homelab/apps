# Native PostgreSQL enrollment: remaining disposable lab gate

Status: the separately approved disposable operation completed qualification and
cleanup on 11 October 2026. See the
[qualification record](../../operations/postgresql-enrollment-qualification.md)
for measured results and limits. Production activation or migration remains
unauthorized by this plan. The allocation and transfer requirements below record
the approval boundary used for the completed operation.

## Bind the next operation before approval

Use a new operation identity `pg-enrollment-native-qualification`, separate from
removed CNPG operations. Candidate VM IDs 980–983 are proposals, not reservations;
prove they are free and unrelated on the actual Proxmox cluster before using them.
Fresh evidence must bind Proxmox node/pool/storage identities, resource capacity,
NAS dataset/quota, template 900 source generation, network bridge and IP ownership,
VM300 maintenance runtime hash/receipt/owner, current Terraform and Ansible commits,
and installed k3s, ArgoCD/ApplicationSet, Sealed Secrets and CSI versions.

Proposed maximum topology, subject to that preflight:

| Resource | Budget | Lifetime |
|---|---|---|
| VM980 isolated runner | 1vCPU,2GiB RAM,16GiB local-zfs root | operation only |
| VM981 control plane | 2vCPU,4GiB RAM,20GiB local-zfs root | replaced in rebuild test |
| VM982–983 workers | 2vCPU,4GiB RAM,20GiB local-zfs root each | replaced in rebuild test |
| Synthetic retained PostgreSQL disk | 8GiB on shared vm-pool | survives compute replacement; deleted at cleanup |
| Dedicated lab dataset | aggregate hard quota 64GiB | no production directory or media mount |

Total maximum 7vCPU/14GiB RAM/76GiB local root allocation plus the separate lab
shared-storage cap. Do not silently choose another template, ID, storage or larger
budget if unavailable: update the concrete proposal first. Never import/delete a
production VM, PVC, disk or database. Bind every created resource in the receipt.

Freeze exact chart/image digests and source hashes from the merged engine PR.
Use current Bitnami PostgreSQL server at the existing major 18.6 and the pinned native
client; do not substitute a different image as proof of this implementation.
Use the installed native Argo/Sealed Secrets workflow and existing verified Ansible
Node retirement; no CCM or custom CSI driver. Repository engine tests must pass
before allocation and again against the frozen artifacts.

## Credentials and access proposal

Generate synthetic administrator and app passwords only. Use a lab sealing key
with matching public certificate; do not copy the production private sealing key,
admin password, existing app credentials or PostgreSQL disk. Root-only files and
private streams hold transient inputs; public evidence contains no plaintext,
verifiers, private keys, token IDs/secrets or full connection URLs.

The concrete preflight must list exact temporary Proxmox user/token/roles and ACLs,
which VM generations/template/pool/dataset they may access, and which host-to-host
transfers are required. Administrator login stays on its approved host. A synthetic
lab cluster kubeconfig and temporary least-privilege API tokens may be required
on the lab runner; obtain explicit transfer authorization with source/destination,
file ownership, purpose, validity and deletion plan. Prior CNPG identity/transfer
approval is not reusable. No production API write ACL is required.

## Qualification matrix

1. **Native first installation.** Deploy the synthetic same-major retained server,
   record physical system ID, explicitly bootstrap the ledger once, prepare and
   seal a synthetic canonical pair. Apply the ConfigMap/SealedSecrets/server/Sync
   Job through native Argo full sync. Prove the Job runs after healthy server and
   projected credentials, and canonical writer authentication succeeds. Record
   exact hooks/waves and controller versions.
2. **Hooks and ordering.** Successful hook cleanup, failed-hook evidence retention,
   BeforeHookCreation replacement, bounded failure, full-sync retry and repeated
   same-generation runs. Exercise selective sync and record that it does not run
   the hook. Exercise secret projection delays, wrong app password, corrupt/missing
   registry and wrong system ID; no replacement DB or ready new writer.
3. **Consumer gate.** Include a synthetic service consumer and a synthetic consumer
   in the same controllers rollout group as PostgreSQL. Use an explicit database
   acceptance gate; prove no writer before enrollment completion, including a
   deliberately failed/blocked hook. Force the authentication child to fail after
   ready/LOGIN commits while canonical app login is possible; the writer must still
   wait for successful Job/acceptance completion. Do not rely on same-group RollingSync order.
   Any required new writer-gate source gets its own reviewable PR before use.
4. **Adoption.** Create a synthetic legacy database with data, extension, membership
   and nontrivial grants. Adopt the actual sealed credential without changing its
   verifier/catalog/data. Remove its declaration and verify retention. Wrong owner,
   password and attributes must fail without takeover or rotation.
5. **Full Terraform/Ansible rebuild.** Capture latest acknowledged writer sentinels
   and retained disk/system ID/ledger/credentials. Replace control-plane and all
   workers using the actual handoff/retirement sequence while retaining only the
   synthetic PostgreSQL disk and encrypted Git inputs. Destroy Kubernetes metadata.
   Apply the same normal desired state without re-bootstrap, backup checkpoint,
   manual PV repair or credential generation. Prove unchanged system ID/ledger,
   newest acknowledged rows/passwords and unattended Job success. Confirm old VM
   generations/writers are gone before a new database writer can start.
6. **Absent/wrong retained disk.** Native startup must fail safely before Bitnami
   initialization. Missing registry/Secret/disk, wrong disk/system ID and alternate
   generation are explicit cases. If current server startup cannot prevent an
   empty PGDATA from being initialized, prepare/qualify a separate startup-guard
   change before declaring the rebuild gate passed. Enrollment alone cannot guard
   Bitnami's initialization or unconditional postmaster.pid deletion.
7. **Evidence and cleanup.** Keep sanitized before/after source hashes, physical
   identity, acknowledgment comparisons, Job/Argo results and negative-case outputs.
   Stop on uncertainty without claiming the remaining matrix passed. Remove only
   operation-owned VMs/disks/dataset, temporary identities/ACLs/token copies/sealing
   key/kubeconfig; verify absence and release the exact VM300 maintenance ownership.

## Production boundary

Even a passing lab does not activate production. Present a separate exact scope:
one-time registry bootstrap on the inventoried existing server, inactive-to-active
manifest PR, synthetic production pilot, then individually inventoried legacy
adoption and Autobrr converter rehearsal. Inventory complete memberships,
schema/table/default privileges and current app credential before each adoption.
PostgreSQL NFS-to-CSI migration, cold copy/startup fencing, capacity growth and
independent off-NAS restore remain another plan and approval.
