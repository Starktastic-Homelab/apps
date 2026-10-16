# Monitoring retained-CSI migration

User authority: migrate Prometheus, Alertmanager, Loki and Tempo autonomously,
including preparation, isolated qualification, scoped downtime, Git reconciliation
and PR merges. Pause for a material preservation or deployment decision or missing
access. Apply the existing unmodified Proxmox CSI / verified VM retirement design.

## Outcome and boundaries

Retain each service's current data, image, application configuration, retention,
service endpoints and existing integrations. Metrics, silences/notification log,
log chunks/index/WAL and trace blocks/WAL stay in their native engines. Shared
PostgreSQL and Grafana are not storage-migration targets. No new operator, CSI
fork, object-store deployment, database conversion or loss exception is assumed.
Cold cutovers interrupt collection/ingestion; existing agent retries are bounded,
so continuous collection throughout downtime is not an acceptance claim.

Use one static ext4 RWOP/Retain raw image per service, cache none, existing worker
placement/verified-retirement contracts, prune/delete protection, native read-only
retained identity checks, old-source admission protection and scoped native Argo
sync holds. Ordinary fresh Kubernetes metadata rebuilds bind these known retained
images from Git without Velero, conversion or a manual metadata checkpoint.

## Current facts, October 16

Prometheus3.15.0-distroless/Alertmanager0.34.1, Prometheus Operator0.94.1 and
kube-prometheus-stack91.9.0. Both are operator-owned single-replica StatefulSets,
NFS claims10Gi/2Gi, UID1000:GID2000 subpaths prometheus-db/alertmanager-db.
Prometheus retention15d/8GB remains unchanged. Targets16Gi and2Gi.
Loki3.6.11/chart7.3.0 single binary filesystem TSDB,10Gi NFS, UID10001;
30d retention unchanged, target10Gi. Tempo2.9.0/chart1.24.4 single binary local
backend,5Gi NFS, UID10001,72h retention and existing OTLP/metrics generation
unchanged, target5Gi. All currently Ready. Loki and Tempo each have two existing
restarts; baseline is not permission for fresh target restarts or recovery errors.
Observed logical file bytes: Prometheus7979713298, Alertmanager530,
Loki1966808751, Tempo59835318. Refresh before production.

Current CSI quota160Gi, available96.56Gi. Outstanding raw growth83.31Gi + new33Gi
+512Mi staging +8Gi headroom requires124.81Gi available. Quota192Gi would provide
128.56Gi; pool apps is ONLINE with278.88Gi physical free. Recheck full reservations
and physical capacity before any quota increase or allocation. No unrelated
quota, snapshots, disks, source claims or recovery media are cleanup candidates.

## Delivery adapters

Prometheus Operator supports custom volumeClaimTemplate names: use fixed
prometheus-data-block and alertmanager-data-block templates, static retained PVs
and precreated deterministic ordinal0 claims. Preserve native subpaths. Pause
only each relevant CR, retire its old Pod completely, and replace its exact
zero-writer StatefulSet for immutable-template changes. Keep the old claims.

Loki chart can disable generated claim templates and supply a named external CSI
volume and native init guard through supported values. Disable automatic PVC
deletion, retaining old source claims before any scale-down.

Tempo chart1.24.4 is deprecated and exposes neither init containers nor a direct
startup-command override. The approved alternative uses the already-installed
app-template5.2.1 chart and preserves native image/config/labels/services/ports,
ServiceMonitor, metrics generator and single-Pod semantics. The exact mapping and native recovery were qualified before production.
Do not silently omit the guard, fork the Tempo chart or add an admission controller.

## Preservation and recovery

Use exact current VM/runner ownership and protected durable receipts. A lost or
failed phase is never replayed; inspect its known terminal and continue only the
unexecuted work. Archive exact files/POSIX metadata and compare every restored
file, not just counts. Isolated stock-image fixtures have no production scrape,
alert receiver, remote write, memberlist peer or reachable production network.
Application metrics/logs/traces/alert data may contain private information; keep
copies root-only/0700 outside Git, and retain AES256 recovery ciphertext on VM300
and this computer with separate outside-Git keys. Infrastructure credentials and
production Kubernetes authentication/configuration Secrets must not enter labs.
If automatic review requires specific sensitive-transfer approval, prepare the
exact payload/destination proposal and ask, without copying first.

Prometheus: verify every block, original WAL recovery, bounded historical queries
for each block and near shutdown, then live scrape/rule/remote-write health.
Alertmanager: preserve complete silences and native notification state; isolate
all receivers in fixtures; check production routing unchanged and native APIs.
Loki: verify complete file restore, native recovery, fixed historical query
fingerprints and new ingestion. The September WAL exception applied only to that
NFS operation and is not carried forward; any newly encountered replay/loss
limitation needs a separate decision. Tempo: verify blocks/WAL, fixed trace IDs
and historical search plus fresh OTLP ingestion and unchanged native metrics-generator wiring. Inspect any pre-existing inactive integration separately.
No synthetic production alert or user notification is authorized by this plan.

## Execution and acceptance

Qualify all paths before production. Serialize app cutovers and quota/attachment
changes under the existing native owner. Preserve unrelated apps while holding
only owning Argo Applications (kube-prometheus-stack, loki, tempo, base-configs
and overlapping Filebrowser/NFS provisioner as required). Gracefully stop/retire
all overlapping source writers before cold archive. Use no forced detach or
unreachable-node assumption. A failed pre-authority gate can return to the
unchanged source only after all target writers retire; after authority preserve
newest target writes and recover from accepted current media, never stale NFS.

Merge the reviewed CSI desired definitions under the owned Argo hold before the first target writer. Remaining unpopulated disks fail closed on an unexpected rebuild. Each app must pass original native data/API checks, clean Pod recreation,
healthy-worker movement and restored ordinary worker scheduling with the same
retained filesystem. Final Git must render accepted live resources exactly.
Inspect exact-head CI and Argo diff before every authorized merge; preserve all
existing syncOptions including RespectIgnoreDifferences=true when retiring held
queues. Release only the owned hold under a continuous six-minute typed workload
and Pod watch; require every scoped app Healthy/Synced and full current-source
operations with original credentials unchanged. Then clean only exact owned
temporary state, encrypt audits and release the owner last. Keep old source,
retained targets, accepted encrypted media and keys. Publish sanitized evidence
and recovery instructions; final local plaintext deletion follows report merge.

## Primary references

- https://prometheus.io/docs/prometheus/latest/storage/
- https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/v0.94.1/pkg/prometheus/server/statefulset.go
- https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/v0.94.1/pkg/alertmanager/statefulset.go
- Exact downloaded charts: kube-prometheus-stack91.9.0, loki7.3.0, tempo1.24.4.
- Existing live-storage-migrations design and Grafana/pgAdmin recovery runbooks.
