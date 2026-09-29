# Retained Storage Inspection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the first PR from the approved design: local, read-only status and dependency preflight for the existing retained-storage state.

**Architecture:** Add a standard-library inspection module and route two new operations to it before importing mutation/transport dependencies. Read existing records without conversion. Produce human and JSON views from one allowlisted report; existing maintenance operations retain their current paths and behavior.

**Tech Stack:** Python standard library, unittest, existing Python CLI; no new runtime dependencies.

**Spec:** [Approved retained storage hardening design](../specs/2026-09-29-retained-storage-hardening-design.md), delivery boundary 1. Approved by the user on 2026-09-29.

## Global Constraints

- “Do not add profile fields to the existing native identity record or change its hashing.”
- “Existing state is inspected in place.”
- “Secrets remain in restrictive files and never appear in reports or command lines.”
- “Inspection success never implies permission to release a writer.”
- “No workflow switch or admission change.”
- No live API, SSH, NAS, mount, login, ownership acquisition, state writes or stage advancement in these new commands.
- This PR supports `jellyfin` only. Unknown services fail explicitly; do not advertise general enrollment before shared admission is implemented.
- This is a local readiness report, not runtime qualification, backup validation, live health or release authorization.

## Review Focus

1. Symlink or special-file input: refuse before reading, including symlinks in parent directories (Task 1).
2. Secrets embedded in malformed records or exceptions: report only fixed diagnostics and allowlisted validated fields (Tasks 1 and 3).
3. State changes while reading: detect file identity/size/mtime changes and return an inconclusive result rather than a consistent-looking snapshot (Task 1).
4. Missing optional dependencies: status and help must still run; preflight reports dependency gaps without importing transport modules (Tasks 2 and 3).
5. Successful local inspection mistaken for live permission: both formats explicitly report live checks and release authorization as unverified (Task 3).

## Scope and file map

Create `scripts/storage/storage_inspection.py` for safe reads, normalized reports and local capability checks. Create `scripts/storage/tests/test_storage_inspection.py` and `scripts/storage/tests/test_inspection_cli.py`. Modify `scripts/storage/maintenance_cli.py` only for argument parsing and early dispatch/lazy imports. Update `docs/runbooks/jellyfin-storage.md` with commands and limitations.

No changes to `maintenance_lock.py`, release logic, native record hashes, service manifests or workflow dispatch. Later plans cover supervised execution/recovery, service profiles/shared admission, and isolated rebuild/retirement. This plan does not satisfy those later acceptance gates.

## CLI and report contract

New commands:

```text
python3 scripts/storage/maintenance_cli.py status --service jellyfin --state-root /var/lib/homelab-maintenance [--json]
python3 scripts/storage/maintenance_cli.py preflight --service jellyfin --state-root /var/lib/homelab-maintenance [--json]
```

`--state-root` and `--service` are required for these commands, preventing accidental inspection of a different mount. The service directory is `<state-root>/operations/jellyfin`; the shared ownership file and runner marker are at the root. New options are rejected for legacy operations, rather than silently ignored. Legacy invocations remain valid.

Report schema 1: `schema`, `command`, `service`, `scope` (`local-only`), `observed_at`, `checks` (list of `id`, `status`, fixed `message`, allowlisted `details`), `live_verified` (false), `release_authorized` (false). Check statuses: `pass`, `fail`, `unknown`, `not_checked`. Exit 0 means all required local checks passed; 1 means failed or unknown required checks; argparse usage errors remain 2. Unperformed live checks are `not_checked` and never make local success imply live success.

No raw input objects, credential paths/content, nonce, owner identity, arbitrary exception strings or subprocess output in reports. Report stage names only after validating their format. Report hashes/revisions only after validating their expected hexadecimal format. State age derived from file mtime is labeled as file age, not evidence freshness; semantic timestamps must be separately parsed as timezone-aware timestamps. Future timestamps are unknown, not fresh.

### Task 1: Safe local state inspection

**Files:** Create `storage_inspection.py` and `tests/test_storage_inspection.py` under `scripts/storage/`.

**Interfaces:** `inspect_state(root: Path, service: str, *, now: datetime) -> dict` produces the report contract above. It performs no external commands. Reuse the unchanged `render_storage.record_hash` for comparison.

- [ ] Write tests for a valid synthetic Jellyfin directory; missing root/record; invalid JSON; non-object JSON; symlinked parent/file; FIFO; oversized file; mismatched service; changed file during observation; and secret sentinel strings in unknown fields and parser errors. Assert files and directory entries remain unchanged, sentinel strings never appear, and outcomes distinguish missing, malformed, contradictory and unstable state.
- [ ] Run `python3 -m unittest discover -s scripts/storage/tests -p test_storage_inspection.py -v`; confirm failure from the missing module/interface.
- [ ] Implement safe bounded regular-file reads using descriptor-relative traversal, `O_NOFOLLOW`, `O_NONBLOCK` and `fstat`; reject `..`, relative roots and symlink components. Limit each JSON file to 1 MiB. Recheck observed file metadata after collection; changes yield `unknown`. Document that this detects changes but does not provide a transaction across external writers.
- [ ] Inspect `runner-instance`, `operation.json`, `operations/jellyfin/record.json`, `stages.json`, `placement.json`, and `target-may-have-written.json`. Validate schema-1 ownership fields privately without emitting nonce/owner; check instance against the runner marker. Validate the native record's service and completeness with the existing renderer, without emitting rendered data. Validate stages as revision mappings and placement against the keys consumed by `observe_release`. A present first-write receipt must have `target_may_have_written: true` and the matching native hash; absence means unknown, never “safe rollback.” Do not infer a current stage from Git mappings: report the ownership stage separately.
- [ ] For existing `onboarding.jsonl` and `snapshot-intent.jsonl`, report presence and file age as unresolved inspection work (`unknown`); do not invent journal-completion semantics. Missing journals are `not_checked`. Runtime installation/revision evidence absent from legacy state is `not_checked`, with no fabricated version claim. These limits must appear in the runbook.
- [ ] Run the Task 1 tests; require all pass. Commit as `feat(storage): add read-only retained state inspection`.

### Task 2: Local preflight capability report

**Files:** Extend `storage_inspection.py` and `tests/test_storage_inspection.py`.

**Interfaces:** `preflight(root: Path, service: str, *, now: datetime) -> dict` extends Task 1's report with local capability checks. Use `shutil.which`, `importlib.metadata` and filesystem metadata; do not execute found binaries or import optional packages.

- [ ] Add failing tests with mocked PATH/package metadata for missing SSH, missing kubectl, missing websocket-client, mismatched transport version, missing maintenance helper, and unavailable filesystem statistics. Assert no subprocess/network calls, no secret-file content reads, and no filesystem mutations.
- [ ] Run Task 1's test command and confirm the new cases fail for missing preflight behavior.
- [ ] Report Python version; availability of `ssh`, `kubectl`, `tar`, `systemctl`; installed `websocket-client` versus the exact requirement in `scripts/storage/requirements.txt`; and discoverability of `maintenance_lock` without importing it. Clearly label executable presence as presence only, not executable version or feature qualification. Read-only inspection itself remains usable without these tools.
- [ ] Report available bytes on the state filesystem using `statvfs`; do not call this backup capacity or compare it with Jellyfin worker space thresholds. No backup destination is selected in this PR. Worker tools, remote capacity, NAS identity and live bindings are `not_checked`. Missing prerequisites and unavailable local capacity produce nonzero preflight results.
- [ ] Rerun the focused tests and commit as `feat(storage): report local maintenance prerequisites`.

### Task 3: CLI integration, operator documentation and regression verification

**Files:** Modify `scripts/storage/maintenance_cli.py`, update `docs/runbooks/jellyfin-storage.md`, create `scripts/storage/tests/test_inspection_cli.py`.

**Interfaces:** Early CLI dispatch calls Task 1/2 functions; text and JSON rendering share the same report. Preserve existing named helpers used by current tests, including `verify_recovered_chap` and `observe_release`.

- [ ] Add subprocess CLI tests for status/preflight JSON and text, required arguments, unknown service, and refusal of new options on legacy commands. Run in an environment without websocket-client/maintenance_lock and without credential environment variables. Assert status/help load successfully, preflight reports missing dependencies, and output contains `local-only`, false release authorization, and fixed sanitized diagnostics.
- [ ] Add in-process tests using spies that fail if NAS, `require_maintenance`, `mutate_kube`, `probe_filesystem`, or subprocess execution is reached by either new operation. Snapshot fixture bytes and entries before/after. Retain existing CLI helper tests to catch import regressions.
- [ ] Run `python3 -m unittest discover -s scripts/storage/tests -p test_inspection_cli.py -v`; confirm failures before routing changes.
- [ ] Extend argument parsing, dispatch inspection before legacy transport imports, and move only imports necessary for optional-dependency independence. Do not rewrite legacy operation bodies. Render fixed text lines or JSON; sanitize failures without printing traceback/input data. Make command exit codes match the report contract.
- [ ] Update the runbook with both commands, root mapping (`/var/lib/homelab-maintenance` on the runner versus `/maintenance` in its container), exit codes, local-only limits and handling of unknown journals/state. State explicitly that output cannot be used as release evidence and does not replace the existing maintenance workflow.
- [ ] Run `python3 -m unittest discover -s scripts/storage/tests -v` with the pinned transport and PyYAML test dependencies installed. Require all existing 82 baseline tests plus new tests to pass. The SQLite-copy test needs a writable `/var/tmp`; treat environment denial separately from a product failure.
- [ ] Run `pre-commit run --files scripts/storage/storage_inspection.py scripts/storage/maintenance_cli.py scripts/storage/tests/test_storage_inspection.py scripts/storage/tests/test_inspection_cli.py docs/runbooks/jellyfin-storage.md` and `git diff --check`. If a tool is absent, report that check as unrun and run the applicable available checks; do not claim equivalent full hook validation.
- [ ] Commit as `feat(storage): expose local status and preflight commands`. Review the entire diff against zero mutation, redaction, compatibility and scope requirements. Open a PR describing the affected tooling, tests and lack of live rollout. Attach the PR to this task. Do not merge or dispatch maintenance.

## Completion and next boundary

This PR is complete when local inspection works on synthetic legacy-compatible state without secrets or transport dependencies, preflight reports gaps honestly, regressions pass and the reviewed PR is available. No production state is needed for unit tests or sample output.

The next implementation plan covers qualified runtime and supervised execution, including its own Ansible changes and failure-injection environment. Do not begin that work, delete pilot tools, enroll another service or claim rebuild recovery as a consequence of completing this PR.
