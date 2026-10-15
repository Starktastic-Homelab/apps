# ntfy PostgreSQL and retained CSI migration

The user authorized autonomous ntfy assessment, qualification, implementation,
production migration and final PR reconciliation on October15. This follows the
accepted live-storage workflow. Pause for actual preservation loss, an unresolved
identity/ownership result, or a change to the selected architecture.

## Outcome and scope

Preserve existing users/password hashes, roles, topic ACLs, access tokens,
preferences, quota/statistics, message bodies/IDs/timestamps, attachments, web-push
subscriptions and VAPID identity. Keep the exact pinned v2.29.0 image and external
URL. Reuse shared PostgreSQL18.6 and idempotent enrollment. Ordinary rebuilds
remain Terraform/Ansible/Git-driven with retained storage and verified retirement.
Do not change notification routes, create a new database deployment, upgrade
ntfy, rotate existing credentials or patch the upstream importer.

Fresh assessment: one Ready ntfy Pod; two NFS claims at
`/mnt/apps/pv/operations/ntfy-config` and `ntfy-cache`; databases total532480bytes;
no attachments; original files root-owned. Both stores currently have no WAL/SHM
files. VM300 has only~369MiB available. Use a local disposable Docker lab with an
internal network, exact ntfy/PostgreSQL images, fixture SQL credentials and no
published ports. Production administrator credentials never enter the lab.

## Selected data path and acceptance

Use the unmodified importer from tagv2.29.0, commit
`f18d1137c63a26e85b91ce639e7bc72bb9a82736`. Its initial PG stores are user6,
message14 and webpush1; stock application upgrades user/message schemas to9/15.
Never rewrite source or target schema markers to bypass compatibility. The tool
omits newer auth tables and samples message verification; qualification must
independently compare every typed field and all tables, including omitted tables,
password hashes, ACL booleans, nullability, messages' statistics and webpush state.
Count-only success, replacement of malformed UTF8/NUL, skipped files and dropped
rows are unacceptable. Recheck the exact latest cold source at production cutover.
If official conversion fails preservation, stop for the architecture decision.

All database state moves to PostgreSQL; remaining files are attachment cache.
Use one static8GiB ext4/RWOP/Retain image,
`k3s-block:9999/vm-9999-ntfy.raw`, PV/PVC `operations/ntfy-data-block`, CSI handle
`homelab//k3s-block/9999/vm-9999-ntfy.raw`. Mount at `/var/cache/ntfy`; preserve
attachments and require `.homelab-ntfy-data` with `homelab/ntfy/data/v1`.
Disable old config/cache dynamic claims and remove SQLite-file environment
options. All other effective configuration and the sealed VAPID secret stay equal.
Retained startup checks reject absent/wrong marker, active SQLite fallback,
unaccepted enrollment, wrong physical PG identity or missing/mismatched schema
before stock ntfy can initialize empty data. Reuse the completion/login gate and
sealed URL generation; keep existing enrollment entries/ciphertexts unchanged.

## Operational workflow

Prepare and test commands before downtime. Acquire a new operation-owned VM300
maintenance owner/executor, capture VM/cluster/resource UIDs and fresh availability.
Require aggregate160GiB quota to cover every existing image's full unallocated
growth, new8GiB,0.5GiB staging and8GiB headroom, plus actual PG resources/connections.
Hold only ntfy/base-configs and the actual ancestor writers found by inventory.
Stop exact writers and prove runtime/mount retirement before cold backup. Briefly
pause Filebrowser/NFS provisioner only where their parent mounts can reach the
sources; resume them after cold recovery. ntfy delivery is unavailable while its
writer is stopped and during deliberate recreation/movement tests.

Retain encrypted cold/config and SQL recovery copies on VM300 and this computer;
keep the per-operation recovery key separately outside Git. Verify cold restore,
full latest-source comparison, fresh physical PG dump restore and attachment
metadata/bytes before authoritative startup. Protect old sources with UID-bound
admission policy. Mark the authoritative-write boundary before first stock start;
never reopen stale SQLite after that boundary without a newest-state recovery
choice. Use an original boot/monotonic clock:90minutes pre-start,180minutes total;
continuations preserve failures and never reset the clock or replay mutations.

Accept stock health/readiness, preserved credentials and ACL allow/deny behavior,
private test-topic publish/poll with no human subscribers, preserved VAPID keys,
attachments, fresh Pod recreation and healthy worker movement with physical identity
and retirement proofs. Never trigger an existing user's real webpush endpoint.
Verify a complete scheduled-backup-template run includes ntfy. Merge only exact-head
CI-green PRs; require merged-main desired/live equality, safe held-queue retirement,
six-minute native no-regression watch and all scoped apps Healthy/Synced. Clean up
only exact owned containers/media/plaintext/helpers, release maintenance ownership,
and preserve old NFS data, target images and encrypted recovery.

## Sources

- [Accepted live workflow](2026-10-10-live-storage-migrations-design.md)
- [Pinned importer](https://github.com/binwiederhier/ntfy/tree/v2.29.0/tools/pgimport)
- [Official database configuration](https://docs.ntfy.sh/config/#database-options)
