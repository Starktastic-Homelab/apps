# Bazarr retained storage and PostgreSQL

Bazarr uses the shared PostgreSQL18 server for database `bazarr`, owned by role
`bazarr`. The existing enrollment hook provisions its login from sealed inputs;
startup waits for acceptance of the current inputs and verifies that login.
Existing settings and integration credentials remain in `/config`.

| State | Binding |
|---|---|
| Private configuration | `media/bazarr-config-block`,4GiB ext4, RWOP, Retain |
| Image | `k3s-block:9999/vm-9999-bazarr.raw` |
| CSI handle | `homelab//k3s-block/9999/vm-9999-bazarr.raw` |
| Config identity marker | `.homelab-bazarr-config`: `homelab/bazarr/config/v1` |
| Shared PostgreSQL physical ID | `7584099661242523698` |
| Media/subtitles | Existing NFS `media-library-pvc`, mounted at `/data` |
| Protected former SQLite source | `10.9.8.30:/mnt/apps/pv/media/bazarr` |

The stock image stays pinned. The retained guard rejects missing/wrong config,
credentials or database identity, an incomplete schema and active SQLite files.
Both native PostgreSQL environment settings and `postgresql.enabled: true` in the
preserved config must agree. Missing data must fail startup rather than create a
fresh installation. The source admission policy prevents mounting the former
SQLite PVC; its retained data is recovery evidence, not an automatic fallback.

Ordinary rebuilds use the existing Terraform/Ansible cohort and verified retirement
procedure. Retained images and sealed declarations rebind through GitOps. RWOP,
verified retirement and the shared storage fencing policy protect the writer;
a marker or database guard alone does not establish safe writer retirement.

Recovery requires matching PostgreSQL and configuration backups. Stock Bazarr's
PostgreSQL-mode ZIP backup contains configuration only; its SQLite-oriented restore
UI does not restore the PostgreSQL database. Use the shared complete PostgreSQL
backup and a verified config backup, with writers fenced before restore. The
cutover procedure also retains encrypted cold-source and SQL recovery copies on
VM300 and the operator computer, with the recovery key kept separately outside Git.
After PostgreSQL has accepted production writes, reopening the old SQLite source
would discard newer state; choose a verified forward or reverse recovery first.

The qualified importer uses pinned pgloader with `reset no sequences`, then restores
actual discovered allocator floors and compares every typed field, stock constraint
and index. Its automatic sequence reset fails on a mixed-case identifier and can
leave foreign keys missing. Row counts alone are insufficient acceptance evidence.
