# Seerr PostgreSQL and retained CSI preparation implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a tested inactive package for both Seerr instances, ready for a separate production execution proposal.

**Architecture:** Reuse existing PostgreSQL enrollment, completion/login gates and static Proxmox CSI bindings. Add only Seerr's retained-settings/database acceptance and instance-specific composition; preserve base/variant inheritance. All activation files remain under `scripts/seerr-postgresql/production/`, outside ApplicationSet discovery.

**Tech Stack:** Python standard library and existing PyYAML, PostgreSQL18.6/psql, app-template5.2.1, Helm, kubeconform, existing SealedSecret tooling and unittest.

**Spec:** [Merged design](../specs/2026-10-13-seerr-postgresql-csi-design.md), accepted through PR1352 (`66bba8c3a881c09efadc3deae1313b8b3f6968b2`). [Disposable qualification](../reports/2026-10-13-seerr-preflight.md) establishes conversion/start/restart; production remains on NFS.

## Global constraints

- Stock `ghcr.io/seerr-team/seerr:v3.4.1@sha256:f4768de5f616248d723e05891f3345a1402123775d03bf0890dbfedc0831bda1`; no application image or driver modification.
- Shared `postgres-postgresql.databases:5432`, PostgreSQL18.6 physical identity `7584099661242523698`; no new database server or SQL enrollment engine.
- Seerr: enrollmentID/database/role `seerr`; Seerr-RU: enrollmentID `seerr-ru`, database/role `seerr_ru`.
- Each retained configuration volume: 4GiB, ext4, RWOP, Retain, `Prune=false,Delete=false`, one replica, Recreate, existing healthy-worker placement.
- Native `DB_TYPE=postgres`, port5432, `DB_POOL_SIZE=3`; preserve settings/API/session secrets and all14 application tables. Engine-specific migration ledger stays PostgreSQL.
- Keep discovered service, PostgreSQL and base-configs files byte-identical. No live enrollment, CSI allocation, source hold, outage, real-data transfer or production cutover in this plan.
- No new dependencies, controller or per-service Ansible inventory. No credential regeneration after partial/ambiguous output. Never publish private values or row fingerprints.

## Review focus

- Seerr-RU can inherit Seerr's database, Secret or claim if its override source is omitted: prove both actual render compositions and `valuesOverride: true`.
- Stock settings loader generates missing API/session/client/VAPID identifiers: reject absent or malformed retained values before stock code runs.
- `DB_SOCKET_PATH`, `API_KEY` or a different `CONFIG_DIRECTORY` can bypass nominal configuration: reject conflicting overrides and test the actual container environment.
- Settings duplicates, symlinked config/db paths or dangling SQLite files can conceal incorrect retained state: reject them without writes or secret output.
- Formatting can alter fingerprinted gate/config bytes or lose existing ciphertext: regenerate/compare after pre-commit and refuse partial enrollment regeneration.

## Files and interfaces

Create `scripts/seerr-postgresql/{guard.py,main.sql,prepare.py,README.md}` and `scripts/test-seerr-retained-startup.py`.
Generated files stay in `scripts/seerr-postgresql/production/`:

- Shared `values.yaml` and `guard-configmap.yaml` for the base container/guard behavior.
- `seerr/` and `seerr-ru/`: `app-metadata.yaml`, `consumer-gate.yaml`, `pv.yaml`, `pvc.yaml`, `source-hold.yaml`; only Seerr-RU has an additional `values.yaml` with instance overrides.
- `enrollment/`: final `enrollment-{configmap,job,secret}.yaml` plus `seerr-application-secret.yaml` and `seerr-ru-application-secret.yaml`.

Modify `.github/workflows/validate-and-diff.yml` only to validate this inactive package. Update the design status and migration tracker after preparation acceptance. Activation destination mapping belongs in the package README; production command bodies and cutover automation are deferred.

### Task 1: Read-only retained settings and initialized database acceptance

**Files:** Create `scripts/seerr-postgresql/guard.py`, `main.sql`; start `scripts/test-seerr-retained-startup.py`.

**Interfaces:** `validate(root: Path, instance: str, env: Mapping[str, str]) -> None` raises `ValueError` for refusal. CLI: `python3 -I -B guard.py /app/config seerr|seerr-ru`; reads `os.environ`, emits generic status only. `main.sql` runs as the canonical application role in its own database; success is exit0, refusal is nonzero without private output.

- [x] **Write guard tests first.** For each instance, accept a synthetic existing settings file and exact `.homelab-seerr-config` marker `homelab/<instance>/config/v1\n`. Check before/after byte equality and absence of fixture secrets from stdout/stderr.

```python
def test_retained_settings_are_accepted_without_writes_or_secret_output(self):
    for instance in ('seerr', 'seerr-ru'):
        result, before, after = self.run_guard(instance)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(before, after)
        self.assertNotIn(b'fixture-session-secret', result.stdout + result.stderr)
```

`run_guard(instance)` is a test helper that creates only a temporary synthetic
fixture and returns the completed process plus before/after file-byte maps.

- [x] **Add refusal cases.** Missing/wrong marker; absent/malformed/non-object/duplicate-key settings; blank or wrong-type `main.apiKey`, top-level `sessionSecret`, `clientId`, `vapidPublic`, `vapidPrivate`; symlinked retained root, marker, settings or `db` directory; main/WAL/SHM/journal files at `db/db.sqlite3`, including dangling links. Require regular bounded settings/marker files (128KiB maximum); an ordinary empty/missing `db` directory is allowed.
- [x] **Test environment boundaries.** Accept exact production DB type/host/port/user/name/pool and nonempty bounded password. Reject wrong instance, missing/wrong database fields, test/development `NODE_ENV`, nonempty `DB_SOCKET_PATH`, conflicting `CONFIG_DIRECTORY` or `API_KEY`. The latter may be absent or equal to retained settings; never generate keys.
- [x] **Run the guard tests and confirm failure because the guard does not exist.** Command: `python3 scripts/test-seerr-retained-startup.py RetainedConfigTests`. Then implement the stdlib guard with duplicate-key JSON rejection and generic CLI errors; rerun to pass.
- [x] **Write native SQL negative tests first.** Use one unique no-network Docker PG18.6 fixture with bounded memory/tmpfs/CPU, synthetic credentials only and cleanup on failure. Empty DB, missing table, wrong role/database, missing latest migration, empty users and wrong SCRAM password must fail; populated canonical fixtures for both instances must pass unchanged. Never use production SQL for these tests.
- [x] **Implement `main.sql` and run the native test.** `BEGIN READ ONLY`, statement timeout10s; require database/user equality and membership in `seerr,seerr_ru`, all14 qualified application tables plus `migrations`, and administrator userID1. Require at least19 migration records including timestamp1781732098511/name`AddIgnoreQuotaToMediaRequest1781732098511` (pinned stock migration floor). Tables: `blocklist`, `discover_slider`, `issue`, `issue_comment`, `media`, `media_request`, `override_rule`, `season`, `season_request`, `session`, `user`, `user_push_subscription`, `user_settings`, `watchlist`. This is a bootstrap guard, not a substitute for the full cutover comparison.
- [x] **Commit only this tested deliverable.** No production files or credentials change.

### Task 2: Instance composition and encrypted enrollment preparation

**Files:** Create `scripts/seerr-postgresql/prepare.py`, generated `production/` files and package tests in `scripts/test-seerr-retained-startup.py`.

**Interfaces:** `build_sources(instance: str) -> tuple[list[dict], dict]` adapts existing `postgres-enrollment.prepare.consumer_sources()` for one instance. `write_sources() -> None` serializes the shared overlay plus minimal RU overrides. `prepare_enrollment(output: Path) -> None` reserves a new0700 directory and invokes the existing generator twice; `publish_enrollment(output: Path) -> None` serializes only exact existing completed ciphertext bundles. CLI: `prepare.py sources` or `prepare.py enrollment --output <exclusive-private-path>`; neither applies resources or contacts SQL.

- [x] **Write composition tests first.** Require dedicated `<instance>-postgres-completion` ServiceAccounts, existing named GET-only reader Roles, canonical enrollment args/DB identity and init order `retained-state -> enrollment -> database`. Fail when generated files are absent, then implement the adapter using the existing generator and Prowlarr chart adaptation pattern.

```python
def test_instance_bindings_and_init_order(self):
    resources, values = self.prepare.build_sources('seerr-ru')
    inits = values['controllers']['main']['initContainers']
    self.assertEqual(inits['enrollment']['dependsOn'], 'retained-state')
    self.assertEqual(inits['database']['dependsOn'], 'enrollment')
    self.assertEqual(values['persistence']['seerr-config']['existingClaim'],
                     'seerr-ru-config-block')
```

- [x] **Pin Secret/environment composition.** `media/<instance>-postgres-secret`, key`password`; aggregate keys`seerr-password`,`seerr-ru-password`. Include `NODE_ENV=production` in the same native DB environment definition for main and retained-state, with Secret `valueFrom` for `DB_PASS`. Only the acceptance init mounts a projected API token. Only database-login init mounts `/credentials/password`; it invokes `main.sql`. Config mounts RW at `/app/config` for stock app and RO for retained-state. Clear inherited Pod fsGroup mutation using the established controller Pod override and test the rendered result.
- [x] **Test storage, metadata and inheritance.** Exact claim/PV names `<instance>-config-block`, CSI handles `homelab//k3s-block/9999/vm-9999-<instance>.raw`, existing homelab/pve topology and cache`none`. Both app metadata patches set `manifests: true`; RU additionally sets `valuesOverride: true`, preserving `baseApp` and ingress. RU values contain only differing instance bindings/gate args/environment; common image, probes and behavior stay in the base overlay. Reuse the existing old-claim admission pattern with separate Seerr/Seerr-RU policy names. No `app.yaml` may appear anywhere in the inactive package.
- [x] **Before sealing, verify collisions read-only.** Against the unchanged production PostgreSQL identity, verify proposed IDs/password keys are absent from current declarations and roles/databases are absent from SQL. Verify the public certificate through the existing certificate provenance. No adoption, password rotation or live enrollment is allowed; an actual collision requires a decision before generating credentials.
- [x] **Prepare two encrypted declarations once.** Chain current config/aggregate -> Seerr bundle -> Seerr-RU bundle with the existing `new` generator, using `scripts/seal.sh`. Preserve all prior aggregate ciphertext. Keep separate strict-scope app Secrets from both intermediate bundles. Persist private output outside Git; existing output or partial failure refuses regeneration and retains the exact completed intermediate bundles.
- [x] **Test and publish the exact bundles.** Verify both entries and new keys, unchanged prior ciphertext/server identity, strict Secret scope, absence of plaintext fields, exact gate script bytes, acceptance-generation hash and matching hook Job name. Require current-hook acceptance for each identity; reject stale generation or failed hook using the unchanged existing completion gate. Test exclusive-output refusal before any sealing subprocess runs. Use a formatter-safe literal YAML serialization like Prowlarr's existing implementation.
- [x] **Commit the inactive generated package and tests.** Recheck discovered files remain unchanged.

### Task 3: Actual renders, CI and activation handoff

**Files:** Finish `scripts/test-seerr-retained-startup.py`, create `scripts/seerr-postgresql/README.md`; modify `.github/workflows/validate-and-diff.yml` and documentation status/tracker.

**Interfaces:** Test flags `SEERR_SQL_TEST=1`, `SEERR_RETAINED_RENDER=<file>`, `SEERR_RU_RETAINED_RENDER=<file>`. Tests consume the exact generated files from Task2; no separate test-only generator or enrollment protocol.

- [ ] **Add render contract tests before CI wiring.** For both Pods, assert original image, UID/GID1000, one replica/Recreate, worker placement, disabled automount, exactly one correct retained claim, init ordering/mount isolation, canonical DB env and Secret, and all health probes `/api/v1/status/appdata`. Prove RU does not reference Seerr's Secret/account/claim or database. Its shared guard ConfigMap may intentionally be common. Confirm the old dynamic config claim is disabled and no media mount is added.

```python
def test_ru_render_cannot_use_base_instance_storage_or_credentials(self):
    pod = self.ru_render['spec']['template']['spec']
    self.assertFalse(pod['automountServiceAccountToken'])
    claims = [v['persistentVolumeClaim']['claimName'] for v in pod['volumes']
              if 'persistentVolumeClaim' in v]
    self.assertEqual(claims, ['seerr-ru-config-block'])
    main = next(c for c in pod['containers'] if c['name'] == 'main')
    env = {v['name']: v for v in main['env']}
    self.assertEqual(env['DB_NAME']['value'], 'seerr_ru')
    self.assertEqual(env['DB_PASS']['valueFrom']['secretKeyRef'],
                     {'name': 'seerr-ru-postgres-secret', 'key': 'password'})
```

- [ ] **Render both actual value cascades.** Base: globals -> common -> current Seerr values -> inactive shared overlay. RU: same sequence -> inactive RU overrides. Use chart5.2.1 from the current ApplicationSet; the future activation merges the shared overlay into base values and discovers the RU override through `valuesOverride`. Also render the prospective base-configs bindings from temporary copies; do not edit active paths. Run kubeconform on these renders and the static package manifests with the workflow's raw/template exclusions and CRD policy.
- [ ] **Wire the same checks into hosted CI.** Add one Seerr preparation step beside Prowlarr's: both renders/schema checks and `SEERR_SQL_TEST=1` with both render flags. Reuse existing pinned tool setup; Docker fixture uses the existing pinned PostgreSQL client image. Do not rerun the real-copy rehearsal or cluster rebuild for this local package.
- [ ] **Write the exact activation mapping/runbook.** Map shared values into Seerr base, RU override to its values plus metadata flag, both manifest directories with discovery enabled, shared guard into the base app's manifest directory, static bindings into separate base-configs template directories, and final aggregate config/Job/Secret to PostgreSQL. Publish enrollment before outage only under separate execution approval; retain source writer fencing, cold backup/recovery, live/Git equality and the qualified release/watch sequence from the design. Explain that prepared ciphertext does not create SQL identities.
- [ ] **Run relevant checks after formatting.** `pre-commit run --files <changed-files>`, scoped YAML lint, regeneration-byte equality, actual render/schema tests and `SEERR_SQL_TEST=1 SEERR_RETAINED_RENDER=/tmp/seerr-retained.yaml SEERR_RU_RETAINED_RENDER=/tmp/seerr-ru-retained.yaml python3 scripts/test-seerr-retained-startup.py`. Run documentation image/link checks and `git diff --check`. Confirm `git diff --name-only origin/main` contains no discovered service/PostgreSQL/base-configs/bootstrap changes.
- [ ] **Request independent final review, fix actionable findings, open the inactive preparation PR and follow hosted checks.** Report actual pass/skip results. Stop for human merge; no production enrollment, allocation or outage is implied. The later private execution package needs fresh identities, budgets, commands, timing and separate approval.

## Plan review and execution choice

Recommend native execution in this existing isolated worktree: the three tasks
share a small adapter and the already-qualified enrollment contract. Implement
serially, then obtain one independent whole-branch review. Subagent-driven
execution is available if the user prefers per-task implementation/review.
The human approved this plan and native execution. Production execution remains
outside its scope.
