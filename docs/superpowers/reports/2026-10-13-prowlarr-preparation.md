# Prowlarr inactive preparation qualification

The merged Prowlarr PostgreSQL/retained-CSI proposal has app-specific preparation
sources under [scripts/prowlarr-postgresql](../../../scripts/prowlarr-postgresql/README.md).
This is an inactive preparation package, not production execution acceptance.
It changes no discovered service values, PostgreSQL manifests or base-configs
templates. No production credential/data transfer, enrollment, allocation, hold
or downtime occurred during preparation.

Focused checks cover retained configuration read-only acceptance/rejection,
Secret projections, duplicate/conflicting XML, absent credentials and SQLite
fallback; exact embedded script bytes and encrypted-input fingerprint; both gate
identities and stale/failed hook rejection; preserved prior ciphertext and new
main/log app keys; and exact retained binding/RWOP/Recreate/placement/mounts.
The actual app-template 5.2.1 render uses globals, common, media-arr-common,
current Prowlarr values and the inactive final overlay. Native PostgreSQL 18.6
checks use one disposable local container with synthetic inputs and no network,
verify populated/main-version requirements and SCRAM password rejection, and
delete only that fixture. CI repeats these focused checks plus ordinary validation.

Twenty-one focused tests passed with actual render and native SQL enabled. ConfigMap
generation uses literal scalars: a formatter regression changed embedded Python
bytes and was caught by the fingerprint/code-equality tests, then fixed and tested
again after formatting. No credentials were regenerated. Initial SQL-fixture
loopback trust was replaced with explicit SCRAM initialization so a wrong-password
test exercises authentication; no production authentication settings changed.

Independent review identified a missing final activation flag: Prowlarr's
`app.yaml` must set `manifests: true` for its new guards/Secret to become durable
desired state. An inactive metadata patch, explicit activation instruction and
failing-to-passing discovery contract test address it; current app discovery is
unchanged during preparation. No other blocking or minor findings remained.

This reuses existing consumer acceptance, SQL enrollment, storage and verified
VM-retirement contracts. It does not repeat generic live enrollment, full cluster
replacement or the accepted real-copy conversion rehearsal. Conversion from old
SQLite remains unsupported upstream. The full latest cold source, independent
restore, real integrations, healthy-worker movement and final Git/live matching
are mandatory execution gates, not established by these fixture tests.

Before execution approval, freeze the native private command package and current
identities, propose absolute time boundaries and private transfer destinations,
and review capacity/writers. The pre-outage enrollment activation must be durable
Git and pass a full native hook; the final app/storage merge follows accepted live
availability, keeping the owned hold until reconciliation finishes.
