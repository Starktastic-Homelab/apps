# CloudNativePG retained rebuild qualification results

Date: 2026-10-10. Disposable synthetic lab; no production PostgreSQL adoption or migration.

## Decision

Do not adopt stock CNPG 1.30.1 for the proposed retained-data rebuild design.
Application enrollment works, but the interrupted orphan-PVC adoption gate failed.
Return to the shortlisted existing PostgreSQL deployment plus an idempotent
application-enrollment Job. Its implementation and the PostgreSQL CSI cutover
still need a reviewed plan and their own live approval.

The user requires an unmodified operator/driver and unattended recovery from
surviving storage after complete Terraform destroy/apply. The tested interruption
left CNPG requesting manual intervention despite an intact retained image. An
owner/status repair script would add a recovery dependency that this qualification
was intended to avoid.

## Decisive test

1. Initialize synthetic PostgreSQL once on the exact prebound 2GiB retained image.
   Verify canonical application logins and a committed deterministic row.
2. Remove retain-policy enrollment CRs while PostgreSQL is healthy; confirm both
   SQL roles/databases survive. Remove the synthetic database namespace and PV
   metadata, wait for native CSI detach, and preserve the image.
3. Recreate fresh namespace/PV/PVC metadata with exact CNPG labels, serial 1,
   ownerlessness and binding. Restore canonical Secrets from isolated lab Git.
   Admission guards prohibit other/unbound claims and bootstrap Jobs/Job Pods.
4. Inject a native admission denial at the exact PVC's first ownerReferences
   assignment. Prove the denial with a server dry run, then start stock CNPG.
5. Observe Initialized=True and targetPrimary=cnpg-lab-1 while PVC ownership remains
   absent; the operator log contains the injected denial. Restart the operator,
   remove only the fault binding, and observe 185.2 seconds without status or owner repair.

Every sampled post-removal observation reported
`Cluster is unrecoverable and needs manual intervention`: Ready=false, no instance
Pods, and the PVC still ownerless. Only the intended claim existed; no bootstrap
Job was created. This is a failed automatic-recovery gate, not observed data loss
or a replacement empty database.

The [exact lab fault policy](../plans/fixtures/cnpg-adoption-owner-fault.yaml.example)
is retained for review/reproduction. The released source explains the result: `reconcileRestoredCluster` stops adoption
once Initialized is true, and calls `restoreClusterStatus` before
`restoreOrphanPVCs`. The injected fault interrupted that exact PATCH boundary.
[CNPG 1.30.1 restore implementation](https://github.com/cloudnative-pg/cloudnative-pg/blob/v1.30.1/internal/controller/cluster_restore.go).

This early gate used fresh database namespace/Cluster/PV/PVC metadata on the
original lab k3s cluster. It did **not** complete a Terraform VM destroy/apply
cycle. The remaining qualification matrix was stopped after the decisive failure;
no full-rebuild qualification is claimed. This rules out the tested version/design,
not every possible CNPG deployment or future release.

## Passed checks

- Native pinned Terraform VM module and maintenance helper created 981–983, after
  reconciling a tainted partial 981. Native Ansible installed k3s and all nodes were Ready.
- Current VM UUIDs matched Kubernetes systemUUIDs; trusted bootstrap set the
  protected placement label and NodeRestriction explicitly denied kubelet self-assignment.
- Isolated Argo foundation reconciled encrypted/public Git inputs, and Sealed
  Secrets recovered canonical CSI configuration with verified Proxmox certificate trust.
- Stock CSI attached/formatted the approved blank image and bound one static
  Retain/RWOP claim; stock CNPG initialized PostgreSQL 18.6 and became Ready.
- DatabaseRole/Database resources created app_alpha/app_beta without manual role/DB
  creation. Canonical supplied passwords authenticated both synthetic clients.
- Explicit PUBLIC CONNECT revocation denied cross-service database access. Database
  ownership alone was not treated as isolation.
- Retain-policy declaration removal preserved both SQL roles and databases.
- The initial deterministic row committed with synchronous_commit=on; its ACK was
  fsynced outside the cluster. The image's ext4 UUID and PostgreSQL system identifier
  were recorded before the interruption.
- Established bootstrap-Job denial and first-owner PATCH denial were explicitly
  exercised with server dry runs before the operator fault test.

## Untested gates

Two full Terraform cold rebuilds (including ongoing ACK writes), Git-only complete
bootstrap recovery and CNPG ownership reconciliation, the complete missing/late/
invalid-PVC and image matrix, worker movement/replacement and unreachable-writer
fencing, growth 2→4GiB, credential rotation/third-service enrollment, synthetic
monolith import and an off-NAS logical restore were not completed.

The synthetic client tests do not establish compatibility of existing application
schemas, extensions, grants or passwords. Live SQL version/catalog inventory and
actual-data rehearsal remain PostgreSQL migration prerequisites. CNPG1.30's
Kubernetes1.37 support limitation also remains unresolved; it did not need a
production decision because the recovery gate already failed.

## Lab scope and adaptations

Four disposable VMs 980–983, each 2vCPU/2GiB/8GiB root; external image owner 9980
remained unused as a VM. Separate NAS child GUID 3032057416834972763/share 11 had
an 8GiB quota. Only the 2GiB primary image was allocated; no restore image or growth
allocation occurred. Host available RAM during sequential native creation stayed
above the 2GiB floor (minimum 3876237312 bytes).

Pins: Ansible 6d520867695f8d9b3071dec2ef53938abf808e04,
Terraform 3331a4f058ae7ae7a4e8f70a060d60f9ecf39a4b,
k3s v1.37.0+k3s1, CSI v0.20.0/chart 0.5.10, Argo chart 10.9.2,
Sealed Secrets chart 2.20.0, CNPG 1.30.1 commit 2a35abb4628f209d149825ef3c38011e0701ff2f
and digest-pinned PostgreSQL 18.6. See the [artifact pins](evidence/2026-10-10-cnpg-qualification-preparation.json).

The lab used a separate local Terraform backend, explicit lab inventory, single
eth0, no production VIP/bootstrap, empty public registry credentials and lab API
trust. The wrapper cleared boot-on-host-start on each lab generation. It disabled
Telmate's stock broad minimum-permission preflight while retaining server ACLs
and production-write denial checks. Approved follow-up grants were an exact
synthetic-user discovery group and VM.GuestAgent.Audit limited to 981–983.
VM980 was removed from the inherited Terraform lifecycle pool. No administrator
login entered the lab runner or Kubernetes; only generated lab credentials did.

Controllers were initially installed through native Helm/SSA, and isolated Git
used a native read-only daemon with encrypted/public contents. Harness setup
failures were reconciled before resuming: partial Terraform/provider privileges,
a moved Helm index, dumb-HTTP Git incompatibility/service startup, wrapper compile/
variable mistakes, CSI detach lag, atomic SSA manager conflicts, stale Argo sync
retry history and admission-binding propagation. The selective metadata-loss fixture
recreated its foundation Application to remove surviving failed-sync history;
complete control-plane loss would also discard that history. These adaptations
are distinct from the actual stock CNPG failure and are not production workflow coverage.

## Cleanup and evidence

Verified removal: VMs980–983 and their root/cloud-init disks, the primary image,
lab Proxmox storage/pool, three users/tokens, four roles, the discovery group/ACLs,
NAS share11 and child dataset with its recorded GUID. Generated lab private copies
were deleted from Proxmox/VM300; VM980's keys, credentials, kubeconfig and Terraform
state/plans were removed before its root disk was destroyed. Public operation
receipts and the user's persistent local login files were preserved.

Original VM/container configuration hashes and the original ACL hash matched the
preallocation baseline. Remaining storage fields matched the recorded mid-lab
readback after treating content as an unordered set; native serialization produced
several equivalent orders. The original storage baseline included a global API
digest and did not preserve raw bytes, so an exact preallocation storage-byte
comparison remains unverified. Cleanup verification passed before maintenance release.
The exact owned VM300 maintenance operation was released through the pinned native
helper after verification. No generated private copies remain in the operation.

Sanitized [qualification evidence](evidence/2026-10-10-cnpg-qualification-results.json)
records identities, observed failure, passed initial checks, cleanup and scope limits.
Private tokens, credentials, keys, kubeconfigs, Terraform state/plans and private logs
are excluded from repository evidence.
