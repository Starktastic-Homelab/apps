# Proxmox CSI: rebuild and lifecycle qualification

Run: `csi-rebuild-20261004`. Status: **tested runtime cases passed; lab cleaned; production remains disabled**.

This run continues the [approved integrated plan](../plans/2026-10-04-proxmox-csi-integrated-qualification.md)
after [Ansible PR281](https://github.com/Starktastic-Homelab/ansible/pull/281)
merged as `913941f2610681d048587f30b0984453c7b768af`. Its tree matches the
previously qualified candidate; its post-merge deployment succeeded. Terraform
remained at `3b8806422f2cf11a3992f05198619493fa8874e9`.

[Sanitized evidence](evidence/2026-10-04-proxmox-csi-rebuild-results.json) records
source pins, VM/metadata generations, ACK correlations and cleanup receipts.

## Environment and isolation

A fresh disposable VM980 runner, VMs981–983, dedicated 8GiB-quota NAS dataset,
restricted NFS export, lab pool/storage registration and one synthetic raw image
used the approved allocation. The external image owner9980 remained unused as a
VM. Stock CSI v0.20.0/chart0.5.10, k3s v1.37.0+k3s1 and ArgoCD chart10.9.2 were
unchanged. Runtime work ran on the lab guests or the approved VM300 setup
container, never on the workstation.

The real VM300 maintenance operation covered the entire lab lifetime. Separate
lab ownership exercised Terraform and Ansible failures. Temporary Terraform,
CSI and read-only audit tokens retained their approved grants. The CSI token
had no permissions on production VMs. Shared setup passed and reran with zero
changes and unchanged token bytes; its temporary administrator inventory and
container were removed immediately afterward. Administrator credentials never
went to VM980.

Ansible used the explicit lab inventory and excluded production bootstrap and
kube-vip. The lab restored controllers from an isolated Git repository and the
same externally retained sealing key/CSI token. This was not a production
bootstrap or real GitHub Actions dispatch test.

## Cold rebuilds and interrupted expansion

The baseline committed 1,000 deterministic SQLite WAL/synchronous-FULL records.
The retained image started at 2GiB, with ext4 UUID
`45c5032b-80bc-4e87-a4b3-c6ccdf7cf092`, one worker attachment, and a Terraform
no-change plan.

1. **Request committed before expansion.** With controllers paused, Git changed
   the PVC request to 4Gi while the Git PV and actual image remained 2Gi. All
   three guests were destroyed before any replacements were created. A fresh
   cluster reconstructed its bindings from Git without restored Kubernetes
   objects. The claim bound, stock CSI expanded the image and filesystem to
   4Gi, and all 1,000 original records and the filesystem UUID survived.
2. **Backend expanded before Git PV reconciliation.** Git still described a 2Gi
   PV and 4Gi PVC while the actual disk/filesystem were already 4Gi. A second
   native destroy/apply recreated all three guests. An independent SSH/CRI
   session wrote inside the synthetic pod and durably recorded each committed
   acknowledgment on VM980. Recovery retained all 1,372 rows, including all
   372 acknowledged new transactions. The last acknowledgment timestamp was
   `1791144739.0455718`; Proxmox recorded the old worker's stop task in second
   `1791144739`. This is active-write VM-rebuild evidence, not a NAS/host power-loss
   durability test.

Both reconstructions retained the same image, filesystem UUID and external
sealing material. Fresh `kube-system` namespace UIDs and VM generations were
checked. Old guests were absent before new creation in both cold rebuilds;
that ordering provides writer exclusion during reconstruction. A final single
attachment snapshot alone would not prove continuous exclusion.

The anticipated size-mismatch deadlock did **not** occur. The manifests reserve
both directions: PVC `volumeName` and PV `claimRef` with matching name/namespace
and no old UID. In the pinned Kubernetes implementation, the already-reserved
claim branch completes binding without the size check used for an unreserved
PV. Stock expansion then retries until attachment exists and completes node
filesystem resizing. See the [pinned controller implementation](https://github.com/kubernetes/kubernetes/blob/v1.37.0/pkg/controller/volume/persistentvolume/pv_controller.go#L405-L434).
This result depends on the tested prebinding declarations and versions; it is
not a general claim that arbitrary mismatched PV/PVC objects bind.

After verifying actual backend and filesystem growth, Git PV capacity was
updated to 4Gi and Argo returned to Synced/Healthy. Until that update, the
application was healthy but showed capacity drift. Growth remains a request,
verify, then reconcile sequence; this does not qualify a one-edit resize with
permanently stale Git PV capacity.

## Movement and failure boundaries

- **Healthy movement:** GitOps moved the synthetic workload from worker1 to
  worker2. Data hashes, capacity and filesystem UUID were unchanged; the final
  Terraform plan had no changes. Attachment polling observed no overlap, but
  was not a continuous hypervisor trace.
- **Failed worker:** after exact-generation VM983 was powered off, the original
  pod remained held for 60 seconds after its Node became Unknown. Only after
  verifying power-off did the test apply Kubernetes' native out-of-service
  taint and move the declaration to worker1. Stock controllers detached and
  reattached the volume, preserving all rows. VM983 was restarted only after
  its image attachment was gone, then its taint was removed. No CSI finalizer
  was forcefully removed. This is an explicitly fenced recovery procedure,
  not unattended failover based only on a NotReady condition. See
  [Kubernetes' non-graceful shutdown procedure](https://kubernetes.io/docs/concepts/cluster-administration/node-shutdown/#non-graceful-node-shutdown-handling).
- **Missing image:** after complete workload shutdown and native detachment,
  the original image was temporarily moved aside within the same lab export.
  CSI returned NotFound, no replacement image appeared, and no writer became
  ready. Restoring the original inode allowed native retries to recover all
  data without volume recreation or finalizer changes.

## Cohort interruption

The native plan requesting replacement only of the control-plane resource
planned all three VM replacements. The test preserved Terraform's dependency
graph. At the native apply boundary, it injected external loss of the exact
old control-plane VM and required a strictly newer SQLite acknowledgment after
confirmed absence. The old workers remained alive. The injected failure left
lab ownership held at `applying`, emitted no success handoff and dispatched no
bootstrap. This was injected external control-plane loss, not a claim that
Terraform naturally destroys the control plane before its dependent workers.

Recovery adopted the original owner/nonce at the held stage without clearing or
resetting the record. Narrow test adapters allowed the unchanged native helper
to resume; a fresh complete plan created the missing control plane and replaced
both old workers. All old generations were gone before bootstrap. The helper
then emitted its actual success handoff. The test deliberately stopped before
Ansible, then a separate invocation consumed that unchanged payload.

Ansible and external Git/sealing bootstrap recovered all 2,628 rows, including
all 1,256 new acknowledgments from this case. The last acknowledgment was
`1791146044.6747477`, in the same second as the old worker's Proxmox stop task.
The filesystem UUID and 4GiB image were unchanged. All three applications ended
Synced/Healthy and the final Terraform plan had no changes.

The handoff payload was `has_changes=true` and `drained_nodes=[]`, because this
case used normal apply. The earlier worker replacement separately exercised a
non-empty drain handoff and pre-existing cordon preservation. The native helper
releases lab ownership before publishing/dispatching the Ansible handoff; this
test preserves that known limitation and does not claim cross-job lock coverage.
The real outer maintenance operation remained held throughout the lab.

## Test harness failures and evidence limits

The preserved logs distinguish test harness corrections from product changes:

- The first cold rebuild's image check used the restricted Terraform identity,
  whose content listing omitted the retained image. Direct inspection confirmed
  the original inode/size; the existing CSI identity could see it. The test
  resumed the same held operation. The second cold rebuild ran through the
  native helper without that interruption.
- The first writer's SSH transport waited for timeout after its VM disappeared.
  The exact obsolete SSH child was closed only after verifying the old VM
  generation was gone. Verification then read the finalized complete ACK ledger.
- Failed-node observation initially indexed `nodeName` on a pending pod. The
  check was corrected and resumed from the verified powered-off state. Its
  attachment polling therefore has an observation gap.
- The external control-plane-loss test initially encoded DELETE parameters in
  a body, which Proxmox rejected. The native failure retained ownership. The
  request was corrected to query parameters and the injection was completed
  under the same owner, nonce and stage.

No upstream driver or production source was changed to obtain these outcomes.
Independent review tightened ACK finalization and proof of new writes after
control-plane loss before the relevant results were accepted.

## Cleanup and delivery

All four current lab VMs and their owned disks, the exact synthetic image,
Proxmox registration/pool and temporary identities/roles/ACLs were removed.
NAS share9 and dataset GUID6623045154214145463 were deleted after identity and
snapshot/child checks. Existing exports and NFS configuration were unchanged;
NFS stayed running. Production VM configurations100/200/201/202/300/900 matched
the recorded baseline before and after cleanup.

Temporary administrator inventory/container, generated token copies, private
staging and local generated SSH keys were removed. The original user credential
file and prior historical records were preserved. The real maintenance lock was
released only after cleanup. A root-only archive containing sanitized logs,
complete ACK ledgers and public test scripts remains at
`/var/lib/homelab-maintenance/operations/csi-rebuild-20261004/qualification-evidence.json`
on VM300; its SHA256 is in the evidence receipt.

Together with the prior worker-retirement result (whose candidate tree matches
merged PR281), these results complete the listed disposable integration cases
within the documented harness/dispatch limits. Production activation still needs
a concrete reviewed scope. No production CSI activation,
application migration, production image allocation, storage-default change or
removal of the existing iSCSI writer guards is included in this run.
