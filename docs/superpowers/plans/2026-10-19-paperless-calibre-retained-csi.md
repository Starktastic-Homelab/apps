# Paperless and Calibre retained-storage implementation plan

> **For agentic workers:** Use superpowers:executing-plans for this authorized inline execution.

**Goal:** Complete the two remaining justified NFS-to-CSI migrations without losing native state or changing application/database identities.

**Architecture:** Reuse static Retain/RWOP Proxmox CSI bindings, one Recreate replica, verified VM retirement, fail-closed retained startup guards and the existing native maintenance lock. Keep Paperless documents/consume and Calibre books/ingest on their current NFS storage. Use stock pinned images and qualify Calibre's stock split-library support before selecting its final layout.

**Tech Stack:** K3s, ArgoCD, app-template, Proxmox CSI, NFS, Paperless/Tantivy, Calibre/SQLite.

**Spec:** User authorization on 19 October: “Let's do the 2 remaining migrations autonomously”; the preceding remaining-storage assessment defines the two targets. Autonomous preparation, scoped downtime, PRs, merges and native acceptance are included. New material trade-offs or credential boundaries require a decision.

## Constraints and review focus

- Preserve all records, account/password identities, keys, original files, ownership and modes. No production application credentials go to the workstation or synthetic lab.
- Keep the application image digests, PostgreSQL service/database, Redis durability and existing endpoints unchanged.
- No additional worker, CSI driver patch, dataset quota change or deletion of old sources is implied.
- Repeat native NAS full-growth checks, including retained images, 512MiB staging and 8GiB spare, before new image allocation. Start with one 1GiB Paperless volume and one 1GiB Calibre volume; qualify actual growth needs.
- Stop and verify every actual writer before copy; preserve source and target after an uncertain result. No copying over a partial target. Hold Filebrowser during source checkpoint/copy.
- Guards reject missing/wrong marker, redirected or empty retained paths and invalid native files before the stock image can initialize defaults.
- Calibre qualification must cover web access, import/conversion, metadata edits, covers, notes and enabled integrations, including helpers with fixed database paths. Do not mount SQLite files singly using subPath.

## Task 1: Paperless retained data

**Files:** `scripts/paperless-retained/guard.py`, its meaningful native/negative tests, `scripts/test-paperless-retained.py`, preparation bindings/ConfigMap, `infrastructure/base-configs/templates/paperless-data-block-storage/`, `services/operations/paperless-ngx/{values.yaml,manifests/}` and the validation workflow.

- [x] Capture fresh source Pod/controller/PVC/PV/Secret proofs, index/database identities, original document hashes, writable-overlap scope and native HTTP/query baseline.
- [x] Add rejection tests first; implement a small read-only guard for the retained marker, Tantivy metadata/settings/segments and native schedule state. Run exact-image synthetic index close/copy/reopen/query tests and actual chart-layer checks.
- [x] Prepare the static 1GiB target and current guard through a green reviewed PR without switching the app. Preserve the original NFS claim and its media/consume mounts.
- [x] Prepare and independently review the finite live command package. Obtain green activation CI before downtime. Under native maintenance ownership, hold reconciliation/frontends, stop Paperless/Filebrowser, verify guest runtime/mount retirement, mark the exact cold source, copy and verify bytes/POSIX metadata into the fresh target.
- [x] Require native recovery checks before target application startup, then merge exact green activation. Qualify current native document/index/model and queue behavior, clean recreation and both-worker startup. Restore normal scheduling, frontends, Filebrowser and Git/live equality; remove only owned holds and release maintenance ownership.

## Task 2: Calibre stock split-library qualification and delivery

**Files:** `scripts/calibre-retained/` native qualification/guard files, a focused test, prepared bindings and guard manifests, `services/media/calibre-web/values.yaml` and relevant workflow validation.

- [x] Rehearse the exact image on synthetic isolated volumes with config/SQLite state separated from book files. Inspect all five existing native databases and enabled integrations without exporting credential values.
- [x] Prove web reads, book import and conversion, edits, covers, notes, restart and every enabled integration use the intended paths. Report a decision if stock behavior cannot meet the split contract.
- [x] After qualification, implement and review minimal static bindings, retained/native guard and split settings. Preserve whole database directories so journals remain on CSI. Obtain green activation CI before downtime.
- [x] Perform a separately owned cold checkpoint/copy, read-only integrity and row/account/key proofs, recover and exercise native functionality, then exact green merge and both-worker acceptance. Keep books/ingest on NFS and old sources retained/held.
- [x] Finish with current native checks, unchanged unrelated controller proofs, Git/live equality, healthy monitoring, attachment count/capacity checks and exact temporary cleanup. Record completion on the merged PRs and in this plan.

Paperless completed through PRs #1411 and #1412. Both workers and final native acceptance passed; all 78 Argo applications are Healthy/Synced, 95 unrelated controllers are unchanged, 32 CSI attachments leave 26 usable slots, capacity alerts are healthy and the maintenance owner/temporary holds are removed. Original NFS data remains retained and held.

Calibre completed through PRs #1413 and #1414. All five native databases, accounts/settings/key, book bytes and author notes passed initial, other-worker and final clean startup checks. Books and ingest remain on NFS; the original configuration and metadata/notes are retained. All 78 Argo applications are Healthy/Synced, 95 unrelated controllers are unchanged, 33 CSI attachments leave 25 usable slots, capacity alerts are healthy and maintenance ownership/temporary helpers are removed. See the [completion report](../reports/2026-10-19-paperless-calibre-retained-csi.md).
