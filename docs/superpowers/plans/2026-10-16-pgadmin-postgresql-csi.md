# pgAdmin PostgreSQL and retained CSI implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline. One independent final review covers the complete implementation/native operation before production; no per-task delegation.

**Goal:** Preserve pgAdmin's complete state on shared PostgreSQL and retained CSI.

**Architecture:** Reuse current enrollment, completion/login gates, static CSI,
verified retirement, native ownership and scoped Argo holds. Qualify a data-only
copy into the exact stock schema before any authoritative production change.

**Tech Stack:** pgAdmin9.18, chart1.70.4, PostgreSQL18.6, Python/SQLAlchemy already
in the stock image, Helm and unmodified Proxmox CSI.

**Spec:** `docs/superpowers/specs/2026-10-16-pgadmin-postgresql-csi-design.md`

## Global constraints

- Preserve all existing accounts, permissions, saved credentials, settings and files.
- Keep the exact pgAdmin image/chart/auth configuration and current administrator Secret.
- No dropped populated tables, schema-marker rewrites, application patches or new controller.
- Keep application copies, keys and plaintext outside Git; no real infrastructure credentials in fixtures.
- Existing source and encrypted recovery remain protected; never reopen stale SQLite after target authority.
- Native clock90minutes before target and3hours total cannot reset or extend without user approval.

## Review focus

- JSON/null/boolean/datetime/binary-as-hex representations must preserve every field and duplicate.
- Copying encrypted fields requires actual decryption/connection acceptance, not equal ciphertext alone.
- The stock entrypoint must never initialize an empty/wrong established target during rebuild.
- Filebrowser and provisioner parent exports expose writers beyond the pgAdmin claim.
- Full-source Argo queue replacement must retain all declared sync options and original Secret bytes.

### Task 1: Qualification and exact conversion

**Files:** Create `scripts/pgadmin-postgresql/data.py`, `scripts/test-pgadmin-data.py`,
`docs/superpowers/reports/2026-10-16-pgadmin-assessment.md`; keep lab/native copies
under ignored `.superpowers/sdd/2026-10-16-pgadmin-postgresql-csi/`.

**Interfaces:** Consumes a read-only SQLite copy and a freshly initialized stock
PostgreSQL schema; produces complete preservation proof and independent recovery.

- [x] Refresh exact source engine/image/schema/files/auth and upstream behavior.
- [x] Write negative representation/coverage tests first; run and observe failure.
- [x] Implement minimal native-schema data transfer and complete comparison, preserving migration markers.
- [x] Exercise synthetic stock app login, encrypted saved connection, restart, corruption rejection and independent restore.
- [x] Complete scoped real-data qualification and record evidence; pause only for a necessary approval/decision.
- [x] Commit public converter/tests/assessment and mark task complete only after its whole test command passes.

Run: `python3 scripts/test-pgadmin-data.py`.
Expected: all conversion/negative preservation checks pass; no source write.

### Task 2: Permanent startup and reviewable native package

**Files:** Create `scripts/pgadmin-postgresql/{prepare.py,guard.py,README.md,production/*}`,
`scripts/test-pgadmin-retained-startup.py`; update scoped CI and inactive enrollment.

**Interfaces:** Consumes Task1 accepted stock schema and credentials; produces
inactive guards/static bindings/enrollment and an immutable exclusive operation.

- [ ] Measure shared SQL capacity and every raw-image growth reservation; select target capacity from current facts.
- [ ] Write rejecting guard/render tests first, implement retained-file/current-enrollment/native-SQL guards and chart adapters.
- [ ] Prepare one append-only sealed enrollment without rotating existing entries.
- [ ] Freeze/rehearse exact native cold backup/restore/allocation/import/rollback/cleanup commands and no-replay fencing.
- [ ] Render actual layers and inspect only intended resources and scoped application changes.
- [ ] Dispatch one independent final review, fix verified important findings with regression tests, then publish/merge preparation on exact green checks.

Run: `python3 scripts/test-pgadmin-data.py && python3 scripts/test-pgadmin-retained-startup.py`.
Expected: complete positive/negative checks pass; actual layered Helm render and raw manifests validate.

### Task 3: Native migration, reconciliation and cleanup

**Files:** Update `infrastructure/controllers/databases/pgadmin/values.yaml`, scoped
manifests and `infrastructure/base-configs/templates/` following current
base-configs storage paths; create `docs/runbooks/pgadmin-storage.md` and a sanitized
production completion report. Resolve exact existing base-configs path from app source.

**Interfaces:** Consumes immutable reviewed package, accepted real-data recovery,
current enrollment and fresh native identities; produces healthy GitOps runtime,
encrypted durable recovery and exact cleanup receipts.

- [ ] Acquire existing native owner/hold; protect source; stop and retire every writer.
- [ ] Independently restore latest encrypted cold data before exclusive allocation/import.
- [ ] Independently restore latest SQL dump; retire helper; mark authority and start stock app.
- [ ] Accept actual authentication/server connection/state, recreation and healthy-worker movement.
- [ ] Verify full shared PostgreSQL backup and exact final Git/live resources.
- [ ] Merge activation with all exact-head hosted checks; safely release full current sync and watch six minutes.
- [ ] Encrypt audits, clean only owned temporary resources/plaintext, release native owner last.
- [ ] Merge completion report on exact green checks; encrypt final audit and remove exact local private working directory.

Run: reviewed native stage dispatcher, one stage at a time under its original clock.
Expected: every stage has paired intent/known terminal/acceptance; four apps Healthy/Synced,
state preserved, recoveries independently verified, owned cleanup complete.
