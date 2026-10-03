# Proxmox CSI integrated qualification scope

Date: 2026-10-04 (Asia/Jerusalem). Status: user approved this bounded allocation, qualification and cleanup scope on 2026-10-04. Directory-mode prerequisite merged as Ansible279; qualification reached a worker-node identity retirement gate. See [partial runtime results](../reports/2026-10-04-proxmox-csi-integrated-results.md). Remaining cases are pending.

**Goal:** Qualify the merged shared setup, replacement ordering, recoverable CSI configuration and ArgoCD retained bindings on synthetic data before production activation.

**Architecture:** Four disposable VMs on the existing Proxmox host: a runner outside the destroy scope and three replaceable k3s nodes. A dedicated TrueNAS sibling dataset retains synthetic images outside cluster Terraform state. Stock CSI and a lab-only GitOps repository reconstruct bindings without Kubernetes backups.

**Tech stack:** Proxmox CSI v0.20.0/chart0.5.10, Terraform1.16.5/Telmate3.0.2-rc10, k3s v1.37.0+k3s1, Helm4.3.0, ArgoCD chart10.9.2, TrueNAS25 NFS4.2, ext4/cache-none. Verify artifacts and record resolved image digests before execution; do not silently substitute versions.

**Spec:** [accepted architecture](../specs/2026-10-03-portable-iscsi-native-lifecycle-proposal.md).
**Prior evidence:** [completed TrueNAS qualification](../reports/2026-10-03-proxmox-csi-truenas-results.md).

## Verified source and preflight

- Apps1288 merged as `180fea486127c0a1c9460fa0ddf9db25261fd867`; its post-merge Refresh ArgoCD workflow succeeded. The staged descriptor remains outside discovery.
- Use merged Ansible `772b5ce3672d8c40ae9de9675786a08695d16216` and Terraform `3b8806422f2cf11a3992f05198619493fa8874e9`. Both post-merge workflows succeeded in the preceding integration step.
- [Fresh read-only Proxmox inventory](../reports/evidence/2026-10-04-proxmox-csi-integrated-preflight.json) confirms PVE9.2.20, no VMs/containers980–983 or9980, no pools, no dedicated NFS registration, and about136GiB free on vm-pool. Template900 remains the inspected Debian13.7 template with a4GiB boot disk on local-zfs.
- The merged setup requires fixed names `kubernetes-csi@pve!retained` and `HomelabCSI`; the user, role and ACL references are currently absent. This run may temporarily create those exact names with lab-only grants, then remove them. It must not adopt an existing identity.
- NAS availability, the proposed new path and host MemAvailable have **not** been refreshed this turn. Prior NAS evidence identifies TrueNAS25.10.7 and apps pool GUID9917900421692286909; repeat all identity/capacity/collision checks immediately before any allocation.

## Exact allocation and allowed side effects

| Resource | Scope |
| --- | --- |
| VM980 `csi-int-runner` | 2GiB RAM, 2vCPU, 8GiB root; tooling and lab Git/state outside cluster destruction |
| VM981 `csi-int-server` | 2GiB RAM, 2vCPU, 8GiB root; disposable k3s control plane |
| VM982/983 `csi-int-worker-1/2` | Each2GiB RAM, 2vCPU, 8GiB root; disposable workers |
| NAS dataset | `apps/csi-integration-20261004`, mount `/mnt/apps/csi-integration-20261004`, quota8GiB, no reservation, sync STANDARD, inherited encryption/compression |
| NFS share | Only that dataset; writable by Proxmox10.9.9.20/32, root mapping for native image allocation; NFS4.2 via10.9.9.30 |
| Proxmox registration | `csi-integration-20261004`, images only, node `pve`; no existing storage edits |
| Proxmox pool | `csi-integration-20261004`, only k3s VMs981–983 |
| External image owner | Unused9980; no VM9980; checked image directory absent before first use |
| Runtime access | `kubernetes-csi@pve!retained`, privilege-separated, role `HomelabCSI`, only lab pool/storage/owner9980 grants from the merged role |
| Provisioning access | Separate temporary `csi-integration-tf@pve` identity/token and role `CSIIntegrationTF`, restricted to allocating/managing VMs981–983 and the necessary template/storage/pool operations; inspect effective permissions before use |
| External secret record | `/maintenance/private/proxmox-csi-integration-20261004.json`,0600; generated lab key material only |

Ceiling:8GiB RAM,8vCPU,32GiB permanent VM roots plus cloud-init disks and at most one temporary4GiB clone on local-zfs while moving it to vm-pool. Require70GiB free on vm-pool before allocation and at least2GiB host MemAvailable after each start; stop lab VMs if this cannot be maintained. Do not alter production memory or ARC settings. Template900 is read-only. No passthrough and no boot-on-host-start.

Use DHCP on vmbr0. Verify each VM generation, MAC, guest-agent address and SSH identity before commands. Set the single lab API endpoint to its verified control-plane address; no production VIP advertisement or network configuration changes. Reconcile the endpoint after replacement. A collision in any ID/name/path aborts instead of adopting the object.

Recheck NAS pool identity/health/unlocked state, free space, dataset/share absence and recursive ancestor snapshot/replication policies. Record the new dataset GUID and NFS share ID. Use a supported export reload; stop if creating/removing the share would require a disruptive global NFS restart. Do not change parent datasets, existing exports or global NFS settings.

## Execution and isolation

Workstation: source preparation and transport only. Run Terraform, Ansible cluster provisioning, Helm, kubectl and workload tests inside VM980/the disposable guests. Never initialize the production Terraform backend or provide production Kubernetes/SSO/sealing credentials to the lab.

VM300 remains the trusted NAS-management and real maintenance-lock coordinator. Verify its existing identity and credential references first. The scope permits a temporary nonprivileged tooling container there, following the existing deployment container pattern, solely to run the merged manual shared-setup playbook against `pve`, with the real maintenance directory mounted and secrets protected. Resolve/pin its image and dependencies before execution; install nothing into the VM300 host and do not modify its runner service. The shared role's localhost delegation therefore stays on VM300, never this workstation. Preserve all historical receipts and ownership records.

Acquire the existing global maintenance operation before the first allocation and hold it continuously until all lab nodes/access/storage have been cleaned up. Lab pool members require the `k3s` tag and could otherwise enter production Ansible inventory; ordinary infrastructure deployments must wait for the entire lab lifetime. A lost/uncertain outer lock stops execution and requires reconciliation before any deployment or writer release. Use a separate lab maintenance root on VM980 for destructive pipeline/failure tests, under that outer ownership. Recheck real ownership before shared mutations. Never copy or clear another operation's ownership. Failure retains ownership until reconciled.

Run the exact merged shared setup with lab settings, then rerun for idempotence and inspect actual effective CSI permissions. If those permissions are insufficient, capture the failed operation; do not broaden them to production resources. The fixed runtime names may be cleaned up only if this run created them. Keep administrative credentials out of VM workers and CSI Secrets.

Use an explicit lab-only inventory and vars; inspect every Ansible target/delegation. The production `bootstrap_cluster` role seeds production secrets, restores certificates and discovers all Apps, so it is excluded from the lab invocation. Run the merged `k3s.yml` installation and drain-recovery sequence with `--skip-tags argocd,kube-vip`, after verifying that the selected task list still includes drain recovery. Apply the native CSI topology reconciliation task separately. Use a lab-only ArgoCD/sealed-secrets bootstrap with generated lab credentials and the same relevant chart pins, multi-source value layering and phased ApplicationSet semantics. Record this adaptation explicitly; do not claim an unchanged production bootstrap or a real GitHub Actions end-to-end deployment was exercised.

VM980 hosts lab Git containing only the selected CSI/sealed-secrets declarations and one synthetic SQLite service. Permit access only from lab peers; no external GitHub repository, production Git write, webhook or production workflow dispatch is required. The lab descriptor is enabled only there and overrides the storage ID. Preserve the production descriptor as disabled. The lab sealing private key and CSI credential record remain outside981–983 and are restored before controllers/services require them.

## Test sequence and acceptance evidence

1. **Shared setup and baseline:** verify setup idempotence without token rotation; effective separated-token permissions and denial outside lab scope. Allocate one2GiB raw image under9980, initialize synthetic ext4 once, record volume handle/filesystem UUID, and declare static Retain/RWOP PV/PVC (`claimRef` without UID, explicit `volumeName`). Argo must reach health with the external configuration, correct topology and native attachment. Record acknowledged deterministic SQLite WAL/synchronous-FULL transactions and integrity.
2. **Independent worker replacement:** use the merged VM module with pool membership and SCSI exclusion. Inspect the real saved plan: only the requested worker replaces. Execute the merged drain orchestration and exact successful drained-node handoff into the merged Ansible recovery. Preserve pre-existing cordons on surviving node objects. Confirm stable image/UUID/data and no simultaneous writable attachment.
3. **Control-plane cohort and failure:** changing only the control-plane incarnation must plan all three replacements. Interrupt after old control-plane removal while an old writer still exists. The failed operation must not dispatch bootstrap or release ownership. Resume the original operation after inspecting state; exclude/confirm stopped every old writer before new service release. Test interruption at the Terraform-success/Ansible-handoff boundary with the original handoff payload, not a newly inferred drain list. Inspect both operations and preserve the known release-before-dispatch limitation.
4. **Fresh metadata reconstruction:** complete whole-cluster destroy/apply twice with surviving external storage/Git/secrets, once with active synthetic writes before confirmed VM power-off. Rebuild Argo and sealed-secrets with the externally retained lab key, recover the same CSI token/handle and all acknowledged records. No last-minute Velero/metadata backup or exported Kubernetes objects may participate.
5. **GitOps growth and interrupted reconstruction:** request PVC2GiB→4GiB without raising Git PV capacity. Observe backend image, controller resize, node filesystem and live PV transitions; then reconcile verified capacity into Git. Deliberately rebuild from fresh metadata at unfinished checkpoints (request committed before expansion, and backend expanded before Git PV reconciliation). Record whether Argo's capacity reconciliation or prebinding blocks recovery. An unresolved case blocks a claim of arbitrary-rebuild safety or a one-edit growth workflow; stop for a design decision rather than silently introducing a custom driver/controller or backup gate.
6. **Boundary checks:** prove healthy pod movement and native failed-node holds with verified-off takeover. Missing-image recovery must not silently allocate a replacement. Prior blank-image/repair and export-withdrawal findings stand; no need to repeat destructive filesystem or NAS-fault experiments to claim this integration coverage.

Capture commands, source/tool hashes, plans, VM generations, attachment transitions, image/UUID identity, acknowledged sequences and SQLite integrity. Scrub literal and encoded generated secrets before exporting evidence. Source/offline tests and attempted runtime steps are not passes. Unexpected image identity, missing acknowledged data, writer overlap, production target selection or uncertain old-VM state stops execution.

## Cleanup and completion

Export sanitized evidence first. Stop lab writers; confirm shutdown/detachment; delete only the current recorded VMs980–983 and their own boot/cloud-init disks, exact synthetic images, temporary storage registration, lab-created tokens/users/roles/ACLs and empty pool. Verify dataset GUID/share ID and absence of unexpected snapshots/children before deleting the dedicated share/dataset. Remove generated lab credentials/container/private staging after cleanup verification; preserve the user-supplied Proxmox file, existing NAS credential references and all historical maintenance evidence. Release the real maintenance operation only after reconciliation.

No production CSI activation, production image allocation, application migration, NFS defaults change, old iSCSI guard removal, NAS reboot, global NFS fault or power-loss test is included. Deliver a results PR with precise runtime coverage and remaining limits; production activation follows a separate concrete review.

## Review focus

- Fixed shared-setup names must remain absent until this run creates them; never adopt or delete pre-existing access objects.
- Lab bootstrap must not discover production Apps, advertise the production VIP or use production secrets.
- Fresh control-plane metadata must not authorize a second writer while old workers survive.
- Git PV capacity must not mask missing backend expansion; interrupted-growth reconstruction needs direct evidence.
- Global maintenance coordination and the lab lock are different scopes; report the GitHub dispatch/production-bootstrap limitation honestly.

## First approved preflight result

The fresh NAS check confirmed TrueNAS25.10.7, the expected healthy apps pool,
absent proposed dataset/share, active NFS and no recursive ancestor snapshot or
replication tasks. Proxmox IDs and fixed CSI names remain free; host MemAvailable
was about5.6GiB before allocation (reclamation still needs observation on start).

The VM300 identity check passed, but the local pre-acquisition guard refused its
private-directory mode `2700`. Inspection confirmed root ownership, no symlink,
and no group/world permissions: the directory inherits setgid from the `2770`
maintenance root. The merged Ansible setup has the same exact-`0700` check.
Its native-Ansible regression now reproduces that refusal. The prerequisite fix
accepts only `0700` or `2700`, without changing live permissions or broadening
read access; unsafe modes, symlinks and non-directories remain rejected.

Resume with the merged correction and recheck identity, available resources and
ownership. Do not reacquire approval for this unchanged lab scope. No lock was
acquired and no allocation/cleanup is pending from this attempt.
