# Prowlarr PostgreSQL execution preparation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task-by-task in this existing isolated worktree.

**Goal:** Prepare inactive, tested Prowlarr PostgreSQL/retained-CSI sources for the reviewed production operation.

**Architecture:** Reuse the existing enrollment generator and completion gate. Keep final application/storage/enrollment inputs outside ApplicationSet discovery until the accepted live cutover is reconciled. Add only the app-specific retained-config and populated-main checks.

**Tech Stack:** Python standard library, PyYAML, existing Helm app-template 5.2.1, native PostgreSQL client and SealedSecrets tooling.

**Spec:** [Merged design](../specs/2026-10-13-prowlarr-postgresql-cutover-design.md).

## Global Constraints

- No production enrollment, allocation, source hold, downtime or activation in this preparation PR.
- Preserve the exact Prowlarr 2.6.5.5623-ls161 digest and existing PostgreSQL physical ID 7584099661242523698.
- Separate `prowlarr-main`/`prowlarr_main` and `prowlarr-log`/`prowlarr_log` restricted owners; two pool limits of five.
- `media/prowlarr-config-block`: 4GiB ext4/RWOP/Retain/Recreate; handle `homelab//k3s-block/9999/vm-9999-prowlarr.raw`.
- Retain old NFS source and encrypted cold archive; fresh diagnostic logs, all main History rows preserved.
- Only ciphertext may be published. No replacement of existing aggregate credentials or generic enrollment logic.
- Live migration restores availability before final desired-state reconciliation merge; no production merge authority assumed.

## Review Focus

- Valid XML with duplicated or conflicting PostgreSQL fields must block, without exposing passwords.
- A preserved-looking config on an empty main database must block stock fresh initialization.
- Either declaration's stale acceptance or failed login must block startup; API token and passwords stay scoped to their inits.
- Partial bundle creation must never silently regenerate already-created credentials or erase prior ciphertext.
- A preparation merge must not discover inactive PVs, source admission, credentials or final workload values.

### Task 1: Read-only retained state and native main-database checks

**Files:** Create `scripts/prowlarr-postgresql/guard.py`, `main.sql`, and `scripts/test-prowlarr-retained-startup.py`.

**Interfaces:** Guard consumes config directory plus mounted main/log password files. It checks `.homelab-prowlarr-config`, exact canonical XML connections and no active SQLite files, returns 0 only on accepted state, and writes nothing. `main.sql` returns success only for populated stock main schema with migration floor 44.

- [ ] Write fixture-based guard tests: accepted retained XML; absent/wrong identity/API key; wrong, partial, duplicated or conflicting connection fields; main/log fallback DB/WAL/SHM; unchanged bytes and no secret output.
- [ ] Run the tests; expect failure because the guard is absent.
- [ ] Implement `connection(database: str, password: str) -> str` and `validate(root: Path, credentials: Path) -> None`, with canonical Npgsql quoted password handling and fixed DB owners/host/pool limits. Reject links for identity/config/credentials; CLI suppresses private exception content.
- [ ] Add native SQL assertions for the expected current stock tables, migration floor and nonempty Users/Config; no writes or admin privileges.
- [ ] Run guard tests; expect all cases pass. Commit the app-specific guard sources/tests.

### Task 2: Inactive final bindings, two gates and encrypted enrollment bundle

**Files:** Create `scripts/prowlarr-postgresql/prepare.py`, `production/values.yaml`, `production/guard-configmap.yaml`, `production/consumer-gate.yaml`, `production/pv.yaml`, `production/pvc.yaml`, `production/source-hold.yaml`, and generated `production/enrollment/` inputs.

**Interfaces:** `build_sources() -> tuple[list[dict], dict]` composes one ServiceAccount/shared completion ConfigMap/two named RoleBindings plus the final Helm overlay. It reuses `postgres-enrollment.prepare.consumer_sources` for both identities; no new gate protocol. `prepare_enrollment(output: Path) -> None` invokes the existing generator twice, preserving aggregate/app ciphertext, with exclusive per-entry outputs.

- [ ] Extend the tests for dual identities, isolated mounted passwords, token mounts, named RBAC, preserved completion-code bytes, absent automatic token, and inactive discovery.
- [ ] Run tests; expect missing source/overlay assertions to fail.
- [ ] Generate the final overlay with `retained-state`, main acceptance/login, and log acceptance/login in that order. Main login executes `main.sql`; both password files are mounted read-only to retained-state, each login sees only its own password. Main app receives neither mounted password files nor API token; XML remains its qualified connection route.
- [ ] Generate exact 4Gi PV/PVC and old-claim admission sources from the established Autobrr pattern; retain flags/topology/cache-none unchanged.
- [ ] Prepare the two encrypted declarations locally using the repository public certificate and `scripts/seal.sh`; keep their outputs inactive. Verify all old declaration/ciphertext entries unchanged, new app keys complete, and acceptance generation/Job consistent.
- [ ] Render real value layers and base-configs preview, then run the render contracts. Expect one target claim, no default config/media claims, one replica/Recreate/worker placement/no fsGroup, unchanged image/probes/API settings and distinct init names. Commit inactive sources.

### Task 3: Qualification, operational handoff and merge boundary

**Files:** Create `scripts/prowlarr-postgresql/README.md`, update `.github/workflows/validate-and-diff.yml` for the focused checks, and add a preparation report.

**Interfaces:** CI renders the inactive overlay without applying it; review consumes exact files/renders/tests plus the merged design. The subsequent private native operation freezes reviewed sources and current live identities before an explicit execution proposal.

- [ ] Document exact local preparation/render/verification commands and activation copy destinations; explicitly separate the inactive preparation merge from enrollment and cutover.
- [ ] Record cold-WAL/archive/conversion/restore and writer-retirement steps using existing accepted native operation patterns and qualified PGLoader settings. List exact per-stage predecessor receipts, expiry behavior, newest-write recovery and retained source cleanup boundaries.
- [ ] Integrate focused guard/render checks into CI; run relevant pre-commit, YAML, schema, Homepage, Jellyfin and documentation references. Generic tests run in normal CI; no repeat live enrollment or full rebuild qualification.
- [ ] Perform fresh whole-branch review, fix blocking findings and verify again. Open/attach a preparation PR, follow current-head CI and stop for its merge. This PR must not change live resources; private fresh preflight, absolute outage window and execution approval follow before production mutation.
