# pgAdmin PostgreSQL and retained CSI recovery

pgAdmin keeps its complete configuration database in shared PostgreSQL and private
files on retained Proxmox CSI. Startup requires accepted current enrollment, the
retained file identity and the expected native SQL schema and application keys.

The file volume is `databases/pgadmin-data-block`:1GiB ext4, ReadWriteOncePod,
Retain, backed by `homelab//k3s-block/9999/vm-9999-pgadmin.raw`. It mounts at
`/var/lib/pgadmin` and requires `.homelab-pgadmin-data` containing
`homelab/pgadmin/data/v1` plus `storage`, `sessions` and `azurecredentialcache`.
The guard rejects SQLite engine/backup files, competing configuration, missing
state and the wrong physical PostgreSQL server. An empty database or replacement
disk is never a recovery procedure.

Ordinary worker replacement and full Kubernetes metadata rebuild reuse the static
retained image and enrolled shared database through the existing Terraform/Ansible
verified retirement workflow. Do not bypass RWOP or force-detach while the old VM
generation can still write. No Velero checkpoint, manual database creation or
per-rebuild pgAdmin conversion is required.

Keep the existing `pgadmin-secret` administrator credential and original internal
user hash, database keys and encrypted saved server credentials. The canonical
restricted credential is `pgadmin-postgres-secret`, whose mounted `uri` is a quoted
Python string required by the stock entrypoint. It uses the shared `pgadmin`
database/role and a pool limited to two connections plus one overflow connection.
No application patch or new controller is involved. Retain the current internal
and webserver authentication settings and saved-server declarations.

The SQL guard checks the complete native schema catalog, migration markers,
original key fingerprints, active administrator and physical PostgreSQL identity
before stock pgAdmin can initialize anything. Keep image/schema signatures and
guard qualification together on upgrade. Deliberate application-key rotation or
physical PostgreSQL recovery requires separate acceptance of new guard inputs.

Before authoritative PostgreSQL startup, the unchanged cold SQLite source may be
resumed only after every target writer and attachment retires and complete source
fingerprints match. After startup, preserve newest PostgreSQL writes and recover
from accepted current SQL media; never automatically reopen stale SQLite. Recover
private files from the retained disk or their accepted encrypted backup. Scheduled
full PostgreSQL backups cover the role/database; they do not back up private files.

The original `databases/pgadmin-pgadmin4` NFS claim/PV and NAS directory remain
retained and admission-held. Do not mount them to a new pgAdmin writer or remove
them as temporary migration files. Retained raw storage and the database are
independent of disposable k3s VMs.

Cutover ciphertexts are retained on VM300 under
`/var/lib/homelab-maintenance/operations/pgadmin-csi-pg-cutover-20261016/recovery/`
and on this computer under
`~/.local/share/homelab-recovery/pgadmin-csi-pg-cutover-20261016/`.
Keys remain separate: VM300's operation `keys/` directory and this computer's
`~/.config/homelab-recovery-keys/pgadmin-csi-pg-cutover-20261016.key`.
Keep them protected outside Git.

See the [qualification report](../superpowers/reports/2026-10-16-pgadmin-assessment.md)
and [production completion report](../superpowers/reports/2026-10-16-pgadmin-production-completion.md)
for the accepted preservation, independent recoveries, lifecycle and cleanup evidence.
