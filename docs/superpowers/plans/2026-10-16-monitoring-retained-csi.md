# Monitoring retained-CSI implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline. One independent final review of the complete native package precedes production; no per-task delegation.

**Goal:** Preserve all four monitoring services on static retained CSI with ordinary unattended rebuilds.
**Architecture:** Reuse the current unmodified Proxmox CSI, verified retirement, native owner, scoped Argo holds and final Git reconciliation. Keep stock data engines and qualify recovery before authority.
**Tech Stack:** Prometheus3.15.0, Alertmanager0.34.1, Operator0.94.1, Loki3.6.11, Tempo2.9.0, Helm and existing Python tooling.
**Spec:** docs/superpowers/specs/2026-10-16-monitoring-retained-csi-design.md

## Global constraints

- Preserve source, all history/state, image/configuration/retention, credentials and service endpoints.
- No unapproved data-loss exception, chart fork, controller/driver change or production notification test.
- Retained ext4/RWOP/Retain disks, exact physical identities and verified old-writer retirement.
- Sensitive copies private outside Git; encrypted durable recovery and separate keys retained.
- Exclusive native ownership, no replay after intent, explicit authority boundary, original per-operation clock.
- Exact-head hosted checks and desired/live equality before releasing the owned hold.

## Review focus

- Operator reconstruction must use the intended deterministic CSI claims after fresh metadata rebuild.
- Scale-down/deletion must not delete Loki's existing claim through chart auto-delete defaults.
- Guards must reject missing/wrong retained state before an empty native database can start.
- Restore readiness alone must not conceal WAL loss, missing blocks, traces, silences or historical queries.
- Held queue replacement must retain every syncOption and must preserve Grafana/monitoring Secrets.

### Task 1: Current assessment, recovery interfaces and adapter decision

**Files:** spec/plan, docs/superpowers/reports/2026-10-16-monitoring-assessment.md; private inventories/rehearsals under this plan workspace.
**Interfaces:** Live source/owner/capacity/version identities and exact current charts become the input contract for startup guards, bindings and native operations.

- [x] Read-only current engine/image/binding/owner and capacity inventory; classify historical warnings separately.
- [x] Confirm stock chart/operator claim naming, subpaths, deletion policy and initialization extension points.
- [x] Render a concrete equivalent Tempo app-template alternative and obtain the deployment-path decision.
- [x] Qualify stock native isolated recovery and historical/API comparisons using consistent source copies.
- [x] Record exact preserved state and any genuine limitation; do not inherit the narrow old Loki exception.

Run: native assessment/recovery checks with exact images and isolated destinations.
Expected: all recovered files and native data checks pass; no production mutation or unapproved transfer.

### Task 2: Inactive static bindings, startup guards and native operation package

**Files:** scripts/monitoring-retained/{guard.py,production/*,README.md}, scripts/test-monitoring-retained.py and scoped CI; ignored native package.
**Interfaces:** Consumes Task1 accepted native data/paths/adapter; produces read-only guards, deterministic static PV/PVCs, source admission holds and immutable native operation stages.

- [x] Write guard refusal tests first: wrong/missing marker, missing native data, symlink/path escape, read-only accepted input; observe RED.
- [x] Implement minimal shared file identity guard plus app-specific native structure validation.
- [x] Render exact layered sources and native operator-generated claims; test mount order, retained source, fixed images/credentials and no unrelated changes.
- [x] Prepare protected ownership, bounded original clock, cold backup, file/POSIX roundtrip, native restore, full-growth allocation, physical fencing, authority, lifecycle and cleanup stages.
- [x] Rehearse cancellation, known failure and exact recovery without replay; freeze exact packet and obtain one independent final review.
- [x] Fix verified important findings RED→GREEN, then publish preparation with all exact-head checks and reviewed intended-only diff.

Run: python3 scripts/test-monitoring-retained.py plus actual layered render/kubeconform and native isolated package qualification.
Expected: all positive/negative gates and exact native adapters pass; runtime stays on original NFS until production execution.

### Task 3: Serialized cutovers, Git reconciliation and protected cleanup

**Files:** scoped three service values/app/manifests, infrastructure/base-configs/templates/monitoring-block-storage/*; docs/runbooks/monitoring-storage.md and sanitized completion report.
**Interfaces:** Consumes frozen reviewed package/current source recovery and fresh native identities; produces native accepted retained disks, healthy current-main GitOps runtime and durable encrypted recovery.

- [x] Acquire fresh owner/hold, pin original deadline and preserve credentials/owners; recheck full growth/physical space before scoped quota192Gi and allocations.
- [x] For each app, stop/retire every source writer, cold archive/encrypt and independently restore current files/native state before target authority.
- [x] Allocate/populate exactly once and prove physical identity; start target with guards only after helper/old writers retire.
- [x] Accept historical/current APIs and data, clean recreation and healthy-worker movement; restore default placement and overlapping services.
- [x] Merge reviewed desired values/bindings under the owned hold before the first target writer, on exact-head green checks; after every app passes acceptance, safely release full current-source sync preserving all options and observe six clean minutes.
- [x] Encrypt audits, remove only exact owned temporary API/guest/NAS/runner/lab plaintext and release owner last.
- [x] Publish final sanitized report/runbook and prepare the post-merge final audit and exact private-working cleanup. Retain source/CSI/recovery and separate keys; the final terminal is recorded outside Git after merge.

Run: each immutable native stage exactly once under its original owner/clock; final paired acceptance receipts and exact cleanup.
Expected: all four native data/lifecycle gates and all scoped Argo apps healthy/synced, no fresh restarts or loss, full recovery and owned cleanup accepted.


## Completion evidence

See the [production report](../reports/2026-10-16-monitoring-production-completion.md).
The exact normal Prometheus retention expiry is explicitly approved and recorded
in the design amendment. Local/hosted checks qualified the implementation; actual
cold recovery, native history/ingestion, all lifecycle checks, full current-source
syncs, continuous six-minute watch and native protected cleanup passed separately.
The prepared final local audit/working cleanup runs only after this report merges.
