# PostgreSQL completion gate implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent new PostgreSQL consumers from starting without current successful native enrollment and actual canonical login.

**Architecture:** The prepared bundle binds configuration, runtime, Job semantics and encrypted inputs to a deterministic generation. A stdlib Python init verifies the current ConfigMap and exact successful Argo hook; a separate native psql init verifies login. Generic manifests stay outside ApplicationSet discovery.

**Tech Stack:** Python stdlib, PyYAML preparation, native Kubernetes RBAC/projected token, ArgoCD, PostgreSQL18.6 client.

**Spec:** `docs/superpowers/specs/2026-10-11-postgresql-completion-gate.md`.

## Global constraints

- No SQL ledger/runtime or production app changes; no administrator credentials in consumers.
- GET only argocd/applications/postgres and databases/configmaps/postgres-enrollment-config.
- Project API token only into the gate init. Successful hook cleanup stays native.
- Reject selective/apply-only/failed/running/stale acceptance; read ConfigMap before and after Application.
- Source PR must merge before native lab use. Native failure/rebuild qualification remains separate.

## Review focus

- Concurrent ConfigMap update: refuse acceptance across different resource versions.
- Config entry rebinding/removal: refuse an init expecting the previous database/role.
- Missing/malformed API fields or transport errors: wait, then fail without credentials in logs.
- Encrypted credential/config/runtime/Job changes: previous successful hook cannot accept them; unrelated Git revisions do not invalidate unchanged inputs.
- Failed authentication child after ready/LOGIN: completed SQL state cannot bypass failed Argo hook.

### Task1: Fingerprint and verify native acceptance

**Files:** Create `scripts/postgres-enrollment/completion_gate.py`; modify/test `scripts/test-pg-enrollment.py`.

**Interfaces:** `generation(data: dict) -> str`, `hook_name(value: str) -> str`, `accepted(configmap: dict, application: dict, identity: dict) -> bool`, `check_once(get, identity: dict) -> bool`; bounded CLI using fixed Kubernetes URLs and projected TLS/token files.

- [x] Add failing CompletionGateTests for successful full hook and rejection matrix (including all five review conditions).
- [x] Run `python3 scripts/test-pg-enrollment.py CompletionGateTests -v`; observe missing-module failure.
- [x] Implement canonical SHA256, strict acceptance, before/after reads and bounded sanitized API loop; use no third-party runtime dependency.
- [x] Run CompletionGateTests; require all pass.

### Task2: Publish matching inactive bundle and consumer sources

**Files:** Modify `scripts/postgres-enrollment/prepare.py`, README and tests; create `scripts/postgres-enrollment/completion-reader-roles.yaml`.

**Interfaces:** `render_configmap(config, encrypted_data=None)` retains low-level SQL-fixture use; prepared bundles always supply encrypted data and emit `enrollment-job.yaml`, `consumer-gate.yaml`, `consumer-init.yaml` alongside existing outputs. Consumer PodSpec fragment selects a dedicated ServiceAccount and mounts projected token only in its Python init, canonical Secret only in psql init.

- [x] Add failing prepared-output tests for matching hook generation, encrypted-input changes, limited RBAC, private file modes and ordered isolated init mounts.
- [x] Run PreparationTests/ManifestTests; observe missing prepared files or fields.
- [x] Generate the matching bundle after both sealing operations; retain exclusive publication and no password regeneration. Add shared exact-name GET Roles and per-consumer RoleBindings/ServiceAccount/local script ConfigMap.
- [x] Document review/integration boundaries, full sync requirement, fail-closed availability and matching-bundle updates.
- [x] Run all enrollment tests, changed-file pre-commit and YAML checks. Do not modify SQL engine tests just to match implementation.
- [x] Obtain fresh independent source review; fix findings and repeat affected checks.
- [ ] Commit, push, create/attach inactive-source PR and verify hosted CI. Await merge before native use.

Execution: continue inline under the user's standing instruction and approved design. No new production scope is introduced.

Verification:17 gate/preparation/manifest tests passed on the final source;8 native Docker SQL tests passed with all owned cleanup verified. Changed-file pre-commit and README image checks passed. Fresh independent review has no outstanding findings, including the transport-error regression fix. Native consumer qualification awaits source merge.
