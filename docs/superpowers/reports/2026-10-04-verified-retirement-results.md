# Verified Node retirement: runtime qualification

Date: 2026-10-04. Status: **candidate worker replacement passed; merge prerequisite remains**.
[Ansible PR281](https://github.com/Starktastic-Homelab/ansible/pull/281) fixes the
runtime type mismatch found in merged PR280. Retirement remains disabled by
default. No production activation or application migration occurred.

[Sanitized evidence](evidence/2026-10-04-verified-retirement-results.json)
records this fresh lab run. It follows the
[original integrated qualification](2026-10-04-proxmox-csi-integrated-results.md)
and [CCM decision](2026-10-04-proxmox-ccm-assessment.md).

## Scope and baseline

The user approved a separate temporary read-only audit identity with inherited
VM.Audit on `/vms`, inherited Pool.Audit on `/pool`, and non-inherited Sys.Audit
on `/access`, granted to both user and separated token. Actual API verification
confirmed complete inventory visibility and no write privileges. The ordinary
CSI identity retained lab-only access and no production VM permissions.

A fresh VM980 runner, three k3s guests, 8GiB-quota NAS dataset, restricted NFS
export and 2GiB raw image used the existing approved allocation. Global VM300
maintenance ownership remained held throughout. Shared setup used merged Ansible
`782bb1b8e6b6f8e8d469190cfe90f1fd6f29543e`, passed, and reran with zero changes
and unchanged CSI token bytes. Its temporary administrator inventory and tooling
container were removed immediately afterward. The administrator login never went
to VM980.

Terraform used merged `3b8806422f2cf11a3992f05198619493fa8874e9` and the existing
lab-only no-autostart override. Native k3s installation, topology and drain tasks
used the isolated inventory, excluding production bootstrap and kube-vip. The
previously qualified immutable Python setup image was restored after detecting
a moved local tag, before running the setup playbook. Lab fixture corrections
supplied empty anonymous registry credentials and fixed the Git listener's nft
rule syntax; these were fixture failures, not driver changes.

Stock CSI v0.20.0/chart0.5.10 and the isolated GitOps fixture reached healthy
state. SQLite committed 1,000 deterministic WAL/FULL records. The image had one
attachment, filesystem UUID `e296d970-f927-4fd9-bfa3-3e0c3743e2bf`, and Terraform
reported no changes with that CSI-managed disk present.

## Failure and fix

The saved plan replaced only VM982. Native Terraform drain/apply succeeded and
emitted the original scheduling-recovery handoff. The other VM generations
remained unchanged; worker2's pre-existing cordon stayed outside the handoff.

A temporary NoAccess override hid existing VM980 from the audit token while
`/cluster/resources` still returned HTTP200. The merged role refused incomplete
visibility, preserved the stale worker Node UID, and retained maintenance
ownership. The override was then removed and the exact approved grants verified.

With complete visibility restored, the merged role stopped at its final identity
check. Live diagnostics showed that the same API evidence passed in ordinary
Python, but the role's templated VM ID was `_AnsibleTaggedInt`. The exact
`type(vmid) is int` guard rejected this valid integer subclass. No Node deletion
or writer release occurred on that failure.

PR281 (`f8cd5d7`) accepts integer subclasses and explicitly rejects booleans.
The regression now renders the role's real expected-identity variables before
verification, reproducing the failure before the fix. All 15 retirement tests,
configured pre-commit/offline lint and hosted lint/syntax/format/policy checks
passed. Independent review found no blockers. The explicit installed-hardware
CI job was intentionally skipped.

## Candidate runtime results

Only the candidate filter was substituted into the merged lab source. Under the
same retained operation and original Terraform handoff, native Ansible:

- Verified full inventory and the absence of the old generation, deleted the
  exact old Node UID, and joined the replacement worker without manual password
  Secret deletion or CSI finalizer changes.
- Recovered all 1,000 records with the original hash and intact SQLite integrity.
  Filesystem UUID and capacity were unchanged; exactly one disk attachment
  remained, on the replacement worker.
- Preserved worker2's pre-existing cordon, restored the handoff's scheduling
  state, and released lab ownership only after success.
- Produced a Terraform no-change plan after recovery.

The surviving worker's same-generation path skipped Proxmox retirement reads;
the initial absent-Node paths did likewise. A separate native Kubernetes module
race test deleted and recreated an unschedulable synthetic Node with the same
name, then attempted deletion using its old UID. The API returned HTTP409 and
preserved the replacement; the synthetic test Node was subsequently removed.
This checks the native UID precondition, not concurrent execution of the entire
retirement role.

## Cleanup and remaining work

The synthetic writer was stopped and native CSI detachment confirmed before
cleanup. All four VMs, the image, storage registration, pool, three temporary
identities and their tokens/roles/ACLs were removed. NAS share8 and dataset
GUID11452572065753770046 were deleted after checking identity, no snapshots or
children, and existing export/configuration baselines. Production VM configs
100/200/201/202/300/900 and existing NAS exports were unchanged; NFS stayed running.
Generated credential copies and SSH keys were removed. Historical maintenance
evidence and the original user-supplied credential file were preserved. The real
VM300 operation was released after verified cleanup.

Merge PR281 before qualification continues against merged source. Control-plane
cohort/failure cases, two fresh-metadata rebuilds, interrupted GitOps expansion,
healthy movement and failed-node takeover remain pending. This candidate result
does not establish full destroy/apply safety or production readiness.
