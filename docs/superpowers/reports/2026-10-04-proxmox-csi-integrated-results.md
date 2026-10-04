# Proxmox CSI integrated qualification: worker retirement gate

Follow-up: [verified retirement runtime results](2026-10-04-verified-retirement-results.md)
record the subsequent candidate worker-replacement pass and PR281 merge gate.
The findings below describe the original run.

Date: 2026-10-04. Status: **incomplete; automatic worker replacement failed**.
The storage baseline and a diagnostic recovery passed. No production CSI
activation or application migration occurred.

Scope: [approved integrated qualification](../plans/2026-10-04-proxmox-csi-integrated-qualification.md).
Evidence: [sanitized runtime observations and public test sources](evidence/2026-10-04-proxmox-csi-integrated-results.json).

## Verified results

- The merged shared Ansible setup completed, then reran with zero changes and
  unchanged token bytes. The separated CSI token had no permissions on production
  VMs100/200/201/202/300/900.
- Terraform used the merged VM module and Telmate3.0.2-rc10. Its first creation
  attempt required `Sys.Audit` at `/` for `GET /cluster/ha/resources/981`.
  The user approved a temporary, non-propagating read-only grant; verification
  confirmed no production VM access. The stopped partial clone was reconciled
  and replaced from a reviewed plan.
- All three guests reached Ready using merged Ansible k3s/drain/topology tasks.
  The lab skipped production bootstrap and kube-vip, used an isolated inventory,
  and corrected the runner's local Python interpreter to its installed venv.
- Stock ArgoCD10.9.2 reconstructed the lab-only applications using the repository's
  ApplicationSet phases and value layering. Stock Sealed Secrets2.20.0 recovered
  the generated CSI configuration from an encrypted Git declaration using the
  separately retained lab sealing key.
- Stock CSI v0.20.0/chart0.5.10 reached Synced/Healthy with the sealed configuration.
  The static Retain/RWOP PV/PVC bound to the existing2GiB raw image under owner9980.
- SQLite committed1,000 deterministic records using WAL and synchronous FULL.
  Integrity passed. Exactly one worker had the retained image attached; filesystem
  UUID was `0463dbf9-1a97-4bb4-bce7-8d510be7175c`.
- Terraform planned no changes with the CSI-managed SCSI attachment present.

## Failure reproduced

The saved replacement plan changed only worker VM982. The unchanged maintenance
helper drained the cluster, replaced that VM successfully, and emitted the exact
handoff `drained_nodes=["csi-int-server","csi-int-worker-1"]`. Worker2 was already
cordoned and was correctly omitted from that list.

Ansible then attempted to install the fresh worker under the same node name.
K3s repeatedly reported **Node password rejected**. The old Kubernetes Node and
its node-password Secret still represented the retired VM generation:

| Identity | Value |
| --- | --- |
| Old VM UUID | `d4171e20-a396-4d00-95ff-9f181132f166` |
| Replacement VM UUID | `eb2ebfa3-4b51-4c33-b93a-f6be1dddc1fe` |
| Old Kubernetes Node UID | `c2b0e3f4-859f-4632-91f1-d09b94142e5f` |

The blocked Ansible process was terminated after preserving the failure evidence.
This is a failed automatic recovery test; the later intervention must not be
counted as a pass of the existing deployment flow.

K3s documents this behavior: reusing a node name after losing its local password
requires deleting the old Node, which also removes its node-password Secret.
See [K3s node-password semantics](https://docs.k3s.io/architecture#node-password-secrets).

## Diagnostic recovery

Read-only Proxmox inspection confirmed the retired UUID was absent from every VM,
the replacement had no retained disk attachment, and the original2GiB image still
existed. Only then was the old Kubernetes Node deleted with its exact UID as an API
precondition. No CSI finalizers were forced and no password backup was restored.

The same Ansible playbook, with the original Terraform handoff, then completed.
The new Node reported the replacement VM UUID. CSI recreated the attachment and
mounted the same filesystem. All1,000 records, their hash, filesystem capacity and
SQLite integrity matched the baseline. The surviving worker's original cordon
remained in place.

This demonstrates that native Node retirement resolves the reproduced obstacle
in this lab. It does not yet provide an automatic, qualified retirement policy.

## Architecture decision before continuation

**Follow-up decision:** the user approved CCM assessment, then chose verified
retirement in Ansible after reviewing the released controller's inventory
visibility limitation. See the [pinned CCM assessment](2026-10-04-proxmox-ccm-assessment.md).
The following records the candidate considered at the end of the original run.

Prefer assessing the **unmodified Proxmox cloud controller manager (CCM)** before
adding custom node-retirement logic to the deployment handoff. This adds a cluster
controller and changes k3s cloud-provider bootstrap, so it needs an explicit design
decision and separate qualification; it was not installed in this run.

The inspected [upstream instance implementation](https://github.com/sergelogvinov/proxmox-cloud-controller-manager/blob/main/pkg/proxmox/instances.go)
compares the live VM UUID with the Node's system UUID and reports the old instance
as absent on a mismatch. This is relevant even when Terraform reuses the VMID.
The [upstream chart](https://github.com/sergelogvinov/proxmox-cloud-controller-manager/blob/main/charts/proxmox-cloud-controller-manager/values.yaml)
supports cloud-node lifecycle reconciliation and optional DaemonSet/host-network
mode. That mode is a candidate for keeping the controller available through the
existing drain procedure, which ignores DaemonSets.

These are source observations from upstream `main`, not a qualification of a
pinned CCM release. Remaining assessment must cover released-version behavior,
k3s external-provider flags, bootstrap ordering, narrowly scoped read-only
credentials, API-failure behavior, cordon preservation and same-name replacement.
The controller must not interpret an inaccessible Proxmox API as proof that a
writer is gone. The alternative is explicit fenced Node retirement in the existing
Terraform-to-Ansible handoff; neither alternative has been implemented here.

## Remaining qualification

The control-plane cohort/failure tests, two fresh-metadata rebuilds, interrupted
GitOps expansion, healthy movement and failed-node takeover remain pending in this
integrated run. Earlier isolated CSI findings retain their original scope. This
run does not establish full destroy/apply safety or production readiness.

## Cleanup

The synthetic writer was stopped and zero Kubernetes VolumeAttachments and active
Proxmox disk attachments were verified. VMs980–983 and their own disks, the single
synthetic image, temporary users/tokens/roles/ACLs, empty pool, NFS registration,
share7 and dataset GUID7010704397472109517 were removed. Proxmox VM purge had already
removed its six per-VM Terraform ACLs; cleanup reconciled that native behavior
before removing the remaining grants.

Production VM configurations100/200/201/202/300/900 matched their original
baselines. Existing NAS exports and global NFS settings were unchanged; NFS remained
running. Final credential-copy removal and maintenance-lock release are recorded
in the evidence's `cleanup_complete` field. Historical maintenance evidence and
the original user-provided Proxmox credential file are preserved.
