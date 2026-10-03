# Proxmox CSI Shared Integration Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for inline execution. Preserve completed qualification evidence; do not recreate a lab or activate production solely to repeat those tests.

**Goal:** Keep NAS data and Apps bindings outside disposable k3s VMs, with unmodified Proxmox CSI handling attachment and growth and no Velero pre-merge gate.

**Architecture:** Apps owns retained PV/PVC declarations. Shared platform setup owns the NFS registration, reserved external image-owner identity and CSI API access. Terraform owns boot/cloud-init disks; CSI owns SCSI attachments. Preserve the existing maintenance lock and Packer → Terraform → Ansible → ArgoCD handoff.

**Tech Stack:** Telmate3.0.2-rc10, Proxmox CSI v0.20.0/chart0.5.10, k3s v1.37.0+k3s1, TrueNAS25 NFS4.2, ext4/cache-none.

**Spec:** [accepted architecture](../specs/2026-10-03-portable-iscsi-native-lifecycle-proposal.md).

## Accepted decision and constraints

The user accepted stock Proxmox CSI and manual workload restaging after the tested export-withdrawal fault. Both qualified backends completed two rebuilds. The production integration is authorized; production storage allocation/activation and Jellyfin migration remain separate reviewed changes.

- Apps is the sole per-volume inventory; no duplicated service inventory in Ansible.
- No driver fork, adoption controller, Velero dependency or change to the user's routine PR merge procedure.
- Keep old-writer exclusion. Fresh Kubernetes metadata does not prove old VMs stopped.
- Do not remove existing iSCSI writer safeguards during shared preparation.
- Workstation work is source editing, offline checks and transport; runtime qualification uses disposable VMs.
- Existing Ansible checkout has a local `scripts/get-kubeconfig.sh` edit; leave it untouched.

## Delivery order

### 1. Terraform SCSI ownership prerequisite

Files: `terraform/modules/vm/main.tf`, `terraform/README.md`.

Consumes: existing virtio0 boot and ide2 cloud-init layout, `virtio-scsi-pci`, pinned provider3.0.2-rc10.
Produces: `lifecycle.ignore_changes` includes only `disks[0].scsi` alongside the existing `startup_shutdown` exclusion. No VM IDs, resources, disks, workflow modes or provider versions are added or changed.

- [x] Verify the qualified lab ownership rule and current upstream main module.
- [x] Add the SCSI exclusion and document its ownership/deletion limits.
- [x] Validate source, open a PR and inspect its normal read-only provider plan.
- [ ] Stop at the merge gate; no apply or workflow dispatch by the agent.

Relevant evidence is [TrueNAS results](../reports/2026-10-03-proxmox-csi-truenas-results.md), including real provider no-op/update/rebuild tests. Do not add a string-matching test for one HCL field. The actual CI plan must show no unintended replacement or disk deletion.

### 2. Shared bootstrap and replacement ordering

Use current `ansible/k3s.yml`, `roles/k3s_common`, dynamic Proxmox inventory and shared host configuration. Supply native region/zone labels and standard guest filesystem prerequisites. Register a dedicated NFS storage and reserve its external owner outside disposable Terraform state; scope CSI API permissions and preserve credential recovery through existing secret infrastructure. Do not allocate service images from Ansible inventory.

Review `terraform/scripts/maintenance_apply.py` and `ansible/.github/workflows/deploy.yml` together. Current destroy mode completes destruction before apply and retains ownership on failure. Ansible is dispatched only after successful apply/release. New Packer guests must not start a fresh storage controller before previous writers are excluded. Partial control-plane replacement with surviving workers needs explicit coverage before activation; the full-destroy lab alone does not qualify it.

Prepare separate source PRs and a concrete production setup scope. No setup playbook runs or secret publication precedes that scope. Reuse native lifecycle handling and the existing maintenance coordination before introducing new helpers.

### 3. Apps controller and retained binding integration

Use the existing foundation ApplicationSet and upstream chart, with a recoverable existing config Secret. Do not create an active app with missing credentials or point it at lab resources. Preserve NFS defaults for existing services. Keep explicit Retain PV, prebound PVC, stable external handle and native failed-node holds for participating block-backed services.

For growth, avoid setting PV capacity ahead of real disk expansion. Qualify the chosen GitOps PVC-first sequence and subsequent fresh-cluster reconstruction before documenting a one-edit workflow. The test used PVC growth first and reconciled PV/PVC capacity after successful expansion.

### 4. Activation and migration

Only after shared PRs, provider plans and setup evidence are reviewed: activate the stock driver against the dedicated production storage. Qualify the integrated pipeline on synthetic data before any Jellyfin migration. Application data transfer, writer release, CHAP/iSCSI retirement and downtime are distinct migration work.

## Review focus

- Ignore only SCSI: boot/cloud-init drift must remain visible; forbid Terraform-managed SCSI disks in this module.
- Separate image ownership survives worker deletion; never reuse the reserved owner as a disposable VM.
- Interrupted apply or partial control-plane replacement cannot introduce a second writer.
- ArgoCD must not report PV growth before the backend/native resizer performed it.
- Export withdrawal may need manual detach/restage; no arbitrary NAS-failure or power-loss guarantee.

## Execution record

Source baselines: Terraform `5058200`, Ansible `59a2813`, Apps `cbe26e7`. The first implementation is intentionally the independently mergeable Terraform ownership prerequisite. All subsequent activation gates remain in place.


Terraform prerequisite: [PR226](https://github.com/Starktastic-Homelab/terraform/pull/226), commit `a372a5e`.
Terraform1.16.5 `fmt -check` and provider schema validation passed with backend disabled and placeholder API settings.
The normal PR workflow validated against the real provider/backend and reported **No changes** for VMs200/201/202;
maintenance tests passed. An independent read-only code review found no findings. The reviewer did not access live
state; the executor read the PR's actual provider plan. The lab's runtime evidence is retained separately and was not
reproduced for this one-field prerequisite. Later bootstrap, fencing, resize and activation work is not implied complete.

No additional runtime test or string-matching HCL test was introduced: the exact ownership behavior already has real
provider/lab evidence, and this PR's provider plan verifies its current production impact without applying it.

Shared prerequisites merged: Ansible276/277/278 and Terraform227/228/229 add
opt-in node preparation, durable whole-cohort replacement policy, post-bootstrap
drain recovery, manual shared storage/API setup and native pool membership.
The post-merge Ansible278 deployment and Terraform229 apply both passed. Storage
setup remains manual and unexecuted; the replacement policy and pool defaults
remain inactive.

Task 3 source preparation stages the stock chart outside discovery at
`infrastructure/system/proxmox-csi/app.yaml.disabled`, with an external Secret
reference and a nondefault Retain class. CI renders the real chart with globals
and local values. No service binding or credential is published. This is partial
integration: external secret recovery, ArgoCD ordering, interrupted replacement,
and PVC-first growth followed by fresh-cluster reconstruction still require an
approved disposable integrated qualification before activation.
