# PostgreSQL enrollment operations

The first activation declares only the retained synthetic `pg-enrollment-pilot`
canary. Its SQL database and role are `homelab_enrollment_pilot`; PostgreSQL
reserves role names beginning with `pg_`. Existing application databases and
credentials are not adopted or changed by this activation. PostgreSQL remains on
its current retained NFS volume, chart and Pod template.

The expected physical system identifier is `7584099661242523698`. Installation
requires the separately approved one-time bootstrap of the admin-only
`homelab_enrollment.enrollments` registry in the maintenance database `postgres`.
Bootstrap is not part of Git reconciliation. Never bootstrap again because a
new cluster cannot find the registry: confirm the retained data and resolve the
failure. Normal enrollment refuses a missing registry or different server.

## Canonical inputs

The PostgreSQL Application owns the generated enrollment ConfigMap,
generation-specific Sync Job, encrypted aggregate credential and two named
read-only completion Roles. The canonical declaration lives in `config.json`
inside `infrastructure/controllers/databases/postgres/manifests/enrollment-configmap.yaml`.
Runtime scripts, Job template and ciphertext fingerprint are one matching bundle;
rebuilds and hook retries do not generate or reseal passwords.

Use the existing [preparation helper](../../scripts/postgres-enrollment/README.md)
for each approved consumer, starting with the current config and encrypted
aggregate. Preserve prior ciphertext and unrelated application Secret keys.
Integrate the helper's generated gate into actual chart values and render its
dedicated ServiceAccount, ordered init containers and exact volume mounts before
merging. Runtime/gate/Job-template changes require regenerating the matching
ConfigMap and Job from existing ciphertext. Do not patch only one input.

Existing databases require a separate `adopt` review, complete privilege and
application inventory, and their verified current credential. Adoption preserves
their password, data and grants. Rotation, renaming, ownership transfer, SQL
deletion, application converters and PostgreSQL's NFS-to-CSI move are separate.

## Acceptance and recovery

Run a **full PostgreSQL Application sync**. Selective or apply-only sync is not
enrollment acceptance. The Sync hook runs after server health; successful hooks
are cleaned up, failed hooks retain evidence. A failed PostgreSQL hook can hold
later services-phase Argo rollouts. Existing application Pods continue running.

New consumers first require current successful full-hook acceptance, then verify
canonical database login. The API token is confined to the acceptance init; the
main application receives only its own database credential. Missing/stale Argo
metadata, unavailable API or denied reads keeps fresh Pods waiting. Existing
running Pods do not continuously recheck acceptance.

The services-phase canary has no ingress, Service or PVC. It writes one fixed-key
sentinel only after both init checks, verifies the same payload on every start,
and never overwrites a mismatch. Its readiness marker confirms that startup
verification completed; it is not a continuous PostgreSQL availability monitor.
Keep the declaration, encrypted credentials and sentinel for future rebuilds.

If a hook fails, inspect its sanitized logs and current input generation, resolve
the cause, and retry a full sync. Canonical login failure never resets an
established password or recreates a database. Stop and inspect durable receipts
before retrying an uncertain bootstrap outcome. Removing declarations or
reverting manifests does not drop SQL objects or the ledger; any such deletion
requires separate approval.

The [disposable qualification record](postgresql-enrollment-qualification.md)
establishes the tested lifecycle and limits. Activation receipts are preserved on
VM300 under
`/var/lib/homelab-maintenance/operations/pg-enrollment-production-pilot/receipts/`.
Source delivery, registry bootstrap and successful live pilot rollout are distinct
milestones; a green PR alone does not establish the latter two.
