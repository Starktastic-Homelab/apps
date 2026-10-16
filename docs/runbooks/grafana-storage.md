# Grafana PostgreSQL and retained CSI recovery

Grafana keeps its database state in shared PostgreSQL and its private files,
including plugins, on retained Proxmox CSI. Startup requires accepted current
PostgreSQL enrollment, the retained file marker and the expected native SQL schema.

The file volume is `monitoring/grafana-data-block`: 2GiB ext4,
ReadWriteOncePod, Retain, backed by
`homelab//k3s-block/9999/vm-9999-grafana.raw`. It mounts at `/var/lib/grafana` and
requires `.homelab-grafana-data` containing `homelab/grafana/data/v1` plus the
plugins directory. The guard rejects missing identity, SQLite fallback files,
competing database configuration or a different physical PostgreSQL server.
An empty replacement database or disk is never a recovery procedure.

Ordinary node replacement and full Kubernetes metadata rebuild reuse the retained
disk and enrolled shared database through the existing Terraform/Ansible verified
retirement workflow. Do not bypass RWOP or force-detach storage while the old VM
generation can still write. No Velero checkpoint or manually created Grafana
database is required.

Keep the existing admin, OIDC and renderer Secrets, Grafana encryption
configuration and shared PostgreSQL credentials. The cutover preserves encrypted
data and keys without rekeying. A successful key-rewrap command alone does not
prove that existing encrypted values can be decrypted. Keep the image, native
catalog and migration-log signatures, guard qualification and encryption
configuration together when upgrading Grafana.

The chart's dashboard and datasource sidecars synchronize their provisioning files
before Grafana starts, then continue watching. Preserve their service account,
discovery RBAC and startup ordering: absent provisioning files can cause upstream
Grafana to delete provisioned dashboards as orphans.

Before authoritative PostgreSQL startup, the unchanged cold SQLite source may be
resumed only after every target writer and attachment has retired and complete
source fingerprints match. After startup, preserve the newest PostgreSQL writes;
never reopen stale SQLite as an automatic rollback. Recover the database with the
shared PostgreSQL backup/recovery workflow and recover private files from their
retained disk or accepted encrypted recovery copy. A physical PostgreSQL recovery
also needs separate acceptance of its new physical identifier in the SQL guard.

The original `monitoring/kube-prometheus-stack-grafana` NFS claim, PV and NAS
directory remain retained and admission-held. Do not mount them to a new writer or
delete them as disposable migration state. The retained raw disk and shared
database remain outside the disposable k3s VM lifecycle.

Cutover recovery ciphertexts are retained on VM300 under
`/var/lib/homelab-maintenance/operations/grafana-csi-pg-cutover-20261016/recovery/`
and on this computer under
`~/.local/share/homelab-recovery/grafana-csi-pg-cutover-20261016/`.
Their keys are separate: VM300's operation `keys/` directory and this computer's
`~/.config/homelab-recovery-keys/grafana-csi-pg-cutover-20261016.key`.
Keep both protected outside Git. The scheduled full PostgreSQL backup covers the
Grafana role and database; it does not replace the private-file recovery copy.

See the [qualification report](../superpowers/reports/2026-10-16-grafana-assessment.md)
for the data conversion and independent recovery requirements.

The [production completion report](../superpowers/reports/2026-10-16-grafana-production-completion.md)
records the accepted live migration, recovery tests and cleanup.
