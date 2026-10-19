# CSI narrowing and ntfy recovery implementation plan

> **For agentic workers:** Use superpowers:executing-plans for this authorized inline execution.

**Goal:** Restore ntfy and remove CSI attachment use where native application semantics allow ordinary shared files.

**Architecture:** Keep databases, local transactional stores and their recovery fencing on retained CSI. Qualify ordinary-file directories individually for retained NFS; detachable old images remain recovery sources. Use the existing GitOps cascade and upstream applications unchanged.

**Tech Stack:** ArgoCD, app-template, PostgreSQL 18, Proxmox CSI, NFS.

**Spec:** User authorization on 19 October: continue autonomously with narrowing CSI usage and the ntfy issue; preserve state and reconcile desired state through PRs.

## Constraints and review focus

- Two workers; stock CSI, 29 usable attachments each. No third worker or driver fork.
- Preserve credentials, application identities, PostgreSQL enrollment and physical database checks.
- No production database DDL for the ntfy repair. Accept only exact qualified schema transitions.
- Ordinary files alone do not prove NFS safety: inspect actual cache backends, locking and durable paths.
- Do not reopen stale pre-PostgreSQL SQLite sources, delete retained data or share a RWOP claim across independent Pods.
- Each storage cutover needs a cold copy, verification, rollback source, native app checks and restart/movement acceptance.

## Task 1: Restore ntfy

- [ ] Reproduce the SQL rejection read-only and compare the catalog with pinned upstream migration SQL.
- [ ] Add native PostgreSQL regression tests for schemas 15 and 16, mismatched versions/columns, wrong identity/owner and missing initialized state. Confirm the old guard fails the valid schema-16 test.
- [ ] Update the canonical SQL and its two ConfigMap copies; preserve exact schema-15 acceptance for restore/upgrade.
- [ ] Render actual values, run relevant checks, obtain independent review and merge only after required CI passes.
- [ ] Verify live init/main readiness, retained bindings and authenticated private publish/poll without notifying real subscribers.

## Task 2: Narrow the attachment inventory

- [ ] Qualify Prowlarr, Seerr/RU, Bazarr, Cleanuparr, Grafana, pgAdmin, ntfy, Cineplete and Changedetection against their actual versions and paths.
- [ ] Record retain/migrate decisions with native filesystem semantics; separate regenerable caches from durable files.
- [ ] Implement qualified cutovers in bounded groups, with exact backup/copy checks and Git reconciliation; keep old images detached and retained.
- [ ] Assess same-Pod HA/Matter and Karakeep/Meilisearch consolidation only if it reduces complexity without weakening recovery.
- [ ] Verify final attachment counts and application health; document any genuine decision blocking further progress.
