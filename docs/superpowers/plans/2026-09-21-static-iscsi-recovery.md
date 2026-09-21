# Static retained iSCSI recovery implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline. The user accepted the static storage direction and authorized continuing the isolated rehearsal. Preserve completed evidence; production migration and merges remain separate decisions.

**Goal:** Demonstrate recovery without a NAS-management credential in Kubernetes or implicit volume initialization.
**Architecture:** Stock node-manual CSI mounts explicitly recorded, externally managed iSCSI volumes. TrueNAS WebSocket operations and identity receipts remain outside the disposable cluster. Actual Argo and Sealed Secrets restore declarative bindings and credentials before writers are released.
**Tech Stack:** TrueNAS25.10.7, democratic-csi1.9.5, K3s1.37.0+k3s1, Python, Helm, Argo, Sealed Secrets, ext4 and SQLite.
**Spec:** ../specs/2026-09-21-static-iscsi-recovery-design.md

## Global Constraints

- No production storage mutations, application migration, PR merges, or further production RAM changes.
- Reuse only the approved VM IDs910–913, RAM8192/2048/1024/1024MiB, fresh names/UUIDs/tag, private bridges and50GiB disk ceiling. Require20GiB host available and130GiB vm-pool free before allocation; leave80GiB afterward.
- Production nodes must be Ready without pressure and all active applications converged before adding lab load. Stop runner300 only after proving it idle; restore it during cleanup.
- Use the corrected repository guard, not old temporary scripts with embedded code. Prepare ownership-checked cleanup before creating resources.
- No default kubeconfig for lab operations. No production credentials or disks in guests. Preserve private receipts and keys outside the disposable cluster, never in Git.
- Never-format is a test obligation, not an upstream feature claim. Reject wrong native identity and filesystem before allowing writers. Failure stops the candidate rather than relaxing acceptance.

## Review Focus

- Missing or replaced filesystem: blank-media hash must remain unchanged; wrong native identity must fail before a writable mount.
- Lost NAS mutation response: query recorded identity; no second allocation or unrecorded target.
- Lost sealing key or wrong CHAP: recovery stays held, never creates an empty replacement claim.
- Stale VM identity or failed fence: replacement stays blocked while an old writer might exist.
- Partial resize or cleanup: reconcile verified native state; never expand/delete by name alone.

### Task 1: Prove the stock-image safety candidate

**Files:** tests/static-iscsi/format-probe.js; tests/static-iscsi/README.md; reports/evidence/2026-09-21-static-format-probe.json.
**Interface:** pinned stock image, regular disposable files, whole-file SHA256 evidence; no host block devices.

- [x] Verify post-upgrade production: three Ready nodes,125/125 ready pods,77/77 healthy/synced applications,68/68 original bindings,38/38 sealed secrets,7/7 certificates.
- [x] Exercise stock Filesystem.formatDevice with a normal-format positive control, then `['-m','0','-n']` on zero and unrecognized byte patterns. Require normal control changed/type ext4 and both guarded hashes unchanged/no filesystem signature.
- [x] Preserve the reproducible probe and evidence; distinguish helper success from actual NodeStage acceptance.
- [x] In the isolated guest, run actual node-manual NodeStage against a blank lab LUN; require a failed stage and unchanged whole-device hash. Check an existing ext4 volume still mounts. If either fails, record the blocker and clean up.

```sh
docker run --rm --user "$(id -u):$(id -g)" --network none --cap-drop ALL \
  --security-opt no-new-privileges --read-only \
  --mount type=bind,src="$probe_dir",dst=/probe --entrypoint node \
  ghcr.io/democratic-csi/democratic-csi:v1.9.5@sha256:746bf6b373ae75f5da8b1e412d13c3e8d0e2e1494654268b9dd6fe1f1e55aade \
  /probe/probe.js
```

### Task 2: Build the bounded25.10.7 fixture and external lifecycle

**Files:** tests/static-iscsi/ fixture scripts; reuse tests/iscsi-platform/guard.py and host_setup.py without modifying historical evidence.
**Interface:** new private manifest with exact VM ownership; versioned read-only identity record and fsynced operation receipt.

- [x] Download25.10.7 official ISO/checksum and pinned offline node/controller inputs. Recheck capacity before allocation; verify checksum again after transfer.
- [x] Prepare fresh cleanup, run the existing guard suite, install guard, create isolated network and stopped VMs; validate UUIDs, disks and NICs before boot.
- [x] Install NAS, node guests and pinned K3s; prove production addresses unreachable from guests. Only lab API credentials are allowed.
- [x] Provision two synthetic volumes over WSS once, with CHAP and exact initiator ACLs. Capture pool/ZVOL GUID, extent ID/serial/NAA, target ID/IQN, portal/LUN, size, filesystem UUID/type and service marker.
- [ ] Test changed/missing native identities and simulated lost responses before implementing read-only reconcile. Reconcile existing objects after interrupted responses; no blind allocation retries.

```sh
python3 -m unittest discover -s tests/iscsi-platform -p 'test_*.py'
```

### Task 3: Recover with actual Argo and Sealed Secrets

**Files:** tests/static-iscsi/ declarative manifests, identity policy, external recovery evidence.
**Interface:** explicit Retain PV/PVC, nodeStageSecretRef, unpartitioned ext4, no dynamic storage class/controller, writers held until identity check.

- [x] Render pinned node-manual with `controller.enabled: false`, `node.format.ext4.customOptions: ["-n"]`, filesystem checks disabled. Inspect final chart resources for unintended provisioner, API credentials or mutation controller.
- [x] Install actual Argo and Sealed Secrets; preserve a dedicated lab sealing key externally. Put CHAP only in a SealedSecret. Reconcile from a lab Git source containing nonsecret records and encrypted manifests.
- [ ] Exercise server-side rejection of alias PVs, foreign/dynamic claims, non-Retain deletion, changed storage identity and substituted driver/fsType. Missing key and wrong CHAP must leave writers held.
- [x] Initialize each synthetic SQLite dataset once and record exact acknowledged values outside the cluster. Normal application startup requires an existing DB/service marker.
- [ ] Destroy/recreate only the three owned K3s VM disks twice. Restore the sealing key, Argo source and existing bindings; prove new CAs/object UIDs, unchanged NAS/filesystem identities and every acknowledged SQLite value. Verify Argo deletion/prune retention and native volume count.

### Task 4: Writer, maintenance and restore failure cases

**Files:** tests/static-iscsi/ failure probes and sanitized evidence.
**Interface:** exact-UUID external power fence; explicit maintenance receipts; independent backups outside NAS.

- [x] Verify RWOP contention and clean movement, then disconnect only an owned worker control NIC while storage remains reachable. Record witness writes.
- [ ] Inject stale UUID, failed fence and timeout; require replacement held. Only after exact VM power-off confirmation remove stale pod objects and release a replacement.
- [ ] Snapshot and restore to distinct authenticated targets over WSS; verify CHAP/ACLs and source identity unchanged, with wrong credentials/initiator rejected.
- [ ] Quiesce/unmount and interrupt expansion after NAS growth, initiator rescan and filesystem growth. Reconcile each from observed native state, then prove actual Argo PV/PVC capacity convergence and retained values.
- [ ] Restore externally captured backups to separate storage while lab NAS is verified off; verify integrity and exact backup-time values.

### Task 5: Cleanup and delivery

**Files:** reports/2026-09-21-static-iscsi-recovery.md; source, sanitized evidence and this ledger.

- [ ] Stop writers, validate current exact VM ownership/disk identities, delete only the run's VMs/disks/bridges/firewall/transient services/downloads and private artifacts.
- [ ] Restore runner, compare original production identities/storage and health; reconcile host memory/storage headroom.
- [ ] Run relevant local checks and one fresh whole-branch review, fix important findings with regression tests. Update the existing draft PR with passed/failed/untested gates. Do not claim production acceptance from incomplete lab evidence.

## Execution ledger

- 2026-09-21: production NAS reports25.10.7. Reboot recovery converged fully; no storage-binding mismatch.
- 2026-09-21: stock-image regular-file probe passed the positive control and both no-write cases. This does not yet establish NodeStage safety.
- Ruling: retain the user-approved inline execution and lab boundaries; this plan records the accepted continuation without another approval cycle. Cost if wrong: isolated fixture work may need revision; no production migration is authorized.

- Actual blank NodeStage passed: stock command`mkfs.ext4 -m 0 -n`, subsequentblkid exit2, no mounted writer and unchanged128MiB SHA256254bcc3fc4f27172636df4bf32de9f107f620d559b20d760197e452b97453917. Evidence saved separately.
- TrueNAS25.10.7 lab and three Ready K3s nodes installed;9/9 production reachability probes blocked. Guard production_ok remained true. Three CHAP-protected lab LUNs created with exact initiator ACLs; two explicitly initialized ext4 filesystems recorded externally.
- Native identity checks:8 test methods pass, covering replacement, ambiguity, redirected mappings, changed capacity, authentication/ACL weakening and disk serial selection. Live read-only verification passed for all3LUNs; both service filesystem UUIDs also matched.
- Actual Argo core3.5.3 and Sealed Secrets0.40.0 are healthy. Real CHAP SealedSecret decrypted. Stock CSI node plugin4/4ready on each node; no NAS API credential in Kubernetes.
- Ruling: remove only checksum-matched redundant image archives from guest disks, retaining seed media and external copies. This cleared transient lab DiskPressure without increasing the50GiB disk envelope. Cost if wrong: image restoration would require the externally preserved seed.
- Ruling: use the stock Git daemon from the already pinned Argo image for the isolated Git source; Argo's ref-listing failed on dumb HTTP even though Git CLI succeeded. Cost if wrong: lab synchronization remains blocked; no production repository is modified.
- Git includes admission that denies service writer Pod creation unless a separate external verification ConfigMap matches the current namespaceUID. The verification object is deliberately absent from Git; restores cannot replay an old cluster's release authorization.

- Clean drain and RWOP contention passed. During a control-NIC-only partition both services acknowledged a witness write. Stale UUID and unauthenticated Proxmox fence were rejected; admission blocked replacement until exact-UUID VM913 power-off. Replacements recovered11/11 acknowledgements per service, then added5each.
- Before rebuild1:125/125 production pods Ready,77/77 applications Synced/Healthy,68 original bindings unchanged,38/38 SealedSecrets and7/7 certificates healthy.
- Rebuild1 paused before deletion on graceful worker shutdown timeout; exact-owned disposable workers are explicitly fenced before their OS disks are replaced.
