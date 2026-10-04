# Proxmox CCM assessment and retirement decision

Date: 2026-10-04. Result: use verified Node retirement in Ansible instead of CCM.
The user selected this after reviewing the inventory-visibility limitation below.
CSI remains unmodified. No CCM, credentials or new lab resources were deployed.
Evidence: [release/source identities and installed PVE excerpts](evidence/2026-10-04-proxmox-ccm-assessment.json).

## Released source assessed

- CCM [v0.16.1](https://github.com/sergelogvinov/proxmox-cloud-controller-manager/releases/tag/v0.16.1),
  commit `fd03c86eb3eb3e4090a26bdfca4a24493fa18701`, published 2026-09-28;
  source chart `0.2.32`.
- Its pinned go-proxmox-pool dependency `6bc833630250` and Kubernetes
  cloud-provider `v0.37.0`.
- Installed PVE `9.2.20/49318c671b82f31e`, inspected over read-only SSH.
  `/usr/share/perl5/PVE/API2/Cluster.pm` SHA-256:
  `1296999437390c82a89e56418c2e39fd3579ef5fd35bd6d7307e4a5d7033610a`.

## What would work

The released [instance implementation](https://github.com/sergelogvinov/proxmox-cloud-controller-manager/blob/v0.16.1/pkg/proxmox/instances.go)
compares the live VM SMBIOS UUID with the Kubernetes Node system UUID. A changed
UUID can identify replacement even when Terraform reuses a VMID. Ordinary lookup
errors propagate; an inaccessible Proxmox node is treated as still existing.

The released chart supports a control-plane DaemonSet with host networking and
cloud-provider initialization tolerations. It could remain through a drain that
ignores DaemonSets. K3s would require disabling its embedded CCM and setting the
kubelet external-provider argument. The credential and controller would need to
be available before ordinary GitOps bootstrap to avoid uninitialized-node taints
blocking their own installation. These are source findings, not runtime passes.

## Why CCM was not selected

On the installed PVE version, `GET /cluster/resources` permits authenticated
users but silently skips each VM for which `VM.Audit` is absent (Cluster.pm
lines 263–267 and 587–588). A successful response can therefore be incomplete.

The pinned [pool lookup](https://github.com/sergelogvinov/go-proxmox-pool/blob/6bc833630250/vms.go)
returns `ErrInstanceNotFound` when that list lacks the VM. CCM translates this
into `InstanceExists=false`. The [Kubernetes lifecycle controller](https://github.com/kubernetes/cloud-provider/blob/v0.37.0/controllers/nodelifecycle/node_lifecycle_controller.go)
deletes a NotReady Node after that result. Consequently, losing audit permission
or leaving the pool that grants it can cause false Node retirement while the VM
still exists. This is distinct from an HTTP error or an unreachable API.

The dependency also serves cached inventory on refresh errors. Thus the top-level
error handling is insufficient to claim every absence decision uses a successful
current inventory. No runtime false-retirement or overlapping-writer experiment
was performed. False Node retirement alone does not establish a second writer;
CSI and Proxmox attachment safeguards are separate.

Accepting CCM would require treating continuous VM visibility as an operational
precondition. The user instead chose explicit verified retirement in the existing
Ansible handoff: establish complete inventory, verify the replacement identity,
refuse if the old UUID still exists anywhere, then use UID-conditional Kubernetes
Node deletion. Unknown inventory, read failures or changed identity must stop the
deployment before worker installation or scheduling recovery.

The [integrated qualification](2026-10-04-proxmox-csi-integrated-results.md)
remains incomplete. Its prior cleanup remains the last live lab state; this
assessment made only read-only infrastructure calls. The retirement implementation
and disposable-lab replacement test are the next prerequisites.

## Disabled source implementation

[Ansible PR280](https://github.com/Starktastic-Homelab/ansible/pull/280) stages the
chosen retirement step, disabled by default. Its source checks passed: 155 Python
tests with one existing live-GPU skip, pre-commit and offline Ansible lint. A fresh
independent review found no blocking issues for disabled staging. Runtime ACL
filtering, UID races, no-op paths, K3s rejoin and retained data remain lab gates.
Merge the source prerequisite before resuming qualification of the merged code.
