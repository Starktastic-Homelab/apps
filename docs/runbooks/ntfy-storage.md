# ntfy PostgreSQL and retained CSI recovery

Private files now live on the NFS claim `operations/ntfy-files` (see the
[ordinary-file runbook](ordinary-file-storage.md)). The `ntfy-data-block` volume and
`vm-9999-ntfy.raw` described below, and the original NFS source, were
[retired on 2026-11-16](../../infrastructure/system/proxmox-csi/README.md#retired-migration-sources-2026-11-16); those parts of this page are history.

ntfy stores its database state in shared PostgreSQL and its attachments on retained
Proxmox CSI. Runtime startup requires accepted enrollment, retained filesystem
identity and the existing physical PostgreSQL schema.

ntfy uses the existing shared PostgreSQL enrollment/completion path. Its users,
password hashes, access tokens, ACLs, preferences, messages, statistics and webpush
stores must be preserved together. The existing `ntfy-webpush-secret` carries the
VAPID identity; do not rotate it as part of storage recovery.

The attachment volume is `operations/ntfy-data-block`:8GiB ext4,
ReadWriteOncePod, Retain, backed by
`homelab//k3s-block/9999/vm-9999-ntfy.raw`. It mounts at `/var/cache/ntfy` and requires
`.homelab-ntfy-data` containing `homelab/ntfy/data/v1` plus the attachments directory.
The retained guard refuses SQLite fallback, missing identity, a different physical
PostgreSQL server, missing stock schema, and unaccepted current enrollment inputs.
A newly empty database or disk is never a recovery procedure.

Ordinary node replacement and full metadata rebuild reuse the retained disk and
shared database through the existing Terraform/Ansible verified-retirement workflow.
Do not bypass RWOP or force-detach a disk while its old VM generation can still
write. No Velero checkpoint or manually created application database is required.

Before authoritative PostgreSQL startup, recovery could have resumed the unchanged cold
SQLite sources only after all target/source writers and mounts retired and complete
source fingerprints match. After startup, preserve newest PostgreSQL writes; stale
SQLite must never be reopened as an automatic rollback; those sources no longer
exist. Use the current shared
PostgreSQL backup/recovery workflow.

The original `ntfy-config` and `ntfy-cache` sources, their admission hold, the raw
image and the encrypted cutover recovery copies were
[retired on 2026-11-16](../../infrastructure/system/proxmox-csi/README.md#retired-migration-sources-2026-11-16).
The SQL guard's physical identifier changes only through a separately accepted
PostgreSQL physical recovery.

The initial conversion uses the unchanged importer from ntfyv2.29.0. Source schema
markers must not be edited. Populated `user_email`/`user_magic_link`, duplicate
message IDs or malformedUTF8/NUL are rejection conditions, not permission to drop
state. See the [qualification report](../superpowers/reports/2026-10-15-ntfy-assessment.md).

Production cutover and recovery/lifecycle acceptance are recorded in the
[completion report](../superpowers/reports/2026-10-15-ntfy-production-completion.md).

## Native image schema upgrades

The SQL guard accepts exactly user/message/webpush 9/15/1 and 9/16/1, including
only the latter's `message.claimed_at BIGINT NOT NULL` column. Unknown versions
remain blocked. No CI check covers this: before merging an ntfy image change,
confirm by hand that its schema stays guard-compatible. No production DDL is part of a guard compatibility fix.
