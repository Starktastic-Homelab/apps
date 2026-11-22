# Grafana PostgreSQL and retained CSI recovery

Private files now live on the NFS claim `monitoring/grafana-files` (see the
[ordinary-file runbook](ordinary-file-storage.md)). The `grafana-data-block` volume and
`vm-9999-grafana.raw` described below, and the original NFS source, were
[retired on 2026-11-16](../../infrastructure/system/proxmox-csi/README.md#retired-migration-sources-2026-11-16); those parts of this page are history.

Grafana keeps its database state in shared PostgreSQL and its private files,
including plugins, on retained Proxmox CSI. Startup requires accepted current
PostgreSQL enrollment and the retained file marker.

The file volume is `monitoring/grafana-data-block`: 2GiB ext4,
ReadWriteOncePod, Retain, backed by
`homelab//k3s-block/9999/vm-9999-grafana.raw`. It mounts at `/var/lib/grafana` and
requires `.homelab-grafana-data` holding exactly `homelab/grafana/data/v1` and a
newline, checked by the generic marker guard (`infrastructure/base-configs/files/retained-startup/guard.py`, ConfigMap `retained-startup-guard`). It no longer checks the plugins directory, SQLite files,
database configuration or the PostgreSQL server, and there is no startup SQL check.
An empty replacement database or disk is never a recovery procedure.

Ordinary node replacement and full Kubernetes metadata rebuild reuse the retained
disk and enrolled shared database through the existing Terraform/Ansible verified
retirement workflow. Do not bypass RWOP or force-detach storage while the old VM
generation can still write. No Velero checkpoint or manually created Grafana
database is required.

Keep the existing admin, OIDC and renderer Secrets, Grafana encryption
configuration and shared PostgreSQL credentials. The cutover preserves encrypted
data and keys without rekeying. A successful key-rewrap command alone does not
prove that existing encrypted values can be decrypted. Keep the image and
encryption configuration together when upgrading Grafana.

The chart's dashboard and datasource sidecars synchronize their provisioning files
before Grafana starts, then continue watching. Preserve their service account,
discovery RBAC and startup ordering: absent provisioning files can cause upstream
Grafana to delete provisioned dashboards as orphans.

Before authoritative PostgreSQL startup, the unchanged cold SQLite source could have
been resumed only after every target writer and attachment has retired and complete
source fingerprints match. After startup, preserve the newest PostgreSQL writes;
never reopen stale SQLite as an automatic rollback (that source no longer exists). Recover the database with the
shared PostgreSQL backup/recovery workflow and recover private files from their
`grafana-files` volume and its backup.

The original `monitoring/kube-prometheus-stack-grafana` NFS source, its admission
hold, the raw disk and the cutover recovery ciphertexts on VM300 and the operator workstation
were [retired on 2026-11-16](../../infrastructure/system/proxmox-csi/README.md#retired-migration-sources-2026-11-16). The scheduled full PostgreSQL backup covers
the Grafana role and database; it does not cover private files.

See the [qualification report](../superpowers/reports/2026-10-16-grafana-assessment.md)
for the data conversion and independent recovery requirements.

The [production completion report](../superpowers/reports/2026-10-16-grafana-production-completion.md)
records the accepted live migration, recovery tests and cleanup.
