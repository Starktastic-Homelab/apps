# pgAdmin production migration completed

pgAdmin now uses shared PostgreSQL for its configuration database and retained
Proxmox CSI for private files. Enrollment [PR #1371](https://github.com/Starktastic-Homelab/apps/pull/1371)
and activation [PR #1372](https://github.com/Starktastic-Homelab/apps/pull/1372) are merged.
Activation merge is `c74098b558a5a38e4383e8bf4aa420b15897b67a`; all five hosted checks passed on exact
head `f563b25d9d6e4e211a7bd228c858d8170d50b126` before merging.

## Preservation and recovery

The production cold source contained 22 native tables and 475 rows. Data-only
conversion compared every field and duplicate, preserving the internal user hash,
all three application keys, encrypted saved server password, macros, preferences
and settings. The native catalog and both own-generation migration-marker tables
were unchanged; all ten serial sequence floors passed. JSON comparison preserves
original number tokens rather than rounding through binary floating point.

The original cold archive independently recovered every file and POSIX metadata
from the computer's ciphertext and passed standalone SQLite integrity and foreign
key checks. The converted current PostgreSQL dump was encrypted on both hosts,
then independently restored to a different physical PostgreSQL instance. All 22
tables, every field and duplicate, native catalog/migration records and ten exact
serial states matched before authoritative live startup.

Cold files, current SQL dump and sensitive audit archives remain AES256 encrypted
on VM300 and this computer, with keys stored separately outside Git. See the
[recovery runbook](../../runbooks/pgadmin-storage.md) for protected locations.
The unchanged full PostgreSQL backup completed as a manual acceptance Job.
`pg_dumpall_2026-10-16_134925.sql.gz` was read to gzip EOF; the pgAdmin role/database
and stock completion footer passed. Its SHA256 is
`7f78ca33c8c8b3cc73234a1ebc845126e3b083732da2d5e6a785da8826f9272b`.
Scheduled SQL backups cover the database, not pgAdmin's private files.

## Live application and storage acceptance

The exact stock pgAdmin 9.18 image, chart 1.70.4 and existing internal/webserver
authentication settings remain in place. Native internal form login with the
original administrator Secret and a saved-server connection using the existing
encrypted password passed after startup, recreation, worker movement and final
cleanup. The administrator Secret's UID, type and decoded bytes stayed unchanged.
No login password, application-key rotation or application patch was needed.
Browser OIDC acceptance was not part of this pgAdmin operation; authentication
configuration was preserved and actual internal authentication was tested.

The 1GiB ext4 RWOP/Retain volume is `databases/pgadmin-data-block`, backed by
`homelab//k3s-block/9999/vm-9999-pgadmin.raw`. Raw-image generation, binding,
attachment and filesystem identity were checked. Clean Pod recreation, movement
from worker02 to worker01 and return to ordinary worker scheduling retained the
same filesystem. All three init guards passed and the main container remained
Ready without restarts during the final continuous six-minute Deployment/Pod watch.
The dedicated completion service account avoids granting database-enrollment
read permissions to the namespace's default account.

All four scoped ArgoCD apps (`pgadmin`, `base-configs`, `filebrowser` and
`nfs-provisioner`) finished Healthy/Synced with successful full current-source
operations resolved to the activation merge. The owned sync hold was removed.
Desired/live equality and post-watch credential/physical checks passed.
The continuous watch observed 13 events without a regression.

The original NFS claim/PV and NAS directory remain retained and admission-held.
After PostgreSQL became authoritative, stale SQLite could no longer be resumed.
Normal rebuilds reuse the retained disk and enrolled shared database through the
existing verified-retirement workflow; conversion is a one-time migration.

## Execution closeout and corrections

The original clock began `2026-10-16T13:18:02.206654+00:00`. Its 90-minute pre-target
and three-hour total limits were unchanged; native cleanup completed at
`2026-10-16T14:07:53.933743+00:00`. pgAdmin, Filebrowser and the NFS provisioner were the only stopped
writers; all returned before final Git reconciliation. No VM sizing or storage
controller change was needed. Approved application copies used isolated local
Docker fixtures; infrastructure/runtime/admin Secret credentials stayed native.

The first stopped-source checker required UID 5050 on the export root, but the
actual source root was 0:0/0777 with application-owned children. The corrected
check preserves that exact source metadata and gives the new read-only identity
marker the existing storage directory's 5050 owner. A first permission probe
inherited a supplementary root group; the corrected no-supplementary-groups probe
reproduced the original marker-read failure and verified the fix. The known failed
read-only guest terminal was preserved; a specific continuation completed only
fresh retirement/fingerprinting. Shutdown, allocation and import were not replayed.

The initial live checker expected the driver name `postgresql`, while the stock
image reports `postgresql+psycopg`. Actual login and the encrypted saved connection
had already succeeded. Regression tests now accept the exact stock driver and
reject SQLite. A specific continuation completed only the remaining credential,
recreation and movement checks. The original failed terminal remains in the
protected audit. Neither schema initialization nor data conversion was repeated.
The cleanup gate accepts only the two exact known failed guest identities; unknown
or other failed generations remain blocked. The original reviewed package and
these separately tested factual amendments are preserved in encrypted audits.

Only owned helper isolation, the manual backup Job, NAS cold spool, private runner
working files, sensitive guest receipt namespaces and exact labelled local Docker
fixtures were removed. Native audit ciphertexts were verified on both hosts before
bulk plaintext receipt outputs were redacted. The maintenance owner was released
last, and its private nonce copy removed. Original NFS, retained CSI, PostgreSQL
and recovery media are preserved.

The private local execution directory remains only until this report merges with
all exact-head hosted checks passing. The reviewed finalizer then encrypts the final
local audit, verifies its recovery round trip, writes a durable completion receipt
and removes that exact directory. No unrelated resources are included.
