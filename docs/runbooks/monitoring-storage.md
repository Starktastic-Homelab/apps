# Monitoring retained storage

Prometheus, Alertmanager, Loki and Tempo retain their stock native data on static
Proxmox CSI ext4 disks in `k3s-block`, owned independently of worker VM lifecycles.
The verified bindings are checked into base-configs; the normal application value
cascade and verified VM-retirement handoff apply after a fresh Kubernetes rebuild.
No Velero checkpoint or manual Kubernetes-metadata recovery is required.

| Service | Capacity | Raw image below images/9999 | Native path |
| --- | --- | --- | --- |
| Prometheus | 16Gi | vm-9999-prometheus.raw | prometheus-db |
| Alertmanager | 2Gi | vm-9999-alertmanager.raw | alertmanager-db |
| Loki | 10Gi | vm-9999-loki.raw | filesystem chunks/index/WAL |
| Tempo | 5Gi | vm-9999-tempo.raw | traces/WAL |

All bindings are RWOP/Retain and protected against Argo prune/delete. Each stock
engine starts only after the generic marker guard (`infrastructure/base-configs/files/retained-startup/guard.py`, ConfigMap `retained-startup-guard`) finds its marker on the volume root:
`.homelab-<app>-data` holding exactly `homelab/<app>/data/v1` and a newline, that is
`.homelab-prometheus-data`, `.homelab-alertmanager-data`, `.homelab-loki-data` and
`.homelab-tempo-data`. It checks no native paths and never creates or repairs data.
An absent/wrong marker stops startup for investigation;
do not create a marker to bypass the guard or initialize an empty replacement.
The single exception is a disaster-recovery re-initialisation of a lost image per
ansible `docs/backup-and-restore.md`, "Re-initialise an excluded image", pre-approved
by Ben on 2026-11-16 and allowed only once the image is missing and no replica
copy of it exists.

Preserve the image digests, native retention and notification/service endpoints.
Tempo uses app-template5.2.1 with its original native ConfigMap, Service,
ServiceAccount and ServiceMonitor declared explicitly. The shared-chart Grafana
PostgreSQL deployment and all existing credentials stay unchanged.

The NAS dataset requires the full-growth reserve for every existing raw image,
these additional33Gi, 512Mi staging and8Gi spare headroom. The dataset
quota was raised to192Gi for this migration; the [CSI README](../../infrastructure/system/proxmox-csi/README.md) has the current value. Before later growth, recheck actual
dataset identity, pool health, free space and complete growth commitments.
A quota increase is not a physical-space reservation or a new backup.

Production migration is serialized under native maintenance ownership and an
owned scoped Argo hold. Each source and every ancestor/root-share writer retires
before the cold copy. The original NFS sources, their holds and the recovery media
were [retired on 2026-11-16](../../infrastructure/system/proxmox-csi/README.md#retired-migration-sources-2026-11-16).
Merge reviewed desired CSI bindings under the hold before the first target writer;
never return to stale NFS after target authority begins. Helper/old-writer API,
runtime, mount, device and Proxmox references must retire before another writer.
No forced detach or unreachable-node assumption is part of the procedure.

Native fixtures must have no production scrape,
receiver, peer or remote-write destinations. For ordinary VM replacement, retain
the known raw disks and use the existing verified-retirement handoff.

Completion requires fixed historical/native APIs, new ingestion, clean recreation,
healthy-worker movement and restored ordinary worker placement, then exact desired
resources, all scoped current-source Argo operations and a continuous six-minute
typed workload/Pod watch. Local linting and healthy startup alone do not establish
completed migration or preserved history. Collection/ingestion pauses during cold
cutover; agent retries are bounded and do not guarantee gap-free new telemetry.


## Completed migration and recovery media

The [production completion report](../superpowers/reports/2026-10-16-monitoring-production-completion.md)
records independent cold restores, live history/fresh ingestion, Pod recreation,
healthy-worker movement, current-source Argo reconciliation and the accepted
six-minute continuous watch for all four services.

The original Prometheus15d/8GB policy remains in force. During stock first
startup, normal size retention expired one verified oldest18h block; the user
explicitly accepted that exact expiry. Its data was in the encrypted cold backup,
retired on 2026-11-16. This is not permission to ignore other missing history or WAL failures.
Tempo's qualified zero-byte shutdown WAL scaffold contained no trace payload;
only physically proven empty scaffolds were accepted during migration, and
nonempty/corrupt/unproven replay loss still blocked acceptance.

The `monitoring-csi-cutover-20261016` cold ciphertext, manifests, audit copies and
keys on VM300 and the operator workstation were
[retired on 2026-11-16](../../infrastructure/system/proxmox-csi/README.md#retired-migration-sources-2026-11-16). Retained disks and fresh Kubernetes metadata
reconstruction are not backups.
