# PostgreSQL Application Enrollment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver and qualify a rerunnable native enrollment Job for the existing PostgreSQL server, without activating it in production.

**Architecture:** A native PostgreSQL client uses an admin-only SQL ledger to distinguish interrupted first-time creation from established enrollment. An external preparation helper seals canonical credentials once; Argo reruns SQL without generating credentials. Initial source delivery remains outside ApplicationSet discovery.

**Tech Stack:** PostgreSQL18.6, POSIX shell/psql, Python standard library and existing PyYAML tooling, Sealed Secrets, native Argo Sync Job, Docker-backed unittest qualification.

**Spec:** [Approved enrollment design](../specs/2026-10-10-postgresql-enrollment-design.md). The user's Continue following the idempotency/adoption clarification approves that design; the user approved this source/local-qualification plan before implementation.

## Global Constraints

- Preserve the existing PostgreSQL deployment, major, image pins, service endpoint and application credentials. No production SQL writes, secret reads/transfers, application conversions, CSI allocation or rollout in this source-delivery phase.
- Ready/adopted enrollments retain data and passwords; absent established objects fail, rather than creating replacements. Removing declarations does not delete SQL objects or ledger rows.
- Registry creation is a separate explicit one-time bootstrap command, never part of the ordinary Job/rebuild path. Normal execution requires the registry and expected physical server identity.
- Hold a bounded session advisory lock across every enrollment mutation, including child connections; never release it accidentally with psql reconnects.
- New roles remain NOLOGIN until the ready marker and LOGIN commit together. CREATE DATABASE executes outside a transaction.
- No plaintext credentials in Git, command arguments, SQL/server logs or public receipts. No package installation at Job startup, API Secret reader, operator or Terraform enrollment code.
- Existing controller/service rollout dependencies and value inheritance stay unchanged. A source PR must render no new active postgres resources.

## Review Focus

1. Unknown enrollment names conflicting with removed ledger entries or another declaration must fail before any role/password/database write (Task2).
2. A helper or schema-grant child process fails while parent psql remains alive: parent must exit nonzero and must not commit ready/LOGIN (Task1/2).
3. Missing registry, unexpected owner/structure/ACL, wrong cluster identity, standby or incomplete identity pin must never trigger automatic bootstrap (Task1/2).
4. Mixed successful/new/conflicting entries: preflight the complete declaration set before starting; concurrent runs and retries must preserve completed work without claiming atomicity across databases (Task2).
5. Password/key/URL quoting and partial sealing failure must not leak, regenerate on rerun or overwrite unrelated encrypted keys (Task3).

## File map and interfaces

All new runtime sources initially live under `scripts/postgres-enrollment/`, outside application discovery:

- `runtime/enroll.sh`: CLI modes `run`, `schema`, `verify-login`; native psql invocation, credential files and bounded child operations. Exit0 only on success; sanitized nonzero errors.
- `runtime/enroll.sql`: per-entry preflight, advisory lock, registry/catalog transitions and native client-side password assignment.
- `runtime/schema.sql`: new-database schema privileges through a child connection; no existing/adopted-schema changes.
- `runtime/bootstrap.sql`: explicit one-time registry DDL/ACL initialization, excluded from the ordinary Job ConfigMap.
- `prepare.py`: config validation, native ConfigMap rendering and one-time sealed-credential bundle preparation.
- `job.yaml`: inactive native Job deployment source, used in qualification and later copied into the postgres Application only through separately approved activation.
- `example-config.json`: synthetic example, not a production bootstrap configuration.
- `README.md`: contracts, commands, recovery limits, adoption/rotation boundaries and activation prerequisites.
- `scripts/test-pg-enrollment.py`: stdlib unittest plus actual native client/server containers; imports preparation helper and mounts actual runtime files.
- Modify `.github/workflows/validate-and-diff.yml`: invoke the new tests after existing PostgreSQL backup tests; preserve required job names and all existing validation.

Config contract: `{version: 1, expectedSystemIdentifier: "<recorded decimal ID>", entries: [{id, database, role, mode, passwordKey}]}`. Modes are `new` and `adopt`; ID/database/role are immutable ledger bindings. Reject duplicate IDs/database names/roles/password keys, reserved postgres/pg_* roles and postgres/template0/template1 databases, path separators, control characters and identifiers exceeding PostgreSQL's 63-byte limit. Initial supported SQL names use lower-case ASCII letters/digits/underscore with a leading letter; reject rather than normalize other names. IDs additionally permit hyphens. Credential keys use the same safe ASCII characters with a leading letter; no dot segments or path separators.

Runtime mounts: `/config/config.json`, `/scripts/enroll.sh`, `/scripts/enroll.sql`, `/scripts/schema.sql`, `/credentials/admin/postgres-password`, `/credentials/apps/<passwordKey>`. Only non-secret connection settings enter env: PGHOST, PGPORT, admin PGUSER and PGDATABASE=postgres. Normal production endpoint is `postgres-postgresql.databases:5432`; tests supply their isolated Docker network endpoint and synthetic system ID.

Registry: `postgres.homelab_enrollment.enrollments`, owned by postgres, with text columns `id`, `database_name`, `role_name`, `mode`, `phase`; ID primary key, unique database/role, checked modes/phases. No app/PUBLIC privileges and no passwords/hashes. Bootstrap DDL is transactional; runtime validates structure, ownership, constraints and ACLs before writes.

Lock contract: every bootstrap/enrollment admin session uses the same two-int advisory key `(1346848082, 1)` in the postgres maintenance database. Acquire with bounded pg_try_advisory_lock polling; retain it through child clients and all per-entry transitions. Revalidate each entry after acquiring the lock. Direct administrators remain outside this cooperative contract.

Preparation API: `validate_config(config: dict) -> None`, `render_configmap(config: dict) -> dict`, `prepare_bundle(options: argparse.Namespace) -> pathlib.Path`. `render_configmap` reads the canonical runtime sources and emits native ConfigMap data, without duplicating scripts or including bootstrap.sql.

Bounds: PGCONNECT_TIMEOUT=5; SQL statement timeout60s; lock acquisition deadline30s; Job activeDeadlineSeconds600, backoffLimit2. Job client requests100m/64Mi, limits500m/128Mi. Qualification uses the current digest-pinned Bitnami server image from the design inventory and client `postgres:18.6-alpine@sha256:6c538e7206ea40ff740ef27883529390a690b6ead6ba96b44c67a9f7c638e8fd`.

## Task 1: Implement the guarded SQL lifecycle against actual PostgreSQL

**Files:** Create runtime files and `scripts/test-pg-enrollment.py`; create minimal synthetic example-config used by tests.

**Interfaces:** Consumes config/mount contract above. Produces native `enroll.sh run` and explicit bootstrap.sql operation; later tasks use the same runtime rather than a simulator.

- [ ] Write `test_new_enrollment_then_repeat_preserves_identity_and_data`: explicitly bootstrap a synthetic registry, enroll alpha/alpha, verify ready/LOGIN, canonical authentication and a committed sentinel. Repeat and require unchanged database/role OIDs, password verifier, system ID and sentinel; no credential is generated by runtime.
- [ ] Run `python3 scripts/test-pg-enrollment.py EnrollmentTests.test_new_enrollment_then_repeat_preserves_identity_and_data -v`. Expected RED because runtime is absent, not because Docker/image prerequisites failed.
- [ ] Implement the native runtime. Perform complete input/catalog preflight before mutations. In one admin psql session per enrollment, hold the advisory lock through role+ledger transaction, password assignment, nontransactional CREATE DATABASE, child schema grants and ready/LOGIN transaction. New roles use NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOREPLICATION, NOBYPASSRLS, INHERIT and no memberships. Each child exit status must be checked explicitly; psql ON_ERROR_STOP alone does not validate shell-helper success. Explicit bootstrap.sql checks the expected system ID and uses the same advisory-lock key before transactional DDL; ordinary execution never includes registry-creation DDL.
- [ ] Use native psql password assignment/client-side hashing, with an actual noninteractive check; never emit password-bearing ALTER ROLE text. Read secret files privately and retain the admin connection while running schema/authentication child clients. Reject unsupported CR/LF/NUL password bytes before any write, with a clear error; support spaces, quotes, backslashes, dollar signs, backticks and UTF-8 in password values.
- [ ] Add `test_registry_identity_and_child_failure_are_fail_closed`: missing registry, changed schema owner/shape/ACL, incorrect/absent system ID and failed schema helper return nonzero with no replacement objects; no ready/LOGIN commit after helper failure. Verify client cannot read ledger and cannot connect/read another newly enrolled database.
- [ ] Run both tests GREEN and inspect output for secret leakage. Commit `feat: add guarded native PostgreSQL enrollment lifecycle`.

Docker harness isolation: nonce-named internal network, no published ports, one exact owned server volume, synthetic credentials only, server1GiB/1CPU and at most two clients128Mi/0.5CPU each. Limit logs to two5Mi files; verify owned data usage stays below1GiB and abort if exceeded. Never accept an arbitrary external DSN or production host. Cleanup only recorded test containers/network/volume; no daemon-wide prune. Local daemon availability was verified read-only; this is not permission to use Proxmox/NAS or an existing container.

## Task 2: Prove safe adoption, interrupted recovery and concurrency

**Files:** Extend actual SQL lifecycle and `scripts/test-pg-enrollment.py` only as failures require.

**Interfaces:** Uses Task1 runtime and ledger. Produces a green engine qualification matrix with data/credential/identity preservation assertions.

- [ ] Add `test_adopt_and_remove_preserve_existing_database`: prepare an existing synthetic role/database with sentinel, extension and nontrivial grants. Adopt with the actual password, repeat, remove declaration and rerun. Compare ownership, role attributes/memberships, grants/default ACLs, extensions, password verifier and sentinel before/after. Wrong password, owner or elevated-role attributes must fail without adopting or changing them.
- [ ] Add `test_conflicting_set_is_rejected_before_writes`: duplicate bindings, removed-ledger conflicts, malformed names/keys and a valid-new entry followed by an incompatible entry. Assert no pending role or ledger row was created for the valid-new entry. Conflicts arising after preflight still fail without takeover; do not claim cross-database transactional rollback.
- [ ] Add `test_interrupted_provisioning_resumes_exact_objects`: terminate the exact synthetic enrollment client/backend before/after role+ledger commit, password assignment, CREATE DATABASE, schema grants and ready/LOGIN commit. Resume from the persisted state; prove no second role/database and preserved sentinel after ready. A provisioning role unexpectedly permitting LOGIN, missing recorded role or conflicting database is an error, not repair permission.
- [ ] Use test-only paused copies of the actual SQL at documented boundary comments to make interruption deterministic; record the source hash and pause-only transformation. Do not add a production pause/fault flag or replace native SQL with a mock.
- [ ] Add `test_ready_missing_or_changed_state_is_not_recreated`: remove ready database/role/registry and modify recorded identities in independent fixtures. Runtime must fail with no newly initialized database, role or registry. A wrong synthetic server is rejected before writes.
- [ ] Add `test_concurrent_clients_serialize_and_timeout`: two real clients contend for the same lock; one completes and the other safely verifies/resumes. A held lock produces bounded failure. Prove lock lifetime through schema child work, and that the runner never switches its locking session to another database.
- [ ] Run new cases RED against deficient behavior, then GREEN against minimal fixes. Run the whole engine suite. Commit `test: qualify PostgreSQL enrollment adoption and interruption recovery`.

Comparisons of password verifiers are private test assertions; never print verifiers, passwords, client URLs or full pg_authid snapshots in failure diffs/public evidence. These are synthetic engine tests, not actual production DB adoption or k3s rebuild proof.

## Task 3: Prepare canonical encrypted inputs once

**Files:** Create `prepare.py`, extend tests and README.

**Interfaces:** Consumes validated config, existing sealed aggregate/app inputs and public sealing certificate. Produces a staged bundle of updated config, sealed aggregate credentials, sealed client credentials and rendered ConfigMap; no live SQL/Kubernetes calls.

- [ ] Add `PreparationTests.test_pair_generation_and_retry_preserve_ciphertext`: successful new preparation generates one strong password, feeds that same value to both sealing calls and retains existing encrypted keys/metadata. Duplicate/repeated preparation must preserve existing outputs and refuse regeneration/overwrite. The helper's safe refusal is distinct from SQL runtime's successful repeat execution.
- [ ] Add `test_adopt_uses_supplied_password_and_preserves_unrelated_keys`: adopt requires password on stdin, never generates it. Verify exact namespace/name scope and canonical app password key plus optional percent-encoded database URL. Reject collisions, inconsistent Secret templates/scopes and unsupported password bytes before publication.
- [ ] Add `test_partial_sealing_failure_publishes_nothing`: second sealing operation fails; no final bundle/config is published and temporary private inputs are removed. No plaintext may appear in captured helper output or generated public files.
- [ ] Implement CLI `prepare.py new|adopt --config PATH --id ID --database DB --role ROLE --password-key KEY --app-namespace NS --app-secret NAME --app-password-key KEY --output-dir PATH`, with optional `--app-url-key KEY`; adopt consumes stdin. Use Python secrets for new passwords, urllib.parse for URL quoting and existing `scripts/seal.sh` for sealing. Use a0700 temporary staging directory, controlled0600 private inputs and an exclusive final output directory; no in-place edits of active application manifests.
- [ ] Unit tests use controlled sealing subprocess failures/fixtures and fake synthetic passwords, not a live cluster/key. A real synthetic sealing/readback round trip is an Argo lab gate. Verify bundle ciphertext scopes and schema with existing PyYAML; do not add a new framework.
- [ ] Run tests GREEN, relevant pre-commit and output leak checks. Commit `feat: prepare canonical sealed PostgreSQL enrollment bundles`.

## Task 4: Package the inactive native Job and enforce engine CI

**Files:** Create inactive `job.yaml`, finish example-config/README, modify validation workflow and extend tests.

**Interfaces:** Job consumes Task3 ConfigMap/credentials and Task1 runtime. CI consumes the actual Task1/2 tests. No `infrastructure/**/app.yaml` change or active resource addition in this task.

- [ ] Add `ManifestTests.test_job_contract_and_inactive_delivery`: name postgres-enrollment, namespace databases, hook Sync, sync-wave1, BeforeHookCreation/HookSucceeded, the declared deadline/resources, digest-pinned client and exact mounts. Require no service-account token, API RBAC, CSI volume or bootstrap.sql in rendered ConfigMap. Secrets/scripts must be mounted read-only with permissions compatible with nonroot execution; runtime scratch is memory-backed.
- [ ] Keep failed hook evidence; do not add HookFailed or a TTL deleting it automatically. Run nonroot UID1001 with no capabilities, allowPrivilegeEscalation=false, RuntimeDefault seccomp and a read-only root filesystem. Prevent shell tracing and credential echoing.
- [ ] Add `python3 scripts/test-pg-enrollment.py` after `scripts/test-pg-backup.py` in the existing Validate job. Preserve Docker-backed checks, all existing validation and required check names. CI operates only its own synthetic containers.
- [ ] Validate config examples and README references; run the enrollment suite, backup regression suite, pre-commit on changed files and git diff --check. Verify git diff contains no active postgres server/Secret/app changes. Commit `feat: package inactive enrollment Job and native engine CI`.

## Task 5: Review source delivery and prepare the remaining lab gate

**Files:** README, sanitized `docs/superpowers/reports/2026-10-10-postgresql-enrollment-engine-results.md` and a later exact disposable-lab plan.

**Interfaces:** Consumes actual engine results/source hashes. Produces a reviewable inactive-source PR and concrete remaining qualification scope; no production-ready claim.

- [ ] Record passed/failed/untested gates, runtime/client/server pins, cleanup identities and any harness adaptations. Independently review the whole branch, resolve blocking findings and verify the final diff/tests before push/PR creation. Attach the PR to this task and follow required CI checks.
- [ ] Prepare the exact next lab plan after engine gates pass: native Argo/Sealed Secrets, same-major synthetic retained PGDATA, successful/failed Sync hooks, selective-sync limitation and a controller-phase client. Fresh preflight must bind resources, budgets, native source/version pins, identities, credential-transfer scope, maintenance and cleanup before asking for allocation approval. The removed CNPG lab approval is not reusable allocation authority.
- [ ] Include complete disposable Terraform/Ansible compute+metadata replacement while retaining the database disk. Require unchanged system ID/ledger/latest acknowledged sentinels/passwords, unattended normal Job success and no application writer before enrollment completion. Explicitly test controller-group ordering, hook failure/retry and lost/missing registry/Secret/disk handling.
- [ ] Keep production rollout blocked until that lab passes and a separate exact activation scope is approved. One-time registry bootstrap precedes the normal Job; enroll a synthetic production pilot first, then Autobrr preparation and individually reviewed adoption of existing apps. PostgreSQL CSI migration remains a separate plan.

## Verification and execution handoff

The plan's self-review maps the design's lifecycle, identity, credentials, privileges,
ordering and recovery requirements to Tasks1–5. Local engine/source delivery and
full native rebuild qualification are separate gates; neither substitutes for the
other. No task drops production objects or rotates existing credentials.

Recommended execution: native in this session, with one fresh whole-branch review.
Tasks share one SQL/credential contract; per-task agent handoffs would repeat that
context. Review this plan before implementation. The first source PR is deliberately
inert; exact external lab activation/allocation remains separately approved.

References: [PostgreSQL session advisory locks](https://www.postgresql.org/docs/18/explicit-locking.html#ADVISORY-LOCKS), [psql password handling](https://www.postgresql.org/docs/18/app-psql.html), [Argo resource hooks](https://argo-cd.readthedocs.io/en/stable/user-guide/resource_hooks/).
