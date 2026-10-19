# Retained ordinary-file storage

The [assessment](../superpowers/reports/2026-10-19-ordinary-file-storage-assessment.md)
selects ten ordinary-file volumes. Their fixed bindings are declared by
`infrastructure/base-configs/files/ordinary-file-volumes.json` and rendered by
`templates/ordinary-file-storage.yaml` inside the base-configs chart.
The active workload values select these prepared NFS claims. Preparing bindings alone does not switch workload mounts. Do not mount a fresh
empty target into an application: retained identity guards must pass first.

For each authorized cutover:

1. Record exact Git revision, Application/controller/Pod/PVC/PV identities, raw
   image handle and target NAS directory identity. Require healthy nodes, current
   enrollment and successful read-only SQL guards. Refuse reused target paths.
2. Hold only the relevant Argo owners against automated reconciliation. Hold
   frontend Service selectors before scaling the selected controller to zero;
   wait for its old Pods, runtime processes and mounts to retire. Hold Filebrowser
   during target population because it has an umbrella writable apps mount.
3. Create a temporary helper with the retired CSI source mounted read-only and
   the fresh NFS target mounted writable. Check bindings and source identity.
   Run `scripts/ordinary-file-storage/copy_files.py` with the contract's marker
   and identity. Refuse changed source, nonempty target, special files, external
   hard links, extended metadata or populated filesystem recovery directories.
4. Preserve the copy receipt and original raw image. Remove only the exact helper
   Pod and wait for source detach before starting the app. Never auto-delete data
   after an uncertain result or overwrite a partially populated target on retry.
5. Reconcile the workload's claim through a reviewed green PR. Keep images,
   configuration, enrollment and startup guards unchanged. Start one Pod, require
   native API/data checks, recreate it, and qualify another worker attachment.
   Release its frontend only after acceptance and current Git/live equality.
6. Remove only owned holds, restore Filebrowser and verify all owners healthy,
   original unrelated resources unchanged and the selected old CSI images detached.

Before target startup, the retired original CSI source remains the rollback source.
After target startup can write, preserve the newest NFS files and shared database;
never automatically revert to an older ordinary-file tree or stale SQLite source.
A failed acceptance pauses for diagnosis with both trees intact.

RWO expresses single-node intent; NFS does not provide CSI's RWOP fencing. Keep
one Recreate replica and the established verified VM-retirement rebuild procedure.
Capacity requests on NFS do not enforce quotas. Back up private files as well as
PostgreSQL; a SQL backup does not contain attachments, DataProtection keys or
private user files. Original pre-PostgreSQL NFS admission holds remain active.

The `ordinary-file-retired-csi-hold` admission policy denies new Pods using the
ten retired CSI claims. It must be installed only after all transfer helpers
have retired. An ordinary Git rollback is therefore insufficient to restart an
old source; deliberate recovery must account for writes made on the NFS target.
