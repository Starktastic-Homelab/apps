# Retained monitoring startup and production sources

`guard.py` checks an app-specific retained identity and required native paths
read-only, before the stock application starts. It prevents missing-state
bootstrap. It does not parse/repair WAL, prove all historical records, or replace
backup/restore qualification with the exact native image.

`production/` contains the reviewed source definitions used by the native cutover
and mirrored into the service and base-configs sources. Merge their desired CSI
state only under the owned Argo hold, after the first cold recovery/population
passes and before its first target writer. Retained guards reject unpopulated
images during an unexpected rebuild. Subsequent per-app source holds are created
only after each original writer retires. Do not apply them while an original app
still serves NFS. The shared guard and static bindings belong to base-configs.

Prometheus/Alertmanager use the stock operator's custom claim-template naming.
Loki disables chart-generated claims and automatic PVC deletion. Tempo uses the
approved existing app-template chart with explicit native configuration, Service,
ServiceAccount and ServiceMonitor. Its original container remains named tempo;
the inherited placeholder is disabled through the chart's supported option.

Keep exact image tags/digests and current retention. Prometheus gets16Gi for its
existing15d/8GB policy, Alertmanager2Gi, Loki10Gi and Tempo5Gi. Every raw image is
static ext4/RWOP/Retain on the existing Proxmox CSI driver. No controller fork or
application patch is involved. Normal metadata rebuilds reuse known retained
bindings and verified old-VM retirement.

Run `python3 scripts/test-monitoring-retained.py`. Set
`MONITORING_RETAINED_RENDERS` to a directory with prometheus.yaml,
alertmanager.yaml, loki.yaml and tempo.yaml rendered using the actual value
cascade to include integration checks. Native recovery and production acceptance
are separate operation gates; a passing local render is not a completed rollout.
