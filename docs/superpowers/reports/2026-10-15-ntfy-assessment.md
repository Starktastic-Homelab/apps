# ntfy conversion qualification

Status: production migration completed after real-data qualification and the user's
explicit approval of sensitive copies. See the [production completion report](2026-10-15-ntfy-production-completion.md)
for current runtime, recovery, lifecycle and GitOps acceptance. The assessment below
records the earlier qualification state.

## Fresh production assessment

On October15, ntfyv2.29.0 was Healthy/Synced with one Ready Pod. Its unchanged
image is `binwiederhier/ntfy@sha256:4c599cf0818965782f93f652bd843e92714992e84d6b88ad17713dc0951cda1f`.
`ntfy-config` and `ntfy-cache` use NAS paths `/mnt/apps/pv/operations/ntfy-config`
and `/mnt/apps/pv/operations/ntfy-cache`. The three database files total532480bytes;
attachments were empty. This is an active-file inventory, not a cold backup.
The current160GiB aggregate quota has enough measured room for all remaining raw
image growth, proposed8GiB target,0.5GiB staging and8GiB headroom. Recheck before allocation.

## Synthetic qualification only

A local internal-network Docker lab used the exact ntfy image and shared-server
PostgreSQL18.6 image, fixture credentials, no published ports and no real data.
The unmodified importer was built from tagv2.29.0, commit
`f18d1137c63a26e85b91ce639e7bc72bb9a82736`; binary SHA256
`6bc4fb9a3012a4d8b7e005701db9eeb585667744a4a7b9ec84d25b506b2d2795`.

The first `--create-schema` run returned success but full user-field comparison
found the target's newly seeded anonymous-account creation timestamp differed from
the source. Count checks did not catch it. The accepted synthetic preparation
executes the exact upstream initial schema SQL in an empty database, verifies its
sole blank anonymous seed, removes only that seed, then runs the unchanged
importer without `--create-schema`. Stock ntfy upgrades user/message/webpush stores
from6/14/1 to9/15/1. No schema marker is rewritten and no upstream code is patched.

After that preparation, all11 application tables compared equal across every
mapped field:3users,1topic ACL,1access token,1Unicode message, message statistics,
and empty tier/phone/email/magic-link/webpush tables. Password hashes, nulls, booleans,
prefs and identity fields were compared privately. Source database hashes remained
unchanged. SQLite/PG internal message surrogate IDs differ by backend; externally
used message/sequence IDs and all other message fields are compared exactly.

## Approved real-data qualification

Consistent read-only in-memory SQLite backups were transferred to an owner-only,
Git-ignored local directory after explicit approval. The copies contain6users,
4ACLs,3tokens,24messages and message statistics. Omitted newer email/magic-link
stores and webpush subscriptions are empty; text contains no malformedUTF8/NUL.
All11 application tables and every mapped field compare equal after unchanged
upstream import and stock schema upgrades. Source hashes remain unchanged.

An independent custom-dump restore into a different physical PostgreSQL instance
again preserved all11 tables. All3existing tokens authenticated; an isolated unique
topic accepted publish/poll and denied anonymous access. Restart retained the test
message. The lab has no external egress or published ports, uses fixture SQL/VAPID
credentials, and did not deliver to real notification subscribers.

Native retained SQL tests reject wrong physical identity/database, wrong versions,
missing columns, extra tables, missing anonymous identity and missing administrator.
An isolated restored-state test exercises all4preserved non-admin ACLs:2read-only
and2write-only rules, plus unmatched-topic read/write denial. It detects an
intentionally incorrect read-permission expectation. Missing test tokens are minted
only in the isolated lab; production users, passwords and ACLs are unchanged.

The startup guard accepts Kubernetes Secret atomic-writer links only when their
resolved password stays inside the mounted Secret directory. Retained identity
markers still reject symlinks. Host-user readability of all3standalone cold copies
is required before allocation.

The layered Helm regression catches both inherited provisioning fields on the old
cache entry and null SQLite variables that Helm still renders. The accepted overlay
disables both old claims, uses a separately named retained volume, and explicitly
replaces the environment list while preserving all other effective settings.

Qualification required separate production gates for latest cold-source checks,
independent recovery, actual CSI identity/recreation/movement, backup and live
reconciliation. Those gates subsequently passed as recorded in the completion
report. No populated omitted authentication store may be silently dropped.
No VM980 or ARC change was needed.

Sources: [pinned upstream importer](https://github.com/binwiederhier/ntfy/tree/v2.29.0/tools/pgimport),
[stock store migrations](https://github.com/binwiederhier/ntfy/tree/v2.29.0/user),
[official configuration](https://docs.ntfy.sh/config/#database-options).
