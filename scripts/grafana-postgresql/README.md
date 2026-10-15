# Grafana PostgreSQL and retained CSI preparation

`prepare.py sources` generates inactive manifests and a kube-prometheus-stack
values overlay. It never applies resources. The overlay keeps the current image,
OIDC/admin/renderer Secrets, URLs and chart discovery RBAC. It uses the existing
Grafana service account for the shared enrollment gate rather than replacing it.

The chart's native sidecars remain running after initial synchronization. Their
startup probes delay Grafana until dashboard and datasource provisioning files are
present. Missing provider/files caused stock orphan cleanup to remove resources
in a disposable rehearsal; keeping the actual files passes all 35 dashboards.
This uses upstream chart options and the installed unmodified sidecar image.

The file guard requires the retained marker and plugins directory, canonical
PostgreSQL credentials and no `grafana.db` fallback artifacts. The read-only SQL
guard checks the physical server, role/database, table owners, the entire stock
catalog and all four native backend migration logs. Its signatures exclude log
serial IDs and execution timestamps. Keep the image, schema signatures and guard
qualification together when changing Grafana versions. `catalog.sql` and
`migrations.sql` document the native signature inputs.

`data.py` materializes only legacy Go UTC timestamp strings in a new working copy.
The original source remains untouched. Comparison covers every application field
and duplicate under explicit PostgreSQL timestamp, CHAR-padding and strict UTF-8
representations. Keep all backend schema-operation logs native; omitted obsolete
source tables must remain empty. Stock schema initialization and the data-only
loader are separate, exclusive operations in the reviewed execution package.

`prepare.py enrollment --output <new-private-directory>` prepares one append-only
strictly sealed enrollment. It preserves existing ciphertext and never applies it.
Retain partial output on an uncertain result; do not regenerate a password on retry.

Run `python3 scripts/test-grafana-data.py` and
`python3 scripts/test-grafana-retained-startup.py`. Set `GRAFANA_RETAINED_RENDER` to
an actual layered Helm render for integration checks. `GRAFANA_SQL_CONTAINER`
explicitly selects the labelled, port-free qualification fixture for native SQL
negative tests; it must never select a production container.

The [design](../../docs/superpowers/specs/2026-10-16-grafana-postgresql-csi-design.md),
[qualification](../../docs/superpowers/reports/2026-10-16-grafana-assessment.md) and
[remaining execution plan](../../docs/superpowers/plans/2026-10-16-grafana-postgresql-csi.md)
separate accepted rehearsal evidence from production acceptance. The 2Gi retained
volume and five-connection main SQL pool fit the fresh full-growth/headroom checks.
No production activation is represented by this preparation directory.
