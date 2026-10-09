# Filebrowser Retained CSI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Prepare reviewed, staged Filebrowser changes that preserve private state
through ordinary cluster replacement, without starting a live migration.

**Architecture:** Reuse Jellyfin's static retained ext4/RWOP CSI binding under
external owner9999. Preserve the old local claim, hold Filebrowser through backup
and restore, then release one worker-resident writer against the populated target.

**Tech Stack:** ArgoCD, bjw-s app-template 5.2.1, Helm, Kubernetes native admission,
stock Proxmox CSI v0.20.0/chart 0.5.10, ext4, existing maintenance runner.

**Spec:** [Approved design](../specs/2026-10-07-filebrowser-retained-csi-design.md).

## Global Constraints

- Target capacity 4Gi; handle `homelab//k3s-block/9999/vm-9999-filebrowser.raw`.
- Preserve current main's image: `gtstef/filebrowser:1.5.8-stable@sha256:68455d4953bad8e984e1bc5d112ed1e9c918a0a04f104c13c9ece50790308894`
  (updated independently in PR #1316 before protection merged).
- Keep the existing ConfigMap, Secret reference, OIDC, ingress and NAS mounts.
- One replica/Recreate in final state, worker placement, indefinite NoExecute holds.
- Retain/RWOP with bidirectional prebinding; both new objects prune/delete protected.
- No live allocation, credential transfers, writer hold, data copy, restore, VM
  creation or cutover under preparation approval. No source deletion or quota change.
- Existing control-plane whole-cohort replacement and verified retirement remain.
- Implement in this already-isolated worktree; user owns PR merges. Use native
  execution for preparation and independent review before PR delivery.

## Review Focus

- Merging preparation must not stop Filebrowser or allocate/attach storage.
- Old source must remain guarded after release; stale Git reverts cannot reopen it.
- Maintenance must be zero replicas; release must bind only the verified target.
- Source protection must not patch immutable local-PVC fields or prune the source.
- Shared value cascade must preserve image/authentication and both NAS mounts.

## Task 1: Safe preparation PR

**Files:** Approved spec and sanitized preflight receipt; this plan;
`docs/runbooks/filebrowser-storage.md`;
`services/operations/filebrowser/manifests/templates/data-pvc.yaml`.

**Interfaces:** Input is current main plus accepted spec; output is a safe-to-review
protection PR with source-claim annotations and no change to current writers.

- [x] Add `Prune=false,Delete=false` to the existing local PVC only.
- [x] Write the runbook with exact stage order, identities, operation gates,
  acceptance, recovery and rollback boundaries. Do not claim unused old lab resources
  are available or export authentication material.
- [x] Render baseline and preparation with actual value layers; assert the only
  live-object difference is the source PVC's protection annotation.
- [x] Run relevant formatting/JSON/YAML and schema checks, then commit the first PR.

## Task 2: Draft maintenance/binding PR stacked on preparation

**Files:** `infrastructure/base-configs/templates/filebrowser-block-storage/{pv,pvc}.yaml`;
`services/operations/filebrowser/manifests/templates/storage-hold.yaml`;
`services/operations/filebrowser/values.yaml`.

**Interfaces:** Consumes protected source and approved destination identities;
produces the held application and declared destination, without releasing a writer.

- [x] Add static 4Gi ext4/cache-none PV and RWOP PVC mirroring Jellyfin's explicit
  retention, topology, prebinding and Argo protections.
- [x] Add one native policy/binding denying Pod use of `filebrowser-data-pvc` in
  namespace `operations`; no exemptions and no effect on unrelated namespaces.
  Protect both policy and binding with Prune=false,Delete=false so stale Git reverts
  cannot remove the guard.
- [x] Set `controllers.main.replicas: 0`; retain the old data claim during hold.
- [x] Render and verify zero replicas, exact binding/attributes, source protection
  and guard scope; validate the policy schema and preserved auth/NFS mounts.
- [x] Commit/open as draft. Merge only for a separately approved maintenance window
  after source preflight and with a verified independent-backup/restore capability.

## Task 3: Draft writer-release PR stacked on maintenance

**Files:** `services/operations/filebrowser/values.yaml`.

**Interfaces:** Consumes accepted cold-copy/restore/target receipt; produces one
writer on a CSI worker while maintaining old-source exclusion.

- [ ] Set replicas1, data existingClaim `filebrowser-data-block`, worker nodeSelector,
  and indefinite not-ready/unreachable NoExecute tolerations. Keep Recreate.
- [ ] Render all three stages and compare; assert only expected volume/placement/
  replica changes, unchanged image/env references/NFS claims, and retained source guard.
- [ ] Test the guard's positive/negative Pod cases through a disposable native API
  during the approved rehearsal. Local schema/render verification is preparation
  evidence only; admission execution remains pending until that rehearsal.
- [ ] Commit/open as draft. Do not merge before verified target helper termination,
  independent restore, image/filesystem identity and data-manifest comparison.

## Task 4: Review, delivery and separately approved execution

**Files:** PR descriptions and operation receipts; no automatic execution workflow.

**Interfaces:** Preparation outputs three reviewed commits/PRs. Runtime consumes
approved exact identities/resource budget, merged stage changes, private backups
and accepted data receipts; it is a separate authorization.

- [ ] Request an independent whole-change review, repair material findings and rerun
  affected checks. Explicitly report native admission/recovery checks still pending.
- [ ] Push/open the three PRs, attach them to this chat and document dependency/merge
  order. Only the protection PR is initially ready for user merge; other PRs are drafts.
- [ ] Inspect current maintenance transport and disposable-host capacity before
  requesting execution. Prepare an exact operation manifest and validated backup
  transport, encrypted off-NAS destination, restore guest and helper commands.
- [ ] Request a bounded operation approval identifying Filebrowser outage,
  source-PV Retain mutation, new 4Gi image, helper/guest resources, data transfers,
  and scratch-path acceptance. Do not interpret PR approval as credential-transfer
  approval or as permission to replace production VMs.
- [ ] Execute the approved design's cold backup, independent restore and target
  population gates; record results and stop on uncertainty.
- [ ] After release, verify OIDC and state, both NAS sources, clean Pod recreation
  and healthy-worker movement. Retain source/backup; clean up lab-owned objects only.

This task separates delivered preparation from unperformed runtime qualification.
No normal rebuild needs to execute this migration plan again.
