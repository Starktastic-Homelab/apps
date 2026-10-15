# ntfy PostgreSQL and retained CSI recovery

ntfy stores its database state in shared PostgreSQL and its attachments on retained
Proxmox CSI. Runtime startup requires accepted enrollment, retained filesystem
identity and the existing physical PostgreSQL schema.

ntfy uses the existing shared PostgreSQL enrollment/completion path. Its users,
password hashes, access tokens, ACLs, preferences, messages, statistics and webpush
stores must be preserved together. The existing `ntfy-webpush-secret` carries the
VAPID identity; do not rotate it as part of storage recovery.

The prepared attachment volume is `operations/ntfy-data-block`:8GiB ext4,
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

Before authoritative PostgreSQL startup, recovery may resume the unchanged cold
SQLite sources only after all target/source writers and mounts retire and complete
source fingerprints match. After startup, preserve newest PostgreSQL writes; stale
SQLite must never be reopened as an automatic rollback. Use the current shared
PostgreSQL backup/recovery workflow and the encrypted cutover recovery copies.

Original `ntfy-config` and `ntfy-cache` sources remain retained and admission-held.
Do not mount them to another writer or delete their NAS directories as cleanup.
The retained raw image and shared database are also outside disposable VM lifecycle.
The SQL guard's physical identifier changes only through a separately accepted
PostgreSQL physical recovery.

The initial conversion uses the unchanged importer from ntfyv2.29.0. Source schema
markers must not be edited. Populated `user_email`/`user_magic_link`, duplicate
message IDs or malformedUTF8/NUL are rejection conditions, not permission to drop
state. See the [qualification report](../superpowers/reports/2026-10-15-ntfy-assessment.md).
