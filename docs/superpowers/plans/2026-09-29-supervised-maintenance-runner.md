# Supervised Maintenance Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Preserve the user's Native execution choice. Track tasks with the checkboxes below.

**Goal:** Installable, versioned runner tooling that survives client disconnection and reports interrupted execution from durable records, qualified with read-only storage operations before mutation adoption.

**Architecture:** An Ansible-managed systemd user service executes a fixed Apps dispatcher from a pinned source release. A small standard-library helper submits private, immutable requests and inspects durable receipts. The merged execution mutex protects operation bodies; no queue, daemon, database or general shell-command API is added.

**Tech Stack:** Python standard library, Linux/systemd user services, Ansible, existing maintenance ownership/execution helper, unittest and disposable systemd qualification.

**Spec:** [Approved retained storage hardening design](../specs/2026-09-29-retained-storage-hardening-design.md), delivery boundary 2. This implements the executor foundation; mutation recovery and backup integration remain explicitly incomplete.

## Baseline and boundaries

Ansible #271 merged as `31ba26fd643b15355f70642047f76eef232ef73e`; formatting, Ansible Lint, Ansible Syntax Check and i915 metadata/policy checks passed. Installed-hardware validation was intentionally skipped. Apps #1270 supplies local status/preflight in merge `02fcc29e0317949ebeb0989396d60d547f0b24b2`. Refresh revisions before implementation without changing production pins.

This increment exposes only `status` and `preflight`. Requests for `hold`, `release`, `verify`, onboarding, snapshot, fencing, backup capture, reader creation or arbitrary commands are rejected. Existing manual/workflow mutation routes remain unchanged and must not be run concurrently with future adopted operations. This deliberate staged adoption prevents a generic executor from being mistaken for an operation-specific recovery protocol.

Deliver coordinated Ansible and Apps PRs. Neither PR dispatches installation or maintenance. Installation on VM300 and enabling production use require a later reviewed rollout. No application outage is expected from merging these source changes.

## Global Constraints

- “No automatic restart/retry of mutations after runner reboot.”
- “Persist operation intent before side effects, then observations and completion with atomic, validated receipt APIs.”
- “Limit submissions to supported operations and validated arguments, not arbitrary shell text.”
- “Do not add profile fields to the existing native identity record or change its hashing.”
- Preserve the current original-owner record, nonce, first-write evidence and runner marker; do not migrate or clear them.
- Secrets stay in mode-0600 files inside mode-0700 request directories. No nonce in command-line arguments, reports, Git or ordinary journal output.
- Qualified interpreter/source identity must match before execution. Missing prerequisites are failures, not permission to install dependencies on demand.
- No production credentials, mounts or live network targets are needed for qualification.

## Review Focus

1. Lost submission reply or repeated request ID must expose the existing request, never replay it (Tasks 1 and 3).
2. Symlink/path substitution, incomplete writes and disk-full errors must not create a valid request or success receipt (Task 1).
3. Client loss must leave supervised work running; service/runner loss must remain interrupted or unknown, never inferred success (Tasks 2 and 4).
4. Source/interpreter drift or invalid ownership must refuse execution before the dispatcher starts (Task 2).
5. Concurrent requests, leaked child processes and partial output must not bypass exclusion or publish completed success (Tasks 2 and 4).

## File map and public interfaces

Ansible owns:

- `scripts/maintenance_requests.py`: request validation, safe atomic publication and report inspection.
- `scripts/maintenance_executor.py`: fixed CLI with `submit`, `start`, `run` and `inspect` subcommands; no shell arguments or arbitrary source paths from requests.
- Existing `scripts/maintenance_lock.py`: reused without a new ownership schema.
- `roles/maintenance_runner/tasks/executor.yml`, `templates/homelab-maintenance@.service.j2`, defaults and installation manifest template: opt-in installation, fixed paths and qualified release identity.
- `scripts/tests/test_maintenance_requests.py`, `test_maintenance_executor.py` and `tests/maintenance-executor-systemd.sh`: protocol/unit tests and disposable runtime qualification.
- `docs/maintenance-executor.md`: installation, operation, diagnosis and limitations.

Apps owns `scripts/storage/supervised_readonly.py` and `scripts/storage/tests/test_supervised_readonly.py`: a fixed adapter for existing `inspect_state`/`preflight`; no duplicated state inspector or mutation dispatch. The existing workflow is not switched in this increment.

`validate_request(data: dict) -> dict` accepts exactly schema 1, UUID request ID, operation (`status` or `preflight`), service (`jellyfin`), expected stage, Apps commit SHA and qualified runtime ID (64 lowercase hexadecimal characters identifying the managed release manifest). Expected stage uses the existing lowercase stage-name format; the source commit is 40 lowercase hexadecimal characters. Unknown fields are refused. The managed installation fixes all paths and executable selection; requests cannot supply argv, environment, state roots, interpreters or working directories.

`publish_request(root: Path, request: dict, credentials: dict) -> str` creates `<root>/requests/<uuid>/` privately, with a durable acceptance marker published last. Credentials contain the supplied original owner/nonce, not values inferred from the ownership record. Preserve the schema-1 original ownership verification. Existing IDs, including incomplete directories, are never overwritten or reused.

`inspect_request(root: Path, request_id: str) -> dict` returns a sanitized schema-1 report: requested operation, runtime/source identity, recorded timestamps, phase and fixed diagnostic code. Phases are `accepted`, `running`, `succeeded`, `failed` or `unknown`. `running` is recorded history, not proof of a currently live process; present service state separately. No valid terminal receipt means no success claim.

## Task 1: Durable requests and receipts

- [ ] Write tests first for strict schema rejection, duplicate IDs, lost replies, partial request publication, malformed/truncated records, forbidden fields/commands, symlinked parents/files, FIFO input, oversized JSON and secret-sentinel redaction. Use temporary local state and record exact bytes before/after rejected operations.
- [ ] Run `python3 -m unittest discover -s scripts/tests -p test_maintenance_requests.py -v`; confirm the interface is missing, then implement it. Use no-follow descriptor-relative access and bounded reads. Serialize and validate fully before writing; use exclusive files, fsync and a final durable acceptance marker. Never repair partial directories by overwriting them.
- [ ] Add receipt APIs that publish immutable started/terminal observations with validated schema, request/runtime/runner identity and timestamps. A terminal success requires exact request binding and exit code 0; nonzero dispatcher exits are failures. Reject a second terminal receipt or mismatched identity. Raw exceptions and dispatcher output never enter sanitized reports.
- [ ] Run the focused tests to green, including injected write/fsync failures. Commit the request protocol with documentation of incomplete-request handling. A missing acceptance marker permits inspection only, not execution.

## Task 2: Fixed executor and qualified installation

- [ ] Add failing tests for invalid original owner/stage, source/interpreter mismatch, concurrent execution, unknown request ID, repeated starts, dependency absence, child failure and incomplete terminal writes. Use a fixed test adapter and temporary state; tests must demonstrate no body runs after failed validation.
- [ ] Implement `run` with the existing `execution(root, owner, nonce, stage)` context. Under exclusion, require accepted intent and no prior started/terminal receipt, verify the managed runtime/source manifest and credentials, persist started evidence, then launch only the fixed adapter with `pass_fds` for the lock. Wait/reap children before writing terminal evidence. A prior started receipt with no terminal record is unknown and cannot be automatically rerun. Record sanitized validation/busy failure without changing original ownership.
- [ ] Implement idempotent `submit` behavior: publish once, request `systemctl --user start --no-block homelab-maintenance@<uuid>.service`, then return the request ID. If service start fails or its reply is lost, leave accepted intent visible; do not delete it or automatically resubmit. Repeated submission reports the existing ID and instructs inspection. Implement `start <uuid>` only for accepted requests with no started receipt; the service rechecks this under execution exclusion.
- [ ] Add opt-in Ansible installation disabled by default. Install root-owned source releases under `/opt/homelab-maintenance/releases/<runtime-id>` and a root-owned user-unit template in `/etc/systemd/user/`. Source archives are pinned by commit and SHA-256, never mutable branch names. Record interpreter version and executable hash; a change invalidates qualification and fails startup until a newly reviewed manifest is installed. Initial adapter uses only the standard library; no runtime pip install.
- [ ] Configure the service with `Type=exec`, `Restart=no`, `KillMode=control-group`, `TimeoutStopSec=30s`, `RuntimeMaxSec=3600`, restrictive umask and fixed ExecStart. No boot activation or queue polling. Use the already reviewed runner user; enable lingering only in the opt-in installation and document that host-side effect. Do not grant new sudo privileges or accept arbitrary unit properties from submission.
- [ ] Persist private child stdout/stderr beneath the request directory; return only fixed diagnostics and log references. Keep systemd journal output free of secrets. Test that missing/altered credential paths fail closed. Run focused tests and template assertions; commit executor/install changes without running the role on VM300.

## Task 3: Apps read-only adapter

- [ ] Write tests that the adapter accepts only the two operations and invokes the existing inspection functions with the managed state root. Assert all mutation/transport entry points remain unreachable; malformed arguments and requests for mutating operations fail.
- [ ] Implement `scripts/storage/supervised_readonly.py` with fixed JSON output and matching inspection exit semantics. Set Python bytecode suppression in the fixed invocation so root-owned releases remain immutable. `status` success means local checks passed, never release authorization; `preflight` may correctly exit nonzero for missing prerequisites.
- [ ] Run the full Apps storage suite with the pinned helper and existing test dependencies. Run applicable hooks and document how the executor discovers this adapter from the pinned release. Commit and open an Apps PR without switching `.github/workflows/storage-maintenance.yml`.

## Task 4: Disposable systemd qualification and delivery

- [ ] Add a reproducible Linux/systemd qualification script that takes an explicitly disposable host/environment, checks its identity and requires a temporary state root. Use synthetic ownership and no production credential files. It must refuse the production runner identity/root. Do not provision or repurpose a VM implicitly.
- [ ] In an available disposable environment, test client disconnect, duplicate submission, explicit start of accepted intent, concurrent starts, runtime mismatch, child nonzero exit, forced service stop, process kill and simulated stale started receipts. A fixed test fixture operation may block on a pipe for synchronization; it must not be enabled in the installed production allowlist. Verify request/receipt durability and retained ownership after each case.
- [ ] Verify a second attempt cannot rerun an operation with started evidence, and a terminal success never comes from systemd's inactive state alone. Test full child cleanup on service termination, protected logs and continued lock exclusion while a child is alive.
- [ ] If no suitable disposable systemd environment is available, finish code/unit tests and open draft PRs with runtime qualification explicitly pending. Do not use VM300 as an unannounced test host or call unit tests equivalent to systemd/runner-reboot qualification.
- [ ] Run applicable Ansible maintenance tests, Apps storage tests, configured hooks and diff checks; inspect real CI coverage and include new tests. Obtain one independent review per final repository diff, address material findings, open/attach linked PRs and document the ordered merge/install boundary. Neither merging nor CI dispatches installation.

## Acceptance and follow-on

Completion requires durable submission/inspection, strict request allowlisting, a qualified fixed runtime, full-operation exclusion and successful disposable systemd qualification. Without the latter, source delivery may be reviewable but this stage remains unqualified for production.

Production enabling is a separate reviewed installation. Mutating operation adoption requires another plan that defines each operation's intent/readback reconciliation, owned mount/session cleanup, backup publication and recovery after runner restart. Do not claim this read-only executor makes old mutation workflows crash-safe, solves runner-loss recovery, or qualifies another application migration.

## Execution update: workstation constraint (2026-09-30)

The user reported workstation freezes during this session and prohibited using
this computer as an Ansible deployment target. Privileged systemd container tests
were attempted; no Ansible deployment was dispatched, but causation is unproven.
The disposable container was stopped and removed. No further privileged
containers, systemd qualification or Ansible invocations run on this workstation.
Lightweight synthetic-state unit tests and static checks remain permitted.

The qualification harness now requires an explicitly marked disposable VM and
refuses containers, physical workstations and production VM300. Runtime
qualification is pending, so both coordinated PRs remain draft. No production
installation, workflow switch or mutation adoption is authorized by delivery.
