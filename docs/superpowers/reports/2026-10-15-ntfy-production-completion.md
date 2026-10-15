# ntfy production migration completed

ntfy now uses shared PostgreSQL for its database stores and retained Proxmox CSI
for attachments. Enrollment [PR #1362](https://github.com/Starktastic-Homelab/apps/pull/1362)
and activation [PR #1363](https://github.com/Starktastic-Homelab/apps/pull/1363) are
merged. Activation merge is `663be3f90fc4b0a5002d8032941caa0c93efb827`; all five hosted checks passed on
its exact head before merging. Git desired state and live state reconciled, and all
four scoped applications completed full current-source operations Healthy/Synced.

## Preservation and recovery

The latest cold sources contained 6 users, 4 ACLs, 3 access tokens, 20 messages and
message statistics. All 11 application tables compared equal across every mapped
field, including password hashes, preferences and message identities. The unchanged
upstream importer ran once; stock ntfy upgraded the schema to user/message/webpush
9/15/1. All 112 stock constraints and 35 indexes were preserved. The newer omitted
authentication stores and webpush subscriptions were empty; nothing was discarded.

A separate physical PostgreSQL instance restored the actual cutover dump. All 11
tables compared exactly. All 3 existing tokens authenticated. In the isolated lab,
all 4 non-admin ACLs passed their read/write allow and deny checks, including
unmatched-topic denial. No real subscribers received test notifications. No
plaintext user passwords were supplied, so password preservation is established
by exact hash comparison; fresh password-based sign-in was not directly exercised.

Cold SQLite, PostgreSQL custom dump and sensitive audit recovery archives remain
AES256 encrypted on VM300 and this computer. The key is retained separately outside
Git. Computer archives are under
`~/.local/share/homelab-recovery/ntfy-csi-pg-cutover-20261015/`; the separate key is
under `~/.local/share/homelab-recovery-keys/`. VM300's operation is
`/var/lib/homelab-maintenance/operations/ntfy-csi-pg-cutover-20261015/`, with encrypted
archives in `recovery/` and the separate key in `keys/`. Encryption/decryption
round trips and transferred ciphertext hashes were verified.

The unchanged scheduled full PostgreSQL backup template completed as a manual
acceptance Job. Backup `pg_dumpall_2026-10-15_151702.sql.gz` was read to gzip EOF, with ntfy
role/database coverage and the stock completion footer verified. Its SHA256 is
`e4a84f3e93dbac908d71f1bb5a0fe5661d0893971f154d005d39e385191fe04a`. The schedule was unchanged.

## Live storage and GitOps acceptance

The 8GiB ext4 RWOP/Retain volume is `operations/ntfy-data-block`, backed by
`homelab//k3s-block/9999/vm-9999-ntfy.raw`. Actual binding, raw-image generation,
WWN and filesystem UUID were verified. Clean Pod recreation and movement from
worker01 to worker02 retained the same PV/PVC/filesystem identity. The old runtime,
mount and required disk attachment were retired; the original worker's scheduling
was restored. All 3 tokens, stock health, private publish/poll and anonymous denial
passed after each lifecycle test. VAPID identity and the pinned ntfy image stayed
unchanged; no SQLite fallback files were created.

The owned hold was released only after complete current-main desired/live equality.
A native Deployment watch then ran continuously for 6 minutes, accepting no spec
regression, restart or binding loss. ntfy, base-configs, Filebrowser and the NFS
provisioner finished Healthy/Synced with full operations resolved to the activation
merge. Only owned temporary isolation and the manual acceptance Job were removed.

The original NFS claims, PVs and NAS directories remain retained and admission-held.
Do not reopen stale SQLite after authoritative PostgreSQL startup. Ordinary rebuilds
reuse the retained CSI disk and enrolled shared database through the established
verified-retirement workflow; no Velero checkpoint is required. See the
[recovery runbook](../../runbooks/ntfy-storage.md).

## Implementation choices

Qualification used a closed local Docker lab instead of VM980; no ARC or VM sizing
change was needed. Stock initial SQL plus removal of its verified sole blank
anonymous seed preserved the original account identity. The runtime explicitly
removes the three SQLite environment settings and avoids an inherited fsGroup
rewrite of attachment ownership. The exact public importer binary was staged
before the outage. Production physical recovery and lifecycle acceptance remained
mandatory even after successful local qualification.

## Execution closeout

The original conservative clock began `2026-10-15T14:40:54.589690+00:00`; its pre-target and
finish limits were not reset. First accepted live startup evidence was recorded by
`2026-10-15T15:13:07+00:00`; native cleanup completed by
`2026-10-15T15:28:13+00:00`. These are evidence-recording times, not a measured
continuous end-user availability interval.

Three pre-import wrapper attempts stopped before submitting the importer: admission
cache propagation, a read-only dry-run conflict, and CSI-added topology labels.
Read-only reconciliation established exact state before each bounded continuation.
Only the verified CSI region/zone labels and exact read-only conflicts were allowed;
all ownership, identity, readiness, full-spec and original-clock gates remained.
Allocation, population, initial DDL and the actual import each ran once.
A final local cleanup attempt stopped on copied identity-file permissions before
any container deletion. Its continuation corrected the private copy and resumed
only exact local cleanup and owner release; production cleanup was not replayed.

Temporary local lab containers, their unshared volumes and internal network were
removed by exact recorded identities. Runner plaintext and the maintenance owner
were removed. Protected local plaintext working copies were deleted after preparing this
sanitized closeout; encrypted recovery archives and separate keys stay
outside every Git repository. Unrelated containers, VMs and credentials are outside
this cleanup.
