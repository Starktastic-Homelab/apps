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
engine starts only after the read-only guard validates its app-specific retained
marker and required native paths. Valid empty Alertmanager files are accepted.
An absent/wrong marker or missing native state stops startup for investigation;
do not create a marker to bypass the guard or initialize an empty replacement.

Preserve the image digests, native retention and notification/service endpoints.
Tempo uses app-template5.2.1 with its original native ConfigMap, Service,
ServiceAccount and ServiceMonitor declared explicitly. The shared-chart Grafana
PostgreSQL deployment and all existing credentials stay unchanged.

The NAS dataset requires the full-growth reserve for every existing raw image,
these additional33Gi, 512Mi staging and8Gi spare headroom. The dataset
quota is192Gi after the completed migration. Before later growth, recheck actual
dataset identity, pool health, free space and complete growth commitments.
A quota increase is not a physical-space reservation or a new backup.

Production migration is serialized under native maintenance ownership and an
owned scoped Argo hold. Each source and every ancestor/root-share writer retires
before the cold copy. Keep the original NFS source and accepted recovery media.
Merge reviewed desired CSI bindings under the hold before the first target writer;
never return to stale NFS after target authority begins. Helper/old-writer API,
runtime, mount, device and Proxmox references must retire before another writer.
No forced detach or unreachable-node assumption is part of the procedure.

Recovery ciphertext is retained outside Git on VM300 and the operator computer,
with separately protected keys. Before using a recovery copy, verify its complete
SHA256 and decrypt/restore independently, preserving every file, native POSIX
metadata and engine history. Native fixtures must have no production scrape,
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

The original Prometheus15d/8GiB policy remains in force. During stock first
startup, normal size retention expired one verified oldest18h block; the user
explicitly accepted that exact expiry. Its data remains in the encrypted cold
backup. This is not permission to ignore other missing history or WAL failures.
Tempo's qualified zero-byte shutdown WAL scaffold contained no trace payload;
only physically proven empty scaffolds were accepted during migration, and
nonempty/corrupt/unproven replay loss still blocked acceptance.

Cold ciphertext and complete manifests are retained on VM300 under
`/var/lib/homelab-maintenance/operations/monitoring-csi-cutover-20261016/recovery/`
and on the operator computer under
`~/.local/share/homelab-recovery/monitoring-csi-cutover-20261016/`.
Keys remain separate: the VM300 operation's `keys/` directory and
`~/.config/homelab-recovery-keys/monitoring-csi-cutover-20261016/` on the computer.
Native audit ciphertext is on both hosts; local/final audit ciphertexts and the
sanitized final cleanup terminal are on the computer. These verified recovery
copies are point-in-time backups. Arrange future backup/restore work separately;
retained disks and fresh Kubernetes metadata reconstruction are not backups.
