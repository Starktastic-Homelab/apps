# Grafana PostgreSQL and retained CSI implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Complete exact-state checks before any continuation; do not replay uncertain operations.

**Goal:** Complete Grafana's state migration without losing existing data or changing normal rebuild operations.

**Architecture:** Reuse shared PostgreSQL enrollment, retained CSI, scoped Argo holds and the native maintenance workflow. Qualify complete conversion into the stock schema before any production change.

**Tech Stack:** Grafana 13.2.3, PostgreSQL 18.6, pinned PGLoader, Proxmox CSI, Helm and Python standard library.

**Spec:** `docs/superpowers/specs/2026-10-16-grafana-postgresql-csi-design.md`

## Global constraints

- Keep the exact current Grafana image and all existing runtime identities/settings.
- No data omission, stock schema replacement or migration-marker rewriting.
- Require explicit sensitive-transfer approval; keep real data and keys outside Git.
- Do not change Prometheus/Alertmanager storage or stop their services.
- Reuse existing fencing, enrollment and rebuild behavior; no new controller.

## Review focus

- Grafana 13 unified resources/history and binary encryption fields must survive.
- OIDC, datasource credentials, sessions and signing keys cannot be inferred from counts.
- Stock PostgreSQL migration records are backend-specific and must stay native.
- Parent NFS exports expose overlapping writers beyond the Grafana claim.
- A shared monitoring Application hold must not permit unrelated runtime changes.

### Task 1: Qualification

- [x] Refresh main, actual image, health, effective engine, source bindings and source schemas/counts.
- [x] Generate the stock PostgreSQL schema using only the exact image and fixture credentials in a closed lab.
- [x] Compare table/column coverage; identify empty obsolete source-only tables.
- [x] Exercise representative synthetic SQLite state through the pinned loader, with negative preservation witnesses, stock app logins and an independent restore/decryption test.
- [ ] Obtain explicit scoped transfer approval; copy consistent real state privately.
- [ ] Compare all application fields and stock contract; restore independently and exercise the real-copy app.
- [ ] Stop for any preservation decision; otherwise record accepted qualification.

### Task 2: Preparation

- [ ] Refresh shared PostgreSQL capacity, full NAS growth budget and all writers; size retained files from evidence.
- [ ] Write failing guard/serialization/completion tests, implement minimal Grafana-specific adapters, then run them.
- [ ] Prepare enrollment once without changing previous credentials, retained storage and scoped old-source guards.
- [ ] Render actual monitoring value layers; verify only intended Grafana resources change.
- [ ] Freeze and rehearse the exact native command package, cold backup, independent recovery, rollback and cleanup.
- [ ] Perform one final independent review and fix its verified findings before production.
- [ ] Publish preparation/enrollment; wait for exact-head hosted gates and current successful enrollment acceptance.

### Task 3: Production and closeout

- [ ] Fresh preflight, owned lock and scoped hold; install/verify old-source protection before writer shutdown.
- [ ] Stop every source writer; archive cold state, retain encrypted off-NAS copies and prove independent recovery.
- [ ] Allocate/populate retained target once; convert once with complete data/schema proof and independently restore current SQL.
- [ ] Retire helpers fully; record the authoritative target-write boundary before startup.
- [ ] Accept Grafana behavior, same-volume recreation and healthy worker movement; restore scheduling.
- [ ] Verify complete shared PostgreSQL backup; merge final activation on exact green checks and inspected diff.
- [ ] Prove desired/live equality, release only the owned hold and pass the six-minute regression watch.
- [ ] Remove exact owned temporary resources and plaintext; retain protected old source, encrypted recovery and keys.
- [ ] Merge sanitized completion evidence and leave a clean worktree.
