# ntfy assessment and synthetic qualification

Status: production remains unchanged. Real-data qualification is pending explicit
approval for transferring sensitive ntfy database copies to the protected local lab.
The autonomous migration request remains active; no outage clock has started.

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

This does not qualify real ntfy data, populated omitted newer auth tables, actual
webpush subscriptions, cold recovery, productionCSI attachment or live notification
acceptance. The importer omits user_email/user_magic_link and sanitizes malformed
message text; real/cold checks must reject lost rows, invalid text or embeddedNUL.
The local fixture containers are stopped; their exact owned IDs and private proof
files are retained for continuation. No VM980, ARC adjustment, enrollment, CSI
allocation, production backup, hold or writer shutdown occurred.

## Next gate

Automatic approval review rejected copying databases containing existing credentials,
tokens, messages and webpush state to this computer without explicit approval for
the payload and destination. The pending request scopes copies to the owner-only,
Git-ignored ntfy rehearsal directory, read-only source connections, an isolated lab
and later plaintext cleanup. No production database copies have been transferred.

Sources: [pinned upstream importer](https://github.com/binwiederhier/ntfy/tree/v2.29.0/tools/pgimport),
[stock store migrations](https://github.com/binwiederhier/ntfy/tree/v2.29.0/user),
[official configuration](https://docs.ntfy.sh/config/#database-options).
