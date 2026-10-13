# Seerr PostgreSQL enrollment and retained CSI preparation

This package implements the [merged design](../../docs/superpowers/specs/2026-10-13-seerr-postgresql-csi-design.md)
for Seerr and Seerr-RU. The shared PostgreSQL enrollment hook now declares both
canonical owners, and each application discovers its own PostgreSQL SealedSecret.
Both services remain on their original NFS/SQLite configuration. The retained
CSI bindings, source holds and startup values in this package remain outside
ApplicationSet discovery until the separately approved cutover and reconciliation.

The read-only settings guard accepts only the instance marker, preserved API,
session, client and VAPID identifiers, canonical PostgreSQL environment and no
active SQLite files. It never creates or repairs configuration. `main.sql` runs
as each canonical owner in a read-only transaction; it rejects missing stock
tables, missing pinned PostgreSQL migrations or an absent administrator user.
These structural guards supplement the full data-preservation acceptance from
the [disposable rehearsal](../../docs/superpowers/reports/2026-10-13-seerr-preflight.md).

Each instance has its own ordinary SQL owner/database, completion ServiceAccount,
Secret and retained4GiB RWOP volume. Only enrollment init sees the projected API
token; only the database-login init sees the password file. Main and retained-state
receive their own Secret password through environment. The settings mount is
read-only in the guard. Common behavior stays in the base values; Seerr-RU's
small override switches only instance bindings. All health probes use stock local
`/api/v1/status/appdata`, avoiding an external GitHub update fetch.

## Local verification

Use existing Python/PyYAML, Helm4.3.0, kubeconform, Docker, kubectl and kubeseal.
The encrypted bundle is prepared already; do not regenerate credentials.
The generator reuses the qualified Prowlarr serializer and existing enrollment
adapter without modifying either application's active resources.

```sh
helm template seerr app-template --repo https://bjw-s-labs.github.io/helm-charts \
  --version 5.2.1 --namespace media -f templates/globals.yaml -f templates/common.yaml \
  -f services/media/seerr/values.yaml -f scripts/seerr-postgresql/production/values.yaml \
  > /tmp/seerr-retained.yaml
helm template seerr-ru app-template --repo https://bjw-s-labs.github.io/helm-charts \
  --version 5.2.1 --namespace media -f templates/globals.yaml -f templates/common.yaml \
  -f services/media/seerr/values.yaml -f scripts/seerr-postgresql/production/values.yaml \
  -f scripts/seerr-postgresql/production/seerr-ru/values.yaml > /tmp/seerr-ru-retained.yaml
SEERR_SQL_TEST=1 SEERR_RETAINED_RENDER=/tmp/seerr-retained.yaml \
  SEERR_RU_RETAINED_RENDER=/tmp/seerr-ru-retained.yaml python3 scripts/test-seerr-retained-startup.py
```

The SQL fixture is one uniquely named local no-network PG18.6 container, bounded
CPU/memory/tmpfs, with synthetic credentials and data only; cleanup removes only
that container. The tests also preview base-configs from a temporary copy and
verify separate static bindings. No cluster apply or real data is used.

`prepare.py sources` regenerates only non-secret source serialization after an
intentional source edit. For enrollment this migration's exact original completed
bundle is retained privately under the ignored
`.superpowers/retained-artifacts/seerr-postgresql-csi-preparation/encrypted-bundle/`; `publish_enrollment(output)` can reserialize those
same ciphertexts without sealing again. `prepare.py enrollment --output <private,
exclusive path>` is for initial preparation only: existing output is refused,
intermediate completed bundles remain on failure, and every previous aggregate
ciphertext is preserved. It uses `scripts/seal.sh` with the verified public
certificate; passwords flow only through captured private stdin, never into Git.
Re-run byte/generation comparisons after pre-commit because formatting must not
alter fingerprinted ConfigMap data.

## Activation mapping, only after execution approval

| Inactive source | Future destination |
| --- | --- |
| `production/values.yaml` | Merge into `services/media/seerr/values.yaml`, preserving image/service and the actual value cascade |
| `production/seerr-ru/values.yaml` | New `services/media/seerr-ru/values.yaml`, instance overrides only |
| Each `production/<instance>/app-metadata.yaml` | Merge flags into that app's `app.yaml`; preserve baseApp, phase and ingress |
| Each `production/<instance>/consumer-gate.yaml` | That instance's `manifests/postgres-completion-gate.yaml` |
| `production/guard-configmap.yaml` | `services/media/seerr/manifests/retained-startup-guard.yaml`; shared by both media instances |
| Each `production/enrollment/<instance>-application-secret.yaml` | That instance's `manifests/<instance>-postgres-secret.yaml` |
| Each `production/<instance>/source-hold.yaml` | That instance's `manifests/source-hold.yaml` |
| Each `production/<instance>/{pv,pvc}.yaml` | `infrastructure/base-configs/templates/<instance>-block-storage/` |
| `production/enrollment/enrollment-{configmap,job,secret}.yaml` | Corresponding PostgreSQL `manifests/` files |

The metadata patches must enable `manifests: true` in both apps and
`valuesOverride: true` in Seerr-RU. Otherwise resources/variant values escape
permanent discovery. The common guard ConfigMap is provided by the base app in
the shared media namespace; no guard/code duplication is needed in the variant.

Publish separately approved enrollment inputs before downtime. Require the full
successful current hook, idempotent retry, canonical restricted logins and unchanged
PostgreSQL physical identity; prepared ciphertext alone creates no SQL objects.
The final app/storage/source-protection changes belong to the later live-state
reconciliation PR after acceptance, while maintenance holds remain active.

That execution proposal must freeze current identities, commands, allocation
reservations, private destinations and absolute outage/recovery checkpoints.
Recheck full4GiB reservations for both images against quota/growth/snapshots.
Fence both app writers, Filebrowser's parent-directory access, the NFS provisioner
and any other current NAS/client writer before a fresh cold capture. Acquire the
existing VM300 maintenance owner and scoped native hold; do not rebuild the
cluster between live activation and final merge.

Verify encrypted recovery copies on VM300 and this computer, with the key
separate, then prove recovery before stock target startup. Preserve originals,
WAL, symlink metadata, settings and all typed rows through the qualified conversion.
After first target writes, rollback requires preserving newest target data through
a fresh consistent reverse conversion or restore with an explicitly accepted
loss boundary. A stale source or Git revert is insufficient.

Require live integrations, fresh human sign-in/history when needed, clean
recreation and healthy-worker movement. Reconcile final merged-main render/live
state, recover captured stale operations through the qualified procedure, start
observation before release, release only the owned hold, and complete a six-minute
Healthy/Synced watch after reconciliation. Cleanup removes only captured temporary
generations/copies; protected NFS sources and encrypted recovery remain.
Preparation approval does not authorize these production steps.
