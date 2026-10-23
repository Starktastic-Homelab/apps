# Jellyfin retained iSCSI pilot implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task after review. Preserve the previously used inline execution method, with one independent review at the end. Steps use checkbox syntax for tracking.

**Goal:** Prepare independently reviewable production PRs and qualification procedures for durable NFS writes, scoped fencing, retained static iSCSI and the first Jellyfin migration; do not execute a production migration merely by completing this plan.

**Architecture:** Keep NAS lifecycle and service records in Apps, generic node prerequisites/fencing in Ansible, and VM lifecycle in Terraform. A durable external maintenance lock serializes those operations. Static retained volumes and explicit single-worker authorization keep unknown writers unavailable until verification/fencing succeeds.

**Tech Stack:** TrueNAS 25.10.7 JSON-RPC over pinned TLS; Proxmox 9.2 API; Python standard library plus websocket-client 1.9.2; Ansible; Terraform; K3s admissionregistration.k8s.io/v1; stock democratic-csi 1.9.5; existing Helm app-template and ArgoCD.

**Spec:** [Approved pilot design](../specs/2026-09-21-jellyfin-iscsi-pilot-design.md). User approved the design and the laptop backup destination on September 21. Live NAS/ACL changes, test-VM allocation and Jellyfin downtime remain explicit deployment steps.

## Global constraints

- Production changes are versioned; the user merges PRs. Do not modify their dirty Ansible `scripts/get-kubeconfig.sh` checkout.
- Start implementation branches from current remote main, not the old lab branch: Apps `b3425a4`, Ansible `7a0ed65`, Terraform `d60c54a` at planning time. Recheck remote heads at execution. Apps main already contains #1231/#1233; preserve the PostgreSQL backup fix and its tests.
- The existing draft Apps #1232 is evidence/design only. New platform code belongs in separate PRs; selectively reuse tested algorithms, never run-specific lab scripts/IDs.
- No third-party patches, unofficial Jellyfin PostgreSQL provider, automatic mkfs/fsck, dynamic provisioning, changed default StorageClass, broad NAS credentials in K3s, or silent empty database initialization.
- Pilot ZVOL: 64 GiB, non-sparse, 16 KiB blocks, 512-byte sectors, `sync=STANDARD`, ext4, retained PV/PVC, RWOP. Source NFS claim remains intact.
- CSI formatting `-n` and disabled automatic filesystem checking remain paired with the external native/filesystem gate. The lab did not prove damaged-media NodeStage safety.
- Worker-only pilot, one authorized worker generation at a time. Fencing role: only `VM.Audit VM.PowerMgmt` at `/vms/201` and `/vms/202`, for both user and separated token. No production power-off permission test.
- Cache/transcodes: one disk `emptyDir`, 10 GiB combined limit, separate subdirectories; app ephemeral-storage request/limit 12 GiB; selected worker free space at least 25 GiB and compatible eviction thresholds.
- Backup root: `/home/benf/Backups/homelab/jellyfin`, private 0700, on the confirmed encrypted laptop filesystem. No backups in `/tmp`, Git, or only on Proxmox/TrueNAS.
- User-approved design does not waive live cutover prerequisites or the 24-hour acceptance period. No background monitor is scheduled by this plan.

## Review focus

1. Unknown mutation outcome: no blind second update/create/stop, no success receipt before readback; Task 1/4/5 tests.
2. VMID reuse or overlapping maintenance: exact current UUID plus a persistent shared lock, not timeout-based lock stealing; Task 2/4 tests.
3. New cluster/namespace/node or permissive node affinity: old authorization cannot admit a replacement writer; Task 3/6 tests.
4. Probe encountering a CSI-owned session or unreadable storage: never log out that session, repair source or create an empty service; Task 5/6 tests.
5. Post-cutover writes and incomplete backup streams: stale NFS is not a current rollback; failed producer/extraction/restore never receives a passed receipt; Task 7/8 tests.

## Delivery boundaries and execution order

Prepare four review groups: A, the NFS durability tool/configuration (Task 1); B, coordinated Ansible/Terraform maintenance and fencing (Tasks 2–4); C, Apps retained-volume tools and admission/CSI setup (Tasks 5–6); D, backup and Jellyfin transition (Tasks 7–8). Task 9 validates cross-repository behavior and prepares the qualification runbook. They can be separate PRs without pretending each alone makes migration safe.

Code preparation order is A → B → C → D. Live application order differs: confirm current consistent database backups first, then apply A during its approved observation window; qualify B; onboard C; finally run D during Jellyfin's approved outage. Do not weaken the backup gate just to keep numerical order.

## Task 1: Versioned NFS sync correction with readback

**Files (Apps):** create `scripts/storage/nas_rpc.py`, `scripts/storage/nfs_sync.py`, `scripts/storage/requirements.txt`, `scripts/storage/nfs-sync.json`, `scripts/storage/tests/test_nfs_sync.py`, `scripts/storage/README.md`; modify `.github/workflows/validate-and-diff.yml` to run these tests. Do not change the PostgreSQL backup implementation.

**Interfaces:** `NAS.call(method: str, *params) -> object`, a context-managed TLS/authenticated connection with no automatic retries; `inspect(nas, expected: dict) -> dict`; `apply_standard(nas, expected: dict, backup_receipt: dict, journal: Path) -> dict`. Inspection never invokes mutations. `expected` contains NAS version, pool name/GUID, dataset name/GUID and desired sync. The read-only planning call confirmed dataset GUID `14547210392972608779`; recheck it before filling the real policy and again before a mutation. Never derive identity from its name alone.

- [ ] Capture `pool.dataset.query` with `extra.properties=["guid","sync"]` for `apps/pv`; commit only the nonsecret GUID, pool GUID `9917900421692286909`, dataset GUID `14547210392972608779`, path, version and `STANDARD`. The transport accepts private credential/CA/leaf-pin file paths, not passwords in arguments; reuse the tested TLS fingerprint check before sending authentication. Pin `websocket-client==1.9.2` in the isolated tool requirements. Do not ship the lab's loopback URL or disabled certificate checking without an independently verified exact pin.
- [ ] Write a fake NAS that records method calls and can apply an update before raising TimeoutError; its query path returns that changed state. Assert these concrete behaviors:

```python
class SyncTests(unittest.TestCase):
    def test_wrong_guid_never_updates(self):
        nas = FakeNAS(guid="different", sync="DISABLED")
        with self.assertRaises(ValueError):
            inspect(nas, EXPECTED)
        self.assertEqual(nas.updates, [])

    def test_lost_reply_requires_reconciliation(self):
        nas = FakeNAS(guid=EXPECTED["dataset_guid"], sync="DISABLED",
                      lose_update_reply=True)
        with self.assertRaises(TimeoutError):
            apply_standard(nas, EXPECTED, VALID_BACKUP, self.journal)
        self.assertEqual(len(nas.updates), 1)
        self.assertEqual(inspect(nas, EXPECTED)["sync"], "STANDARD")
```

Define `EXPECTED`, `VALID_BACKUP` and FakeNAS in this test module using synthetic values; use TemporaryDirectory for `self.journal`. Add cases for already-standard/no update, wrong pool/version, missing/expired/failed backup evidence, inherited/changed settings, failed readback, and a secret-bearing server error that must be redacted. A live backup receipt is operator-generated evidence, not a CI fixture.
- [ ] Run `python3 -m unittest discover -s scripts/storage/tests -p 'test_nfs_sync.py' -v` and observe failure before implementation. Implement the narrow transition below, with the journal opened exclusively and fsynced before mutation:

```python
before = inspect(nas, expected)
if before["sync"] == "STANDARD":
    return {"changed": False, "verified": True}
if before["sync"] != "DISABLED":
    raise ValueError("Unexpected current sync policy")
# Require a successful, current backup receipt matching this dataset GUID.
# Persist the operation intent; an existing intent requires inspect/reconcile.
nas.call("pool.dataset.update", expected["dataset"], {"sync": "STANDARD"})
after = inspect(nas, expected)
if after["sync"] != "STANDARD":
    raise RuntimeError("Sync readback did not confirm STANDARD")
```

No `DISABLED` mutation branch and no automatic rollback. Journal terminal states are `verified` or `needs-reconciliation`; an exception cannot mark success. Add CLI subcommands `inspect`, `apply-standard`, `reconcile` with the same identity checks. Require a nonempty, integrity-checked backup manifest with timestamp no older than 24 hours, exact dataset GUID and explicit covered critical applications. The runbook requires operator review of coverage, including SQLite consistency, and a PostgreSQL restore check; metadata alone is not proof of restore.
- [ ] Run tests, `python3 scripts/test-pg-backup.py`, applicable pre-commit hooks and diff checks; commit `feat(storage): prepare verified NFS sync correction`. Draft PR A contains the precise live command, affected dataset, backup prerequisites and latency/health observation procedure, but no apply workflow triggered on merge. Report that mutation has not run.

## Task 2: One external maintenance lock across repositories

**Files (Ansible):** create `scripts/maintenance_lock.py`, `scripts/tests/test_maintenance_lock.py`, `maintenance-runner.yml`, `roles/maintenance_runner/tasks/main.yml`; modify `.github/workflows/deploy.yml` and README. **Files (Terraform):** modify `.github/workflows/apply.yml`, add `scripts/tests/test-maintenance-workflow.py` and corresponding CI invocation.

**Interfaces:** `acquire(root: Path, operation: str, owner: str) -> str` returns a cryptographically random nonce; `verify(root, owner, nonce) -> None`; `release(root, owner, nonce) -> None`. The same versioned Ansible helper is consumed by both workflows at an immutable reviewed commit, recorded in Terraform. Fencing in Task 4 uses exactly these functions. Lock root is the runner-host path `/var/lib/homelab-maintenance`, bind-mounted as `/maintenance` into mutating job containers. No dependency on the K3s API or NAS. Apps NAS mutations, target verification/mounts and writer-release operations execute on this same runner under a manual storage-maintenance workflow with the shared mount. An operator may retain a lock across manual stages; the next authenticated workflow invocation must present the exact original owner/nonce and verify the recorded stage before continuing. Only the immutable or held read-only backup stream and restore tests run on the laptop. A lost client/job leaves the durable operation held; no automatic takeover.

- [ ] Write tests using two processes and one TemporaryDirectory. Both call acquire concurrently; exactly one succeeds. Add process-kill/persisted-lock, wrong-owner/nonce release, corrupted/truncated record, symlink root/record, stale-age, host-reboot (same persisted directory), missing bind-mount marker and interrupted write cases. No elapsed time is permission to acquire an existing lock.

```python
nonce = acquire(root, "terraform-apply", "terraform/123/1")
with self.assertRaises(FileExistsError):
    acquire(root, "fence", "ansible/456/1")
with self.assertRaises(PermissionError):
    release(root, "ansible/456/1", nonce)
verify(root, "terraform/123/1", nonce)
```

- [ ] Implement exclusive creation with `O_CREAT|O_EXCL|O_NOFOLLOW`, owner-only update semantics, explicit file and directory fsync, and corruption refusal. Persist a runner-instance marker so an unmounted empty container directory cannot become a second lock domain. Provision the host directory with controlled group ownership/setgid and default permissions allowing the runner and its root job containers to share the same record; the file contains no API secrets. Refuse an existing mismatched marker. Bootstrap the runner role through a reviewed explicit inventory entry discovered from VM300, never an invented address.
- [ ] Restructure Terraform so lock ownership spans drain, apply and uncordon. Pass nonce as a masked job output and verify the persistent record immediately before each mutation. Release only after successful apply and recovery; failure/cancellation leaves a record requiring a documented owner/operation inspection and explicit reconciliation. No unconditional `always()` unlock. Ansible holds the same lock for its configuration changes, releases after success, and only then publishes final handoff. No nested ownership/deadlock across Terraform's downstream dispatch.
- [ ] Add workflow fixture tests proving all Terraform apply/destroy modes and manual Ansible dispatches traverse acquire/verify, that drain cannot begin without ownership, and that failed prerequisite jobs cannot reach mutation. Verify the helper commit pin and bind mount exist in every mutating job. Existing CI concurrency remains useful, but is not the cross-repository lock.
- [ ] Run helper tests, workflow validation/pre-commit and Ansible syntax/lint; commit this coordinated prerequisite in both repos. Document that a lost runner or ambiguous lock blocks maintenance. An operator must also prohibit concurrent Proxmox GUI actions; ACLs alone cannot serialize an administrator.

## Task 3: Generic worker initiator prerequisites

**Files (Ansible):** create `roles/iscsi_initiator/{tasks,defaults,handlers}/main.yml`, `roles/iscsi_initiator/templates/initiatorname.iscsi.j2`, `scripts/tests/test_iscsi_initiator.py`; modify `k3s.yml`, `roles/k3s_workers/tasks/main.yml` and inventory/group variables. Do not read service definitions from Apps.

**Interfaces:** a reviewed map `iscsi_initiator_names` maps each worker role to one unique IQN; node label `storage.starktastic.net/iscsi-ready=true` is published only after prerequisite validation. A separate generation receipt contains VMID/SMBIOS UUID, Kubernetes node UID, hostname, storage IP and IQN; it is refreshed only after verifying that the old generation is destroyed or fenced. It is not an auto-updated authorization.

- [ ] Test empty/duplicate IQNs, non-worker hosts, existing unexpected IQN with a live session, insufficient root disk space, changed VM generation without retirement proof, and successful re-run with unchanged IQN. Use command-mocked tests for refusal paths; live session commands must never log out during prerequisite checks.
- [ ] Add a worker-only play before joining workers: install `open-iscsi` and `e2fsprogs`, load required initiator modules, write the reviewed IQN before starting iscsid, then verify package/service/network state. Refuse to rewrite an IQN or restart its service when a session is active. Scope handlers to changes and keep unrelated K3s/GPU configuration intact.
- [ ] Use an Ansible assertion before template/service changes:

```yaml
- name: Refuse a live initiator identity change
  ansible.builtin.assert:
    that:
      - iscsi_existing_iqn == iscsi_expected_iqn or iscsi_session_count | int == 0
    fail_msg: "An active iSCSI session prevents changing this node identity"
```

Additionally require old-generation retirement evidence before a fresh VM may reuse the role IQN; zero sessions on the new VM says nothing about an old VM. Do not publish the ready label when this proof is missing.
- [ ] Run the new tests, Ansible lint without a `.` argument, syntax checks and pre-commit; commit `feat(storage): manage verified worker initiator identities`. Ensure fresh-cluster bootstrap still restores Sealed Secrets keys before Apps may release writers.

## Task 4: Restricted fencing account, command and test workflow

**Files (Ansible):** create `storage-fencing.yml`, `roles/storage_fencing/{defaults,tasks}/main.yml`, `scripts/proxmox_fence.py`, `scripts/tests/test_proxmox_fence.py`, `.github/workflows/storage-fencing.yml`; extend README and validation workflow.

**Interfaces:** `verify_vm(api, expected: dict) -> dict`, `fence(api, expected: dict, lock_root: Path, owner: str, nonce: str, receipt: Path) -> dict`. `api.get(path, **query)` and `api.post(path, data)` are a small stdlib HTTPS wrapper with verified CA/pin and bounded timeouts. Expected identity must come from the reviewed generation record, not the currently returned VMID configuration.

- [ ] Test wrong name/UUID, pending identity edits, API403, unreadable status, lost stop response, task timeout/non-OK exit, apparent stop followed by generation change, missing lock and wrong token. Every failure must produce no replacement-release receipt. Assert each stop path uses the exact reviewed VMID and never calls start/reboot/skiplock.

```python
with self.assertRaises(ValueError):
    fence(FakePVE(uuid="replacement"), EXPECTED_VM,
          root, owner, nonce, receipt)
self.assertFalse(receipt.exists())
self.assertEqual(api.posted, [])
```

The FakePVE fixture records posted paths and models both task and VM-status responses. Test a task returning OK while the VM still runs; that must also fail.
- [ ] Implement `GET config?current=1`, pending-state inspection, immediate lock/identity recheck, one `POST status/stop`, owner-task polling and final exact identity plus `status=stopped`. A lost response requires `reconcile` (read status/identity again), not another automatic POST. Atomically save a receipt binding expected generation, lock operation and final observation; release logic revalidates that the VM has not been restarted since the receipt.
- [ ] Create a separate PVE user/privilege-separated token and role with only `VM.Audit VM.PowerMgmt` on 201/202. Both ACL layers use propagation=false; inspect preexisting grants and fail on broader permissions instead of deleting unknown grants. Create the token once, save its value directly to the approved external secret store with `no_log`, and never overwrite/regenerate a lost token implicitly. Live account application is a separately approved playbook run, not part of K3s auto-deploy.
- [ ] The manual workflow runs on the same external runner and uses Task 2's lock. It consumes reviewed identity plus explicit operation choice (`inspect`, `fence`, `reconcile`); it does not accept arbitrary shell commands or a VMID without its UUID. Refuse protected VMIDs and allow only the separately declared disposable-test exception during qualification.
- [ ] Prepare the 128 MiB diskless/networkless test-VM procedure with unused-ID and name/UUID ownership checks, temporary exact ACL, actual token read/stop/task/status checks, wrong-UUID test and cleanup. Protected production VM permission checks are read-only/effective-ACL checks, never attempted destructive calls. Document this proves the permission route, not a production partition recovery.
- [ ] Run unit tests, Ansible validation and workflow checks; commit and include in PR group B. No account, role, VM or production power state changes during PR preparation.

## Task 5: Separate native onboarding and recovery tools

**Files (Apps):** create `scripts/storage/identity.py`, `scripts/storage/onboard.py`, `scripts/storage/verify.py`, `scripts/storage/initiator_probe.py`, `scripts/storage/tests/test_identity.py`, `scripts/storage/tests/test_onboard.py`, `scripts/storage/tests/test_probe_sessions.py`, `storage/services/jellyfin.json`. Reuse Task 1 transport; port the tested predicates from `tests/static-iscsi/identity.py` and session-ownership checks from `initiator_guest.py`, removing lab assumptions explicitly.

**Interfaces:** `verify_native(record: dict, state: dict) -> None`; `onboard(nas, intent: dict, journal: Path) -> dict`; `verify_existing(nas, record: dict) -> dict`; `probe_filesystem(record: dict, runner) -> dict`. The record has service/marker, pool and ZVOL GUIDs, capacity, filesystem UUID, extent ID/serial/NAA, target ID/IQN, portal/LUN, exact auth networks/initiators/group, sync mode and explicit PV/PVC names. Final native IDs remain absent until onboarding returns them; no deployable fake IDs.

- [ ] Copy the existing identity tests to production test scope and add changed sync, production auth network `10.9.8.0/24`, foreign extent, alias target, extra portal listener, duplicate mapping and changed capacity cases. Run and observe failures before porting the minimum predicates. Exact worker IQNs replace the lab's three-initiator list.
- [ ] Test interruption after every NAS mutation with a journaled intent. Re-entry must inspect the exact intent and stop for missing/ambiguous identity rather than create duplicates. Existing records never invoke create/delete/mkfs. NAS errors and receipts must not expose CHAP/API credentials.
- [ ] Require the Task 2 maintenance lock before every onboarding mutation and initiator mount, using the same pinned Ansible helper checked out by the manual Apps workflow. Pure native inspection remains read-only and needs no lock. The workflow supports only reviewed operation names and service records, not arbitrary shell input. Onboarding verifies the apps pool GUID and available capacity, creates only the approved `apps/iscsi` parent and Jellyfin ZVOL, explicitly sets standard sync, and reuses portal identity 1 only if its actual listener still matches. Preserve the global IQN basename. Build the 64 GiB non-sparse target with exact worker CHAP/initiator/network restrictions and insecure third-party copy disabled. Separate the creation intent from deliberate one-time format/copy; normal verification has no initialization operation.
- [ ] Probe tests must preserve foreign/existing CSI sessions and refuse mounted devices before changing node records:

```python
with self.assertRaises(RuntimeError):
    probe_filesystem(RECORD, runner_with_existing_target_session)
self.assertFalse(runner_with_existing_target_session.called("logout"))
self.assertFalse(runner_with_existing_target_session.called("node-update"))
```

Reject blank/wrong UUID/partitioned/corrupt filesystems. Mount only the externally verified device read-only with noload, copy DB/WAL to private scratch for integrity/identity checks, then unmount and log out only the session created by this invocation. A filesystem requiring journal recovery remains held; no automatic fsck.
- [ ] Add a separately invoked snapshot-policy operation for `apps/iscsi` with recursive enabled and one-week retention, preserving unrelated tasks. Read back exact dataset, schedule and retention; reconcile an ambiguous create reply before any retry. Mirror the existing `apps/pv` schedule only after reading its actual current schedule, recording it in the intent. Test wrong-dataset refusal, existing matching task and lost-reply reconciliation. Expose a read-only verification command and a distinct target clone/restore procedure; no automatic production rollback.
- [ ] Run ported session/identity/fault tests and existing lab regressions; commit `feat(storage): separate retained onboarding from read-only recovery`. PR C may contain tooling and non-deployable service intent; returned identities are filled only after separately approved onboarding.

## Task 6: Production CSI and placement-specific admission

**Files (Apps):** create `infrastructure/system/retained-iscsi/{app.yaml,values.yaml}`, `scripts/storage/render_storage.py`, `scripts/storage/release.py`, `scripts/storage/tests/test_render_storage.py`, `scripts/storage/tests/test_release.py`, `.github/workflows/storage-maintenance.yml`, and rendered manifests under `infrastructure/system/retained-iscsi/manifests/` after valid native records exist. Follow the existing ApplicationSet value cascade; do not add an alternate bootstrap framework.

**Interfaces:** `render(record: dict) -> list[dict]`; `authorize(record, verification, namespace_uid, node_generation) -> dict` returns an external authorization ConfigMap only after all checks. It includes released state, exact record hash, namespace UID, hostname, Kubernetes node UID and SMBIOS UUID. This ConfigMap is not a released=true object in Git. The workflow verifies maintenance ownership before hold/release and before mount-changing verification; a local standalone invocation without the runner instance marker refuses these operations. `hold` closes it; `release` cannot create an authorization from only a namespace name.

- [ ] Render the unchanged lab-pinned stock driver image, node registrar, cleanup image and proxy digests from `tests/static-iscsi/csi-values.yaml`, but use driver name `org.democratic-csi.retained`. Render no controller/StorageClass; constrain node pods to the worker storage-ready label. Preserve format `-n` and disabled fsck. Validate actual chart schema/layers before deciding exact value keys.
- [ ] Render static ext4 Retain/RWOP explicit PV/PVC bindings and CHAP SealedSecret references. Use `scripts/seal.sh`; never embed CHAP in attributes. Prune/delete annotations protect both PV and PVC; omit old UID/resourceVersion/claimRef UID from recovery records.
- [ ] Admission tests on a disposable local K3s/kind API must reject missing authorization, namespace UID mismatch, stale node generation, foreign claim, modified driver/fsType/identity, alias PV, dynamic storage, missing writer label, explicit wrong nodeName, and extra affinity OR terms. Require one exact hostname match plus the expected generation label; prevent pre-binding and affinity edits from bypassing it. Unrelated media claims must still pass. Do not count a Python string comparison as a Kubernetes CEL test.

```python
self.assertFalse(admit(writer_pod(host="worker-b"), authorization(host="worker-a")))
self.assertFalse(admit(writer_pod(extra_or_term=True), authorization(host="worker-a")))
self.assertFalse(admit(writer_pod(), authorization(namespace_uid="old-namespace")))
self.assertTrue(admit(unrelated_media_pod(), missing_authorization()))
```

Here `admit` submits a server-side dry-run request to the disposable API, returning false only for an admission denial; transport errors fail the test. The fixture loads rendered policies and its namespace/parameter objects, never production kubeconfig.
- [ ] Add release tests for uncertain old writer, absent CHAP, wrong native/filesystem identity, namespace recreation and stale fence receipt. No release unless clean-unmount evidence from the old worker or a current matching power-off verification is present. Permit exactly one worker, deliberately trading unattended failover for safety.
- [ ] Verify release record survival rules: fresh cluster has no authorization; retired node generation cannot reuse an old one; clean handoff changes authorization only while held. Commit PR C after actual Helm rendering, schema/admission tests and policy regressions. Missing disposable-API capacity/tooling is a blocker to qualification, not a passing test.

## Task 7: Independent cold-backup and restore verification

**Files (Apps):** create `scripts/storage/jellyfin_backup.py`, `scripts/storage/tests/test_jellyfin_backup.py`, `docs/runbooks/jellyfin-storage.md`. Reuse the existing protected secret-backup procedure in Ansible; never copy keys to Git/evidence.

**Interfaces:** `capture(source: Path, destination: Path, metadata: dict) -> Path`; `verify_restore(archive: Path, scratch: Path) -> dict`. Metadata contains exact source snapshot/native identity, image digest, UTC capture time, included paths, explicit disposable exclusions, archive hash and restore result. A backup passed receipt exists only after full extraction and verification.

- [ ] Test source-reader failure after partial output, truncated archive, wrong hash, unexpected absolute/traversing/symlink escape entries, SQLite DB+WAL recovery, wrong ownership, missing plugin/LiteDB files and full target disk. Never publish a final archive or passed receipt after one fails. Use small synthetic fixtures and no production database in CI.
- [ ] After the source is held, create one explicitly owned temporary reader pod that mounts the original config PVC read-only; exclude only this known reader from the no-writer check. Stream a numeric-owner tar archive with ACL/xattr metadata via `kubectl exec` stdout directly to the laptop partial file; do not buffer it in a pod, worker disk or laptop `/tmp`. The held live source can be read consistently after shutdown; record the NAS snapshot as an additional recovery point without falsely claiming the bytes came from a snapshot mount. If any source writer reappears, abort and reject the archive. Delete only the owned reader pod after capture. Implement producer/consumer exit checking separately, analogous to the corrected PostgreSQL backup script. Use private partial files and atomic rename only after completion; fsync before recording durable success. Reject `/tmp`, a symlinked destination or an unapproved backup root. Preserve ownership/modes/links/xattrs in the archive and verify them after extraction; if the local extraction filesystem cannot preserve metadata, stop rather than silently drop it.
- [ ] Source capture requires the held workload state, no active Jellyfin-specific job, no config consumer, and exact snapshot/path verification. Include full persistent `/config` contents plus DB/WAL/SHM and plugin state. Exclude only cache and transcodes named in the spec. Never modify live SQLite or delete WAL/lock files.
- [ ] Run SQLite integrity on an extracted copy, then start the exact Jellyfin image against a second disposable restored copy with network disabled, no production mounts, no GPU requirement and no plugin updates. Verify existing catalog/server state and plugin/LiteDB loading without publishing users/media names. Failed restore keeps cutover closed.
- [ ] Document that this backup needs Jellyfin downtime, and the user has approved the destination but not a downtime window. Do not take the cold backup during code preparation. Run unit/fault tests and commit the tool/runbook in PR group D.

## Task 8: Reviewable held, cutover and rollback states

**Files (Apps):** modify `services/media/jellyfin/values.yaml`, `services/media/jellyfin/manifests/ldap-library-sync.yaml`, `services/media/jellyfin/manifests/kustomization.yaml` only in the appropriate staged PR; retain existing `pvc.yaml` and `cache-pvc.yaml` through acceptance. Add `scripts/storage/tests/test_jellyfin_render.py`; extend `docs/runbooks/jellyfin-storage.md`.

**Interfaces:** reviewed Git revisions `source-held`, `target-held`, `target-released`; record their actual immutable commits in the maintenance receipt before application. They are sequential release artifacts, not magic names that an executor must guess. The LDAP library-sync CronJob is a known API writer: suspend it during hold, wait for current Jobs to finish, and resume only after target acceptance checks.

- [ ] Render tests for replicas=0 while held, unchanged image/probes/GPU/media, exactly one retained config claim, Recreate strategy, strict authorized-worker affinity, 10 GiB shared disposable emptyDir/subpaths and 12 GiB ephemeral request/limit. Confirm old NFS/cache PVC definitions remain present to prevent Argo pruning rollback assets.
- [ ] Implement hold as a Git-managed replica count plus closed admission; a live scale patch is not sufficient. Suspend the known LDAP job in its manifest. Preflight all other pod/job references to the config claim and active Jellyfin API writers, and close ingress during the scheduled maintenance so clients cannot trigger writes during acceptance/rollback.
- [ ] Change config claim only in the target-held revision after valid native identities, sealed CHAP and successful cold restore exist. Initialize cache/transcode subdirectories with 1000:1000 ownership using the existing chart init-container convention. Exact chart keys must be rendered against globals/common/service layers, never assumed from a lab-only app.
- [ ] Release one pod only after Task 6 authorizes its placement. Acceptance requires exact Healthy body, catalog/users, plugins, watched/resume progress, direct play, hardware transcode, seek, new progress writes, and one clean move to the other worker. Preserve error logs and non-sensitive timing evidence, not media titles or user identities.
- [ ] Rollback tests must distinguish the moment the target first opens writable. After that, use a new cold target backup and a new NFS rollback directory/retained binding; reject an old-source-only rollback. Uncertain target writer requires fence before any source restart. Never auto-delete the ZVOL or old source.
- [ ] Run `python3 scripts/check-jellyfin-compat.py`, actual layered Helm rendering, kubeconform using workflow exclusions, targeted admission tests and pre-commit; commit drafts for the sequential transition. Do not merge them or perform the outage.

## Task 9: Qualification package and final independent review

**Files:** extend `docs/runbooks/jellyfin-storage.md` and `docs/superpowers/reports/2026-09-21-jellyfin-pilot-readiness.md`; update each PR body around its final change and exact current checks.

- [ ] Create a coverage table linking every approved design section to Tasks 1–8 and a concrete test/required live result. The following remain deployment gates, not unit-test claims: scoped-token authorization, diskless-VM cleanup, durable lock across real workflow containers, worker initiator setup, real NAS object identities, actual external cold restore, production playback/clean handoff and 24-hour observation.
- [ ] Run offline tests relevant to each repository, Ansible syntax/lint, Terraform fmt/init-without-backend/validate for any Terraform configuration touched, workflow tests and Apps renders/admission. Do not reconfigure live Terraform state just to validate workflow code. Distinguish a tool/access-blocked test from a passed one.
- [ ] Request one fresh whole-change review after inline implementation. Give the reviewer all PR diffs, the approved design, this plan, test evidence, the lock/receipt/placement interfaces and limitations. Fix critical/important findings with regression tests; record any minor deferrals. No per-task implementer agents unless the user changes the execution method.
- [ ] Publish and attach the new draft PRs. Their descriptions must say what a merge executes, what remains manually gated, which companion PR is prerequisite, and how to recover an interrupted maintenance operation. Keep secrets and backups out of all artifacts.
- [ ] Present a concrete next live operation for user approval only after its code and checks are reviewable. The first proposed production operation is the backed-up NFS sync correction, not Jellyfin cutover. Account setup/test-VM qualification follows as its own scoped operation; Jellyfin downtime is last.

## Operational acceptance ledger (not executed during PR preparation)

1. User merges reviewed prerequisite PRs in dependency order; verify their actual deployment effects.
2. Inspect fresh consistent backup/restore coverage of critical `apps/pv` databases, apply STANDARD once during the agreed window, verify NAS property and app/storage latency. No silent reversal to disabled.
3. Install worker initiators, establish the maintenance lock, create/qualify the scoped token with the disposable diskless VM, remove its temporary grants/VM and record cleanup.
4. Onboard the dedicated retained target once, seal real CHAP, capture identities and reconcile the held platform. Verify that current NFS Jellyfin remains unchanged until its scheduled hold.
5. During the Jellyfin outage, execute cold capture and independent restore, copy to target, verify, then release one writer. Record exact release/rollback revisions and proof of writer exclusivity.
6. Complete application acceptance, clean handoff and at least 24 hours of representative operation. Add an explicit snapshot schedule covering `apps/iscsi` before declaring ongoing protection; restore an independent backup of the new backend. Retain old data until a separate cleanup decision.

## Self-review result

The plan covers the approved design without treating code preparation as deployment. Explicit dependency corrections: backup coverage precedes applying the NFS sync change; real IDs precede deployable static bindings; placement authorization precedes any application writable target mount (explicit onboarding/copy is a separate held maintenance operation); fencing/clean unmount precedes cross-worker release. Failed/unknown operations remain held. The original lab branch is an evidence source only, and the current PostgreSQL backup fix is preserved. The backup destination is confirmed; no additional destination choice is required.
