# Retained storage tooling audit

Date: 2026-09-29. Scope: source and local tests, not a fresh production health assessment.

Audited fetched revisions:

- Apps: `a3f979d0bef0849fe57aa464ad04e6a92b7ec1cd`.
- Ansible: `2542043676a7af1cd5d8ddfbbe7d39ce59b68a95`.

The user checkout is an older, unrelated branch. Source was read from the fetched revisions and exported to `/tmp/iscsi-hardening-audit-20260929` for tests. Existing checkout changes were preserved. Historical operational evidence is indexed by [the hardening brief](../../handoffs/2026-09-24-iscsi-hardening-brief.md).

## Findings

| Priority | Evidence | Consequence and proposed treatment |
| --- | --- | --- |
| Before a second service | `scripts/storage/render_storage.py:60`: the PV alias expression matches every PV using `org.democratic-csi.retained`, while its validation permits only the recorded Jellyfin PV. Policy, authorization and CHAP names also contain Jellyfin; namespace policy names are global. | Renaming fields per service is insufficient: independently generated policies would conflict. Generate shared admission from the complete enrolled set, plus service-specific writer checks. Test two services and unknown aliases against a real disposable API server. |
| Before supported resume | Ansible `scripts/maintenance_lock.py`, `_guard`, `verify`, `advance`: the file lock covers metadata access, not the operation body. | Original-owner verification does not serialize two commands using the same owner and nonce. GitHub concurrency helps only that workflow. Add an execution mutex covering the entire supervised operation without holding the existing metadata guard across nested verification. |
| Before the next window | `.github/workflows/storage-maintenance.yml`: floating `python:trixie`, runtime pip installation, kubectl without an explicit version; hardcoded runner identity and Jellyfin credential path. | Dependencies can change between preparation and execution. Ansible should install a versioned, qualified runtime; preflight must check every operation's local and remote dependencies. Keep workflow and manual execution on the same entry point. |
| Before crash recovery claims | `scripts/storage/initiator_probe.py:85`: login precedes the cleanup `try`; mount/session ownership is otherwise process-local. | An uncertain login reply or process loss requires inspection. Persist intent and observed resource ownership, then reconcile exact sessions and mounts; never infer permission to disconnect an existing session. |
| Before generalization | `maintenance_cli.py:21` and `observe_release`; `release.py:34`; `jellyfin_backup.py:18`. | State paths, app/CronJob identities, credential references, backup destination and space budgets are fixed. Separate operational configuration from immutable native identity. `verify` performs login/mount work and must not be presented as read-only status. |
| Preserve compatibility | `render_storage.py:11`, `record_hash` hashes the entire native record. | Adding operational settings to that record would change identity hashes and invalidate existing evidence. Keep the record byte semantics and current first-write boundary; introduce a separate versioned profile. |
| Before supported long captures | `jellyfin_backup.py`, `capture_stream`, and the historical supervised capture described in the brief. | Guards, partial output and exit checks already exist, but durable supervision should be a supported interface. Publish success only after archive, hash and manifest are complete; reconcile interrupted publication without blessing partial data. |
| Usability, preserving safety | `cutover_guards.py:20`, `verify_target_hold` requires an exact reviewed Git revision. | Unrelated merges can invalidate a long operation. Preserve this default. Add explicit reviewed revision advancement with fresh hold checks; do not replace it with a naive path hash or silently accept HEAD. |
| Recovery prerequisite | Ansible maintenance-runner role creates state outside k3s, but on VM300. | Recovery from k3s replacement and recovery from runner replacement are different. Document and test restoration of protected runner state from an independent destination before claiming runner-loss recovery. |

These are source-derived limitations, not claims that concurrent production writers or data corruption occurred.

## Keep, consolidate, retire

| Item | Disposition |
| --- | --- |
| Native identity, CHAP verification, static Retain/RWOP bindings, generation checks, fail-closed admission | Keep, with compatibility tests. |
| Existing ownership lock, intent/readback logic, backup integrity checks, first-write evidence | Keep; expose supported interfaces instead of hand-editing receipts. |
| CLI/workflow, temporary launchers, SSH/Python snippets, manual placement and stage updates | Consolidate into the maintained entry point and supervised executor. Temporary tools are candidates for retirement only after equivalent recovery paths pass. |
| Jellyfin image, backup semantics, semantic `Healthy` check and playback acceptance | Keep explicitly application-specific. |
| Repeated runtime setup and copied source trees | Replace with qualified versioned installation and recorded revisions. Preserve historical evidence. |
| Old NFS data, ZVOLs, snapshots, accepted backups and operation receipts | Preserve. Their deletion is outside this cleanup. |

No temporary file is declared safe to delete by this audit. The brief identifies categories and evidence roots; a deletion manifest must enumerate actual paths, ownership and replacement evidence when retirement is ready.

## Validation

The current Apps snapshot passes **82 storage unit tests** under Python 3.14 with `websocket-client==1.9.2` and test dependency `PyYAML==6.0.3`. The first attempt used an incomplete export and lacked dependencies and `/var/tmp` write permission; those harness problems were corrected before the passing run. Logs: `/tmp/iscsi-hardening-audit-20260929/tests-qualified.log` (temporary).

All **9 Ansible maintenance-lock tests** also pass, including competing ownership acquisition. Multiprocessing required permission to create a local socket outside the restricted sandbox. These tests do not cover competing execution under the same owner.

Disposable API-server admission qualification, runner/systemd failure injection, NAS/cluster access, and full cluster rebuild were not run. Unit results do not establish those properties or current production health.

## Recommendation

Proceed with the [incremental hardening design](../specs/2026-09-29-retained-storage-hardening-design.md). Start with read-only inspection and dependency qualification, then durable execution, then multi-service admission. Another application migration remains behind those qualification gates. PostgreSQL eligibility remains a [separate workstream](../../handoffs/2026-09-24-postgresql-migrations.md).
