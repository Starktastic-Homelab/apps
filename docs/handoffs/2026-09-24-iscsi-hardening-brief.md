# Retained iSCSI hardening: scope for the original task

This is a working brief and evidence-backed audit starting point, not an approved implementation design or a new maintenance authorization.

## User direction

Keep iSCSI work in the original task. Generalize and strengthen the existing platform, remove brittle operational glue, and clean up before migrating another service. PostgreSQL eligibility/migrations have a separate handoff. Preserve the ability to destroy/recreate k3s from Packer/Terraform and deliberately rebind retained application state.

## Starting point

Read current apps main, not the older user checkout. As of September 24, main was `5de6a10c1e84f1f6b8dc71e8eb2f1d5598441c69`. Review `scripts/storage/`, its tests, `storage/services/`, retained-iscsi infrastructure/admission configuration, plus the actual current Ansible runner/maintenance code and Packer/Terraform prerequisites.

Jellyfin is the working pilot on worker01. Backup, independent restore, clean handoff and public acceptance passed. Its intermittent SQLite application error remains a separate open finding; do not call the entire application pilot clean or redesign storage around an unproven cause.

## Observed engineering gaps

- The committed maintenance CLI contains a Jellyfin-specific root, deployment/CronJob assumptions and fixed cache budget. Separating shared volume operations from application acceptance is necessary before a second service.
- Successful operations also depended on `/tmp` launchers, copied source trees, embedded Python/SSH snippets and manual canonical placement/stage updates. These are evidence to inventory, not code to promote wholesale.
- Laptop restart removed ephemeral access helpers. A preserved bundle recovered the operation, but supported recovery should not depend on chat history or remembering which script copy is authoritative.
- A long capture was terminated with SIGTERM after a command-session lifetime; the cause was not conclusively established. A supervised service completed it. Long-running work needs durable execution/exit evidence independent of the initiating chat/tool session.
- An unrelated main-branch merge invalidated the exact-revision capture guard. Preserve relevant-object identity checks while designing how unrelated Git changes can be safely distinguished; do not simply weaken the guard.
- Runtime qualification initially covered Python/backup dependencies but missed SSH for release verification. The missing client was found in the maintenance window. Qualify every operation's dependencies and immutable runtime before downtime.
- A private access wrapper hid diagnostic stderr on failure. Reconciliation remained possible through remote receipts, but operators need sanitized actionable errors and discoverable private logs.
- Manual receipt writing/staging caused recoverable empty-file/permission mistakes. Stable public interfaces should own receipt formats, atomic writes and evidence placement rather than callers using private helpers.
- A simple HTTP 200 readiness check proved insufficient in a disposable test; the correct gate requires body Healthy. Preserve semantic checks.

## Proposed order of work

1. **Inventory and classify.** Identify canonical supported commands, temporary pilot tools, credentials/state/evidence, active resources and abandoned artifacts. Produce a keep/consolidate/retire list with ownership and references. Review tests before adding abstractions.
2. **Define the operator contract.** A small maintained entry point with explicit service/operation/state location, read-only status/preflight, supervised execution and inspection/reconciliation after interruption. Choose repository ownership and execution host deliberately; reuse working code and standard platform facilities.
3. **Durable operations.** Versioned state/receipts, immutable identity records, restrictive credential handling, accurate exit status, timeouts, signal behavior and recovery after controller/runner/network interruption. A new operator should resume from checked-in documentation and durable state, without ad-hoc Python or secret output.
4. **Parameterize only established variability.** Service/namespace/workload identity, application hold/release hooks and resource budgets; shared native volume/CSI identity verification underneath. Keep Jellyfin-specific backup/health/media acceptance explicit. Avoid building a plugin framework or provisioning controller without a demonstrated need.
5. **Qualify failure paths.** Lost replies, partial archives, main drift, ownership loss, changed node/namespace identity, existing sessions, failed unmount, missing tools, runner restart and stale authorization. Rehearse destruction/recreation/rebind in an isolated environment before claiming stateless-cluster recovery. A worker handoff alone does not prove rebuild recovery.
6. **Retire glue and refresh docs.** Remove redundant source only after replacements are tested and references updated. Preserve historical receipts, snapshots and backups. Storage/data/VM deletion is a separate reviewed cleanup decision.
7. **Expansion gate.** Only after the operator contract works for Jellyfin and an inert second service fixture, with interrupted-operation recovery and clean rebuild/rebind rehearsal, choose the next real SQLite workload.

## Safety invariants to retain

External original-owner maintenance lock; fail-closed writer authorization; exact pool/ZVOL/export/device/filesystem identity; worker and namespace generation checks; RWOP/Retain/static binding; proven old-writer quiescence or separately authorized fencing; fresh CHAP/CSI verification; owned mount/session cleanup; no logout beneath a mounted filesystem; no automatic formatting, repair, rollback, recreation or replacement target; permanent first-write boundary; independent verified backups; user-controlled GitOps rollout.

Separate enrollment from normal recovery. Do not infer that a missing object should be recreated. Lost replies require readback/reconciliation, not blind retries. Do not release the original production lock or migrate the active record format until compatibility/recovery is explicitly designed and verified.

## Current operational boundary

Production is healthy and public, on Jellyfin pod UID `f7a8eee6-62d7-4789-b74c-e94374c956c0` on worker01 when last checked. Native record SHA-256: `6515cd395753fde8bb5e4a29533d1efcc9a8d9407548b49e9957cc997d3ad5e6`. These are historical reference values; all mutation gates require fresh live verification.

Runner operation: `/var/lib/homelab-maintenance/operations/jellyfin-migration-20260922T055644Z` under the original ownership. Preserve canonical `/var/lib/homelab-maintenance/operations/jellyfin` records, first-write evidence and private credentials. Do not change them during audit/design.

Evidence roots on encrypted local storage:
- `/home/benf/Backups/homelab/jellyfin/20260923T113854Z-window-state`
- `/home/benf/Backups/homelab/jellyfin/20260923T113854Z-cold-target-supervised`
- `/home/benf/Backups/homelab/jellyfin/20260924-observation`
- `/home/benf/Backups/homelab/jellyfin/20260924-contention-investigation`
- `/home/benf/Backups/homelab/jellyfin/20260924-mixed-replay-evidence`

The mixed replay data directory is a disposable modified copy, not an accepted recovery archive. Old NFS data is stale. Cleanup of either must never accidentally select live state or destroy the accepted archives.

## Immediate deliverable here

An audit and a concise written design identifying what stays, what becomes a supported interface, what can be deleted, where durable state lives, and the first small PR. No new service migration, production restart, image upgrade, NAS mutation or data deletion is part of this preparation.
