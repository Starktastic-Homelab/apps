# Media retained CSI implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline. One independent whole-package review before production; no per-task delegation.

**Goal:** Complete the ten requested private-state migrations with unattended rebuild recovery.
**Architecture:** Existing unmodified CSI, static ext4 RWOP/Retain, stock images, native ownership/receipts, scoped Argo holds and final Git reconciliation.
**Tech Stack:** app-template5.2.1, Kubernetes1.37, Python standard library, installed native maintenance runtime and exact pinned application images.
**Spec:** docs/superpowers/specs/2026-10-17-media-retained-csi-design.md

## Global Constraints

- Preserve settings, users, keys, library/progress/history, images and existing shared media/ingest interfaces.
- No source writes from analysis, no forced detach and no unqualified database conversion.
- Exact fixed4Gi images; full committed raw growth plus staging/headroom and pool physical capacity accepted first.
- All sensitive copies private outside Git; complete encrypted recovery on VM300 and this computer, separate keys.
- Before-intent, native exclusive owner, exact child terminals, original clocks and no replay after uncertain submission.
- Exact-head CI and reviewed Argo diff before autonomous merges; live acceptance is a separate gate.

## Review Focus

- RU variants must not inherit the base instance's claim or identity through the value cascade.
- Two Cineplete claims and Audiobookshelf's container-only metadata must not disappear when the source Pod is retired.
- Startup guards must run as actual app consumers and reject wrong/empty/linked state without changing WAL or SQLite.
- Offline background scanners must not mutate preserved library state because production media is absent.
- Owner/phase failure, source overlap or transport timeout must preserve evidence and prevent replay/dual writers.

### Task 1: Current assessment and concrete native state contract

**Files:** spec/plan, docs/superpowers/reports/2026-10-17-media-assessment.md; private inventory workspace.
**Interfaces:** Produces exact app engine/image/UID/mount/source/API contracts and capacity/VM identities for Tasks2/3.

- [x] Read current sources, source sizes/POSIX features, actual process users, service identities and owning Apps.
- [x] Verify primary exact-version data/backup contracts and record Cleanuparr's selected separately rehearsed PostgreSQL conversion.
- [x] Pin preserved paths, two-volume mappings, consumer users and safe offline scanner handling.

Run: native read-only assessment scripts and primary-source contract checks.
Expected: ten current single writers identified; all source paths accounted for; no production mutation.

### Task 2: Inactive retained resources and guarded native command package

**Files:** scripts/media-retained/guard.py, production/*; scripts/test-media-retained.py; scoped CI; private native packet.
**Interfaces:** Consumes Task1 paths/UIDs; produces exact guarded desired manifests and immutable staged backup/restore/activation/lifecycle operations for Task3.

- [x] Write refusal/acceptance tests for missing/wrong/linked markers, paths and SQLite headers, watch RED, implement minimal read-only guard, watch GREEN.
- [x] Render real common/base/variant layers; test distinct claims, image/probe/media equivalence, Recreate, token exclusion, guard UID and RO mounts.
- [x] Reuse qualified native ownership/file/POSIX/encryption/physical fencing primitives; test before-intent/no-replay/known-terminal and capacity negative paths.
- [x] Qualify exact stock-image offline recovery with unchanged original copies, postponed fixture-only scans and bytes-safe complete SQLite row proofs.
- [x] Freeze packet; one independent final review; fix Important/Critical findings RED to GREEN and run relevant repository checks.
- [x] Publish preparation PR and merge on exact-head green CI plus intended-only Argo diff under user autonomy.

Run: python3 scripts/test-media-retained.py, relevant full existing checks, exact layered Helm/kubeconform and isolated native operation qualifications.
Expected: all refusal/positive gates and original engines pass; live source remains NFS until Task3.

### Task 3: Serialized live cutovers and final reconciliation

**Files:** scoped service app/values/manifests; infrastructure/base-configs/templates/media-block-storage/*; docs/runbooks/media-storage.md; sanitized production report.
**Interfaces:** Consumes frozen package, current cold restore acceptance and native owner; produces accepted retained filesystems, current-main healthy runtime and protected recovery/cleanup evidence.

- [x] Acquire fresh native owner, immutable original operation/app clocks and Argo holds; recheck images, nodes, Secrets and full committed capacity.
- [x] For each app, protect source, capture ABS metadata when applicable, stop/physically retire every source writer, cold snapshot/archive/encrypt and independently restore native state.
- [x] Allocate/populate exactly once, verify complete file/POSIX proof, marker and physical identity; no fixture-mutated data enters target.
- [x] Merge reviewed activation definitions under hold before target writers, using exact-head checks and diff; activate each accepted target.
- [x] Verify preserved native API/DB state, stock startup, recreation, movement and final placement on the same FSUUID with zero unplanned restarts.
- [x] Safely release full current-source syncs preserving all options, watch six clean minutes and verify all affected Apps Healthy/Synced.
- [x] Encrypt audit, remove exact owned transient copies/helpers/labs, release owner last and merge sanitized recovery/completion evidence; retain sources/targets/backups/keys.

Run: frozen native phases once; native acceptance/watch/cleanup and exact-head Git/Argo checks.
Expected: all requested apps accepted on retained CSI; no source rollback after authority; no unrelated workload change.
