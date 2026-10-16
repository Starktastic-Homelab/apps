# Exact pgAdmin application-data transfer approval

This is the missing sensitive-transfer authorization within the user's otherwise
autonomous pgAdmin migration. Production is still unchanged; the rejected export
never executed. This approval does not broaden access to infrastructure credentials.

## Payload

- Consistent pgAdmin configuration SQLite snapshots and the stopped-source private
  directory, currently393216regular-file bytes including the previous DB backup.
- Existing internal user's password hash; three application encryption/signing
  keys; encrypted saved PostgreSQL password; server definitions, preferences,
  macros and other application records/files.
- Later converted application SQL dump and sensitive operation/audit evidence,
  retained encrypted with the cold source for recovery.

This data must be treated as credential-bearing even where values are encrypted.
No separate Proxmox, runner, shared PostgreSQL administrator, pgAdmin administrator
or other Kubernetes Secret plaintext may be supplied to a disposable lab.

## Exact destinations and uses

1. Owner-only0700 ignored local working directory:
   `/home/benf/.codex/worktrees/ntfy-postgresql-csi/apps/.superpowers/sdd/2026-10-16-pgadmin-postgresql-csi/`.
   Copies are exclusive0600 files, hashed/read back and never printed or committed.
2. Exact labelled local Docker fixtures on internal network
   `pgadmin-qualification-20261016`, with no published ports or outside egress.
   Mount only scoped app copies; use dummy database/UI credentials. Do not contact
   production using saved credentials. Preserve the original snapshot untouched;
   any fixture-only derivative remains separately identified.
3. VM300 root-only0700 operation directory:
   `/var/lib/homelab-maintenance/operations/pgadmin-csi-pg-cutover-20261016/`.
   Native cold backup/conversion and independent encrypted recovery use private
   subdirectories; no infrastructure login is copied into an app fixture.
4. Durable ciphertexts on VM300 under that operation's `recovery/`, with its
   separate protected `keys/` directory; and on this computer under
   `~/.local/share/homelab-recovery/pgadmin-csi-pg-cutover-20261016/`, with key
   `~/.config/homelab-recovery-keys/pgadmin-csi-pg-cutover-20261016.key`.
   Verify decryption round trips and transferred ciphertext hashes.

## Bounds and cleanup

The first source snapshot uses SQLite read-only mode and an in-memory consistent
backup; it changes no production object or source file. Verify unchanged source
hash, maximum2MiB snapshot, native/received hashes, integrity, foreign keys and
schema52. Subsequent cold copies require the reviewed writer-stop/retirement and
native maintenance ownership gates; this authorization does not bypass them.

Use only verified native encrypted/SSH/Kubernetes transport, never public uploads.
Remove only exact owned temporary fixture resources and plaintext after accepted
migration/recovery and protected audit retention. Keep old source and encrypted
recovery. The final private local working directory is removed after the sanitized
completion report merges, using the established exact-cleanup procedure.
