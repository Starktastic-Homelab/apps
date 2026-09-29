# Retained storage hardening design

Status: proposed for review. This document authorizes no live maintenance action.

## Outcome and boundaries

An operator should be able to inspect, run and recover retained-storage maintenance from checked-in documentation and durable state, without chat history, temporary launchers or manual receipt edits. k3s must remain replaceable while application data and its verified identity survive. Before another service migrates, demonstrate recovery after interruption and intentional cluster rebuild/rebinding.

The [source audit](../reports/2026-09-29-retained-storage-tooling-audit.md) identifies the concrete gaps. PostgreSQL migration research proceeds separately. Jellyfin's unreproduced SQLite contention remains an application investigation; this work does not claim to fix it.

## Approach

Recommended: evolve the existing Python modules behind one supported operator command, using systemd for durable execution and the existing external ownership record. This preserves reviewed checks and keeps repository responsibilities familiar.

Merely tidying shell wrappers would leave execution ownership and interruption recovery unresolved. A Kubernetes controller or general migration framework would add lifecycle complexity and place recovery machinery inside the cluster being rebuilt. Neither is recommended.

## Ownership and configuration

- Apps owns storage operations, service profiles, admission generation and application acceptance.
- Ansible owns runner installation, qualified tool versions, systemd execution, permissions, host identity and the existing shared maintenance lock.
- Packer retains worker OS prerequisites; Terraform retains VM resources. No new image or VM change is assumed necessary by this design.

Use a versioned service profile for namespace, workload and background-writer identities, authorization resource names, old/new claims, credential file references, backup root and space budgets. Accept only established fields, not arbitrary executable hooks. Keep Jellyfin backup/acceptance code explicit until a second application demonstrates reusable behavior.

Do not add profile fields to the existing native identity record or change its hashing. Preserve existing Jellyfin resource names and receipts. Existing state is inspected in place; any future conversion must be separately qualified and must preserve the original ownership and first-write boundary.

## Operator interface

Extend the existing CLI with explicit service and state-root selection. Paths must resolve within the configured protected root without symlink escapes. Secrets remain in restrictive files and never appear in reports or command lines.

- `status`: inspect durable records and report stage, runtime/revisions, evidence age and unresolved intent. Missing, malformed and contradictory state are distinct outcomes. Redact owner nonces and credentials.
- `preflight`: check installed tools, configuration, capacity and read-only live observations when requested. Report failed and unknown prerequisites. It must not log in to iSCSI, mount, alter authorization, acquire ownership or advance stages.
- Existing mutating operations run through one supervised executor. Filesystem probing is explicitly classified as an owned maintenance operation, even when mounting read-only.
- `reconcile`: compare recorded intent with fresh observations, report discrepancies and perform only an explicitly selected, supported recovery action. It never means retry every unfinished mutation.

Use human-readable output and structured JSON from the same result. Nonzero status means a failed/unknown required precondition. Inspection success never implies permission to release a writer.

## Execution and interruption

Maintain two separate protections: persistent original-owner authorization and a per-runner execution mutex. The mutex covers the full operation including child processes; a second same-owner command must refuse while one is active. Do not reuse the short-lived metadata guard for this purpose.

An Ansible-installed systemd service executes a validated request using a recorded Apps revision and qualified runtime. GitHub Actions and manual CLI calls submit and inspect that same service. Limit submissions to supported operations and validated arguments, not arbitrary shell text. Disconnecting the client does not stop execution. No automatic restart/retry of mutations after runner reboot.

Persist operation intent before side effects, then observations and completion with atomic, validated receipt APIs. Record runtime versions, source revisions, timestamps and sanitized failure reasons. Preserve private diagnostics under restricted permissions. If serialization fails, no empty success receipt may be published.

On uncertain NAS replies, login, mount or process termination, retain the hold and inspect first. An owned-resource receipt identifies host generation, target, session/device and mount before cleanup is allowed. Failed unmount forbids logout. Existing unrelated sessions must never be adopted or disconnected.

Backup success requires successful producer exit, valid final guard, hashes and complete manifest. Partial archives remain explicitly incomplete. Recovery after a crash between archive and manifest publication must validate both before acceptance. Keep independent restore and application-level acceptance separate from archive integrity.

## Durable state and revision changes

Keep protected operation state outside k3s under the existing runner root. Back it up with credential recovery material to an independent protected destination. Never write secrets to Git or ordinary CI artifacts. Runner replacement needs a documented restore and explicit identity reconciliation; a changed runner identity must not silently inherit ownership.

Preserve exact reviewed Git revision checks initially. A later supported revision-advance operation must revalidate the held workload and relevant rendered resources and record the reviewed transition. Do not automatically accept an unrelated merge based only on changed paths: charts, shared values and ApplicationSets can affect the result.

## Multiple retained services

Generate shared driver admission once from the complete set of enrolled native records. Any PV using the retained driver must match exactly one enrolled binding. Preserve protections against aliases by IQN and inline iSCSI. Unknown enrollment, duplicate backend identity and mismatched bindings fail closed.

Generate writer authorization per service; deduplicate namespace-generation rules by namespace. Services sharing a namespace remain independently held/released. Missing authorization, forged labels and stale worker/namespace generations remain denied. Preserve existing Jellyfin names during this transition.

Changing the shared admission set is a separate reviewed rollout with real API-server tests. A fixture with two services must demonstrate both legitimate bindings succeeding and cross-service substitution failing. No second production enrollment is part of implementing the fixture.

## Delivery boundaries

1. **First small PR: read-only status and preflight.** Add explicit state selection, redacted reporting, malformed-state handling and a dependency/capability report. Read existing records unchanged. Tests demonstrate zero mutation calls. Document local versus live-read checks. No workflow switch or admission change.
2. **Qualified execution and recovery.** Ansible runtime/service installation, full-operation serialization, durable receipts, supported reconciliation and supervised backup integration. Qualify interrupted calls and restart recovery in a disposable runner environment before enabling production use.
3. **Shared admission and profiles.** Preserve Jellyfin compatibility, introduce an inert second-service fixture and exercise real Kubernetes admission. Review generated manifest differences before deployment.
4. **Rebuild rehearsal and retirement.** Restore runner state and destroy/recreate an isolated k3s environment, deliberately rebind retained data, verify exact identity and semantic readiness, then inventory and retire superseded source/tooling. Preserve all historical evidence and retained data.

These are delivery boundaries, not permission to deploy or begin another maintenance window. A detailed implementation plan follows design approval.

## Acceptance gates

- A new operator can determine stage, missing prerequisites and recovery action from documented commands alone.
- Two same-owner processes cannot mutate concurrently; client loss does not lose execution evidence; runner reboot cannot automatically replay a write.
- Lost replies, partial archives, failed unmount, stale identity, ownership loss and missing tools leave the writer closed and produce actionable diagnostics.
- Existing native hashes, first-write receipts and Jellyfin bindings remain compatible.
- Both enrolled-service fixtures work, while unknown/aliased/cross-service bindings and stale authorizations are denied by a real API server.
- An isolated rebuild preserves filesystem identity and data; independently restored application state passes semantic readiness.
- Every retired tool has a tested supported replacement. Data deletion requires a separate decision.

Unit tests alone cannot satisfy the executor, admission or rebuild gates. Production verification and deployment remain explicit later steps.
