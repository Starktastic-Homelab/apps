# ntfy PostgreSQL and retained CSI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve ntfy state while replacing NFS-backed SQLite with shared PostgreSQL and retained CSI attachments.

**Architecture:** Use the pinned upstream importer and stock schema upgrade only after full data qualification. Reuse shared enrollment/completion, native maintenance and the accepted scoped live-cutover workflow; reconcile final live state through reviewed CI-green PRs.

**Tech Stack:** ntfy2.29.0, PostgreSQL18.6, Python standard library, existing PyYAML/Paramiko, Docker, Helm, Kubernetes/ArgoCD, Proxmox CSI.

**Spec:** docs/superpowers/specs/2026-10-15-ntfy-postgresql-csi-design.md

## Global Constraints

- Preserve all original data/identity; exact pinned stock app and importer; no schema-marker rewriting, credential rotation or upstream patches.
- Reuse existing shared PostgreSQL/enrollment and maintain every prior encrypted credential unchanged.
- Target static8GiB ext4/RWOP/Retain `ntfy-data-block`, image `k3s-block:9999/vm-9999-ntfy.raw`, marker `homelab/ntfy/data/v1`.
- Fresh quota reserves full existing growth +new8GiB +0.5GiB staging +8GiB headroom under160GiB quota.
- Keep credentials and private copies outside Git; local internal-network lab has fixture SQL credentials, no administrator credentials, no external push delivery.
- Original90minute pre-start/180minute finish monotonic clock; failed operations retained, never replayed or reset.
- Independent fresh whole-branch review before production; only current exact-head successful CI permits authorized merge.

## Review Focus

1. Newer user_email/user_magic_link rows omitted by stock importer: compare every source table and stop if nonempty state is lost.
2. Invalid text, NULL/boolean conversion, statistics and skipped source files: compare full typed content and negative cases; never accept import success alone.
3. Existing token/password/VAPID identity and allow/deny ACLs: private functional probes without notifying real subscribers.
4. Missing/wrong retained data and metadata rebuild: guard and actual layered rendering must fail before empty initialization.
5. Transport uncertainty/partial failure: immutable inputs, native child identities, exact reconciliation, no repeat allocation/import or outage-clock reset.

### Task1: Qualify conversion against consistent current copies

**Files:** Private `.superpowers/sdd/2026-10-15-ntfy-postgresql-csi/`; public sanitized report under `docs/superpowers/reports/`.
**Interfaces:** Input `readonly-inventory.json` and pinned upstream source; output full typed source/PG proof, stock version/schema contracts, independent restore proof and exact lab identities.

- [ ] Read exact stock importer/store migrations; record supported fields, omissions and text transformations.
- [ ] Create consistent read-only SQLite backups in memory on identified NAS; transfer only compressed backups privately to this computer. Record hashes, schemas, counts and auth secret fingerprints, never values in output.
- [ ] Build the unmodified pinned importer; run exact ntfy/PostgreSQL images on an owned internal Docker network with fixture SQL passwords and private source mounts.
- [ ] Import into empty stockinitial PG schemas, permit stock upgrades, then independently compare all typed fields/tables, statistics and file metadata. Reject data loss and unexpected omitted state.
- [ ] Restart/recreate stock ntfy and independently restore its dump into fresh PG storage; test fixture auth/token/ACL/private publish/poll without external egress.
- [ ] Publish sanitized qualification evidence; exact cleanup removes only owned lab resources/copies when no longer needed.

### Task2: Prepare retained runtime, enrollment and executable cutover

**Files:** `scripts/ntfy-postgresql/`, `scripts/test-ntfy-retained-startup.py`, inactive production fragments; later active ntfy values/manifests and base-configs PV/PVC; relevant CI step and runbook.
**Interfaces:** Consume qualified schema/data contract; produce generated sealed enrollment bundle, completion/login checks, fail-closed retained guard, rendered runtime and finite reviewed command phases.

- [ ] Write failing tests for absent/wrong marker, SQLite fallback, wrong PG physical identity/schema, missing current completion, and fresh layered render; run RED before implementing the minimal guard/SQL.
- [ ] Reuse shared enrollment preparation with sealed URL key; append ntfy once without changing prior entries/ciphertexts. Generate no replacement credentials on retries.
- [ ] Generate inactive retained PV/PVC/guard/gate/source policy and exact layered rendering. Implement command preflights and phase intents/terminals using established native primitives and prior transport fixes.
- [ ] Test in representative containers: all helper/stock commands, actual server dry-run defaulting, whole JSON transport, metadata restore witnesses and deadline/no-replay failures before production.
- [ ] Run relevant unit/render/schema/precommit checks; commit. One fresh reviewer checks whole branch, preservation evidence and production command package. Fix real blockers with regression tests.
- [ ] Publish/merge enrollment-only PR after current-head CI/diff review. Prepare activation PR for CI in advance without merging it before live acceptance.

### Task3: Execute and reconcile production

**Files:** Private immutable per-operation inputs/receipts, final active app declarations and `docs/runbooks/ntfy-storage.md`.
**Interfaces:** Consume reviewed immutable commands and accepted latest cold source; output full live/restore/backup/current-main acceptance and cleanup evidence.

- [ ] Fresh native maintenance identity/resource/writer/PG/quota/headroom preflight; acquire owner/executor and scoped Argo hold; start original outage clock with writer shutdown.
- [ ] Exact writer retirement, cold backup/encryption and independently accepted latest cold restore; resume ancestor writers when safe.
- [ ] Allocate absent8GiB image, establish exact binding/WWN/FSUUID and populate retained attachments/marker; initialize/import target once and compare all current source data, then verify fresh physical SQL restore and encrypted copies.
- [ ] Before first authoritative startup, retire helper/runtime/mount and persist irreversible boundary. Start ntfy; verify preservation, authorization and private no-subscriber publish/poll.
- [ ] Prove clean recreation and healthy worker movement, unchanged physical retained identity and old runtime/mount retirement; restore scheduling.
- [ ] Run/verify complete unchanged backup template; merge exact tested activation head; prove final desired/live equality, resolve only captured held queues, release own hold and observe6minutes.
- [ ] Remove owned helpers/lab/plaintext only, preserve encrypted recovery/old source, release owner and verify final Healthy/Synced/Bound/runtime identity. Record completion and report affected apps/checks/any limitations.
