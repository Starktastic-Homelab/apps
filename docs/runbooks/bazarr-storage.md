# Bazarr retained storage and PostgreSQL

Private files now live on the NFS claim `media/bazarr-files` (see the
[ordinary-file runbook](ordinary-file-storage.md)). The `bazarr-config-block` volume and
`vm-9999-bazarr.raw` described below, and the original NFS source, were
[retired on 2026-11-16](../../infrastructure/system/proxmox-csi/README.md#retired-migration-sources-2026-11-16); those parts of this page are history.

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
| Former SQLite source (deleted 2026-11-16) | `10.9.8.30:/mnt/apps/pv/media/bazarr` |

The stock image stays pinned. The `retained-state` init runs the generic marker guard (`infrastructure/base-configs/files/retained-startup/guard.py`, ConfigMap `retained-startup-guard`)
with `bazarr /config config`: it refuses startup unless the marker above is a regular
file holding exactly that content and a newline. It no longer checks credentials,
configuration, the database schema or SQLite files, and there is no startup SQL check.
Missing data must fail startup rather than create a fresh installation. The former SQLite source, its PVC and its admission policy
were deleted on 2026-11-16; there is no SQLite fallback.

Ordinary rebuilds use the existing Terraform/Ansible cohort and verified retirement
procedure. Retained images and sealed declarations rebind through GitOps. RWOP,
verified retirement and the shared storage fencing policy protect the writer;
the marker guard alone does not establish safe writer retirement.

Recovery requires matching PostgreSQL and configuration backups. Stock Bazarr's
PostgreSQL-mode ZIP backup contains configuration only; its SQLite-oriented restore
UI does not restore the PostgreSQL database. Use the shared complete PostgreSQL
backup and a verified config backup, with writers fenced before restore. The
cutover's encrypted cold-source and SQL recovery copies were
[retired on 2026-11-16](../../infrastructure/system/proxmox-csi/README.md#retired-migration-sources-2026-11-16).
After PostgreSQL has accepted production writes, reopening the old SQLite source
would discard newer state; choose a verified forward or reverse recovery first.

The qualified importer uses pinned pgloader with `reset no sequences`, then restores
actual discovered allocator floors and compares every typed field, stock constraint
and index. Its automatic sequence reset fails on a mixed-case identifier and can
leave foreign keys missing. Row counts alone are insufficient acceptance evidence.
