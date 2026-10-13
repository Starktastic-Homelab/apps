# Seerr and Seerr-RU inactive preparation

The approved [plan](../plans/2026-10-13-seerr-postgresql-csi-preparation.md)
implements the [accepted design](../specs/2026-10-13-seerr-postgresql-csi-design.md)
outside ApplicationSet discovery. No discovered app, PostgreSQL, base-configs or
bootstrap file changes. No production enrollment, storage allocation, hold,
data copy or workload restart was performed.

## Prepared behavior

Both instances retain separate PostgreSQL databases/owners, Secrets, completion
accounts and 4GiB ext4 RWOP configuration claims. Common behavior stays in Seerr's
base overlay; Seerr-RU overrides only its bindings. Static PVs use owner9999
images, Retain and pruning/deletion protection. Old-claim admission policies are
prepared but inactive; parent-directory writers still require execution fencing.

The read-only startup guard refuses missing or malformed settings identifiers,
wrong markers, conflicting environment, symlinks and remaining SQLite files.
Enrollment acceptance precedes canonical database login. The SQL guard refuses
uninitialized databases; full row/settings preservation remains a cutover gate.
Only the enrollment init sees a projected API token, and only database init sees
the password file. All probes use stock local `/api/v1/status/appdata`.

Two encrypted enrollment declarations were prepared once using the existing
generator and `scripts/seal.sh`. Prior declarations and ciphertext remain intact;
each application Secret retains strict instance/namespace scope. Existing or
partial output refuses regeneration. Prepared ciphertext creates no SQL objects.

## Verification

- Sixteen Seerr tests passed with both actual app-template5.2.1 value cascades,
  the prospective base-configs chart from a temporary copy, and one bounded
  no-network PG18.6 fixture using synthetic data. No required test was skipped.
- All 25 existing shared enrollment tests and the native canary passed. An initial
  run lacked sandbox access to Docker; the same suites passed with Docker access.
- Kubeconform validated all25 package/app resources and all32 prospective
  base-configs resources without errors or skipped schemas. Relevant pre-commit,
  YAML, documentation-link/image and whitespace checks passed. Regeneration plus
  formatting restored exact committed bytes, including original ciphertext.
- Both rendered Pods select their own claim, Secret, account and database with
  retained-state, enrollment and database init ordering. Neither inherits a
  Pod fsGroup mutation; the original UID/GID1000 and image pin remain.
- Negative checks rejected a Seerr-RU render missing its override, absent/invalid
  retained state, stale/failed enrollment acceptance, wrong credentials and
  incomplete PostgreSQL data. Accepted fixtures remained unchanged. Eight
  main-only environment mutations are rejected by the actual render contract.
- Read-only production checks found no proposed SQL identities, declarations or
  application Secrets, and confirmed the existing PostgreSQL physical identity,
  current declaration equality and public sealing-certificate provenance.
- Embedded guard/gate bytes, hook generation and prior encrypted values match
  their qualified sources. The same render, schema and native tests are wired
  into hosted CI.

The [package README](../../../scripts/seerr-postgresql/README.md) maps every
inactive file to its eventual discovery location and carries the source fencing,
encrypted recovery, live/Git reconciliation and release/watch requirements.
Next is a private production execution package with fresh identities, allocation
budgets, exact commands and absolute outage/recovery checkpoints. This preparation
does not authorize those operations.

## Independent review

The independent final review found no critical issues. Its important finding was
that the render contract accepted main-only `CONFIG_DIRECTORY`, `API_KEY`,
`DB_SOCKET_PATH` and `envFrom` overrides invisible to the separate guard. Eight
negative mutations reproduced the gap; the corrected contract rejects them for
both instances. The full sixteen-test suite passed after the fix.

Deferred minor: `publish_enrollment()` reads and writes inputs sequentially; a
missing later input can partially overwrite inactive output. Preloading all five
inputs before publication would improve recoverability. Exact completed bundles
are retained privately, and no live resources are applied by this helper.

Production enrollment/conversion/integration/movement/release checks remain in the
separately approved execution scope; judging them from preparation would overclaim
rollout readiness. Ciphertext decryption and live credential agreement also remain
execution gates because this review uses no operational credentials. If either
gate is omitted later, local consistency alone cannot establish production safety.
