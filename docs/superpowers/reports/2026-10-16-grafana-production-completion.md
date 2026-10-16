# Grafana production migration completed

Grafana now uses shared PostgreSQL and retained Proxmox CSI for private files.
Enrollment [PR #1367](https://github.com/Starktastic-Homelab/apps/pull/1367) and
activation [PR #1369](https://github.com/Starktastic-Homelab/apps/pull/1369) are merged.
Activation merge is `9b6dce35e646c90814f35b2c1b667e92d068008b`; all five hosted checks passed on
exact head `e1eef35af53fb1db82e97e5ac8b3a2b35328a4d2` before merging.

## Preservation and recovery

The actual cold source's 87 application tables and 1,890 rows compared across every
mapped field and duplicate. The three obsolete source-only tables were empty.
All four PostgreSQL backend migration logs stayed native, including their exact
own-generation SQL text and records. The stock 91-table catalog and all 63 serial
sequence floors passed. Legacy Go UTC strings were normalized only in a new working
SQLite copy and compared using PostgreSQL's native timestamp/CHAR representations;
the original source was never edited and no records were discarded.

The off-NAS encrypted cold archive independently recovered every file and its
POSIX metadata, plus a valid standalone 94-table SQLite source. The actual converted
PostgreSQL dump was encrypted on two hosts and restored to a different physical
PostgreSQL instance; all 91 tables, every field/duplicate, catalog, native migration
records and sequence checks matched before authoritative live startup.

Cold files, current PostgreSQL custom dump and sensitive audit archives are
retained AES256 encrypted on VM300 and this computer. Keys stay separately outside
Git. Computer ciphertexts are under
`~/.local/share/homelab-recovery/grafana-csi-pg-cutover-20261016/`; its key is
`~/.config/homelab-recovery-keys/grafana-csi-pg-cutover-20261016.key`.
VM300's operation is
`/var/lib/homelab-maintenance/operations/grafana-csi-pg-cutover-20261016/`, with
ciphertexts in `recovery/` and its separate key in `keys/`. Encryption/decryption
round trips and transferred ciphertext hashes were verified.

The unchanged scheduled full PostgreSQL backup template completed as a manual
acceptance Job. `pg_dumpall_2026-10-16_102100.sql.gz` was read to gzip EOF with the
Grafana role/database and stock completion footer verified. Its SHA256 is
`a88f0614c4d6274a831eb24099a51554f520395e01259a5fb1efdda884d9102a`.
The backup schedule stayed unchanged.

## Live application and storage acceptance

All 35 dashboards, four datasource identities/configurations, users and organization
roles, configured settings and alert definitions were preserved. Previously healthy
datasources stayed healthy. All original monitoring Secret UIDs, types and decoded
bytes match at closeout. Admin/OIDC credentials and Prometheus/Alertmanager
specifications and readiness stayed unchanged. The renderer token correction is
documented below.
The existing admin/OIDC identities and exact Grafana image stayed in place; the
original renderer credential was restored and no database rekeying occurred. Real browser sign-out followed by Authentik/OIDC return
passed. Live metrics, browser dashboard image export and an actual server-rendered
CPU gauge PNG were visually checked.

The 2GiB ext4 RWOP/Retain volume is `monitoring/grafana-data-block`, backed by
`homelab//k3s-block/9999/vm-9999-grafana.raw`. Physical raw-image generation,
PV/PVC binding, WWN and filesystem UUID were verified. Clean Pod recreation,
movement from worker02 to worker01 and restoration of ordinary worker scheduling
retained the same storage identity. Every new Pod passed the retained-file,
current-enrollment and native SQL guards; its main container and both continuously
running provisioning sidecars were Ready without restarts. Ordered native init
sidecars synchronized provisioning files before Grafana startup, preserving the
existing discovery service account and RBAC.

After the activation merge, all four scoped ArgoCD applications
(`kube-prometheus-stack`, `base-configs`, `filebrowser` and `nfs-provisioner`)
were Healthy/Synced, with successful full current-source operations resolved to
`9b6dce35e646c90814f35b2c1b667e92d068008b`. The owned sync hold was removed.
After the renderer correction below, a continuous six-minute native Deployment
and Pod watch passed with 12 events. Complete original API/settings, Secret,
monitoring and physical-storage acceptance passed again afterward and after
temporary API-resource cleanup.

The original NFS claim, PV and NAS directory remain retained and admission-held.
Do not reopen stale SQLite after authoritative PostgreSQL startup. Ordinary rebuilds
reuse the retained CSI disk and enrolled shared database through the existing
verified-retirement workflow, with no Velero checkpoint or manually created Grafana
database. See the [recovery runbook](../../runbooks/grafana-storage.md).

## Execution closeout

The original conservative clock started `2026-10-16T08:50:17.068118+00:00`; its
90-minute pre-target and three-hour total limits were not reset. Only Grafana,
Filebrowser and the NFS provisioner were stopped; Filebrowser/provisioner returned
Ready after lifecycle acceptance. No host/VM sizing change or disposable VM was
needed. Qualification and additional diagnostics used isolated local Docker fixtures.
Infrastructure and admin/OIDC/renderer Kubernetes Secret values never entered them;
only approved application data copies and dummy fixture credentials were used.

The immediate admission probe stopped before writer shutdown because it did not
yet observe the new policy denial. Fresh read-only reconciliation verified the same
policy enforcing and the original writers unchanged, then a one-use continuation
completed only their unexecuted shutdown/retirement. Allocation, population, schema
initialization and application import each ran once.

A full settings fingerprint initially differed before the frontend was read.
Faithful startup of the actual cold SQLite/files/plugins with the same image,
public configuration and visible CPUs reproduced every target setting. A normal
`GET /api/frontend/settings` then reproduced six lazy default entries: analytics,
caching, recorded queries and reporting flags, plus the cache TTL. After frontend
use, the original complete source settings fingerprint matched exactly. All original
strict API/Secret/monitoring/physical checks passed; no configuration was changed to
force a match. This was a one-time acceptance ordering issue, not a rebuild step.

The first release-watch attempt stopped during reconciliation; a subsequent
complete watch exposed a real renderer-token change in the final Secret check.
The temporary queued-operation replacement had omitted the application's three
existing sync options, including `RespectIgnoreDifferences=true`, allowing a
Helm-generated token to overwrite the Secret. The original token was recovered
and verified entirely inside the native master from the unchanged renderer Pod,
then restored with Secret UID/resource-version preconditions. No token value left
the master. A full current-source sync carrying all three declared options
succeeded and preserved the original token. The final six-minute watch and all
original strict acceptance checks then passed. Admin/OIDC credentials were
unchanged; the renderer credential was temporarily changed and restored before
closeout.

Native cleanup completed at 14:15 Israel time, within the original three-hour
limit. Only owned helper isolation, the manual backup Job, cold-file spool,
plaintext runner working files, sensitive guest receipt namespaces and isolated
local Docker fixtures were removed. Sensitive native audit outputs were encrypted
on both hosts before their bulk plaintext receipt fields were redacted. The
maintenance owner was released last and its private nonce copy removed.

The original NFS source, retained target disk, enrolled database, encrypted cold
and SQL recovery copies, audit ciphertexts and separate keys remain protected.
The remaining private local execution directory is retained only until this
completion report is merged with all hosted checks passing. The reviewed finalizer
then encrypts the final local audit, verifies its recovery round trip, writes a
durable completion receipt and removes that exact private plaintext directory.
No unrelated containers, volumes, repositories or files are included.
