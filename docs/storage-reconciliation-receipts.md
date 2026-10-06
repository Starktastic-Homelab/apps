# Historical native reconciliation receipts

This document records the retired iSCSI adapter. Its producer and dispatcher are removed;
the commands below describe historical behavior and must not be used for current storage.
Use [the current Jellyfin runbook](runbooks/jellyfin-storage.md). Existing receipts and
installed immutable runtime evidence remain archived.

This increment adds source support for an operator-published reconciliation receipt. It has not been installed or
published on VM300. Original journals are preserved.

`/etc/homelab-maintenance/jellyfin-reconciliation.json` records schema 1, the fixed service and
historical-native-reconciliation scope, runner instance, timezone-aware observation timestamp, SHA-256 hashes of the
exact record/onboarding/snapshot input bytes, and verified onboarding/snapshot outcomes. It contains no credentials or
raw NAS objects.

The local inspector accepts only an unaliased root-owned regular file with mode 0640, reached without symlinks. It
requires exact field/schema/result agreement, matching runner identity and all three input hashes, and a nonfuture aware
timestamp. Every containing directory must be root-owned and not writable by group/other; the shared operations parent
is therefore not used to store the receipt. Missing receipts retain the existing journal `unknown` diagnostics. Invalid
or unsafe receipts fail; mismatches and removed inputs remain inconclusive. Observed files remain covered by the
inspector's snapshot-stability check.

A passing journal check means historical native reconciliation matches the current local evidence bytes. It does not
mean current NAS state was checked by that request. The report includes evidence age; age alone does not invalidate a
historical observation. `live_verified` and `release_authorized` remain false. Live identity, filesystem/probe/playback,
backup readiness and writer fencing are independent gates.

## Explicit publication

`scripts/storage/reconciliation.py` is an administrative entry point outside the supervised status/preflight request
dispatcher. It requires root, the existing original maintenance owner/nonce on private stdin, an exact expected stage,
and private NAS credential/CA/leaf-pin paths. The state-root argument must match the installed manifest, and the managed
runner marker must match that manifest’s runner identity. A copied state directory cannot substitute another execution
guard. It takes the existing execution guard before NAS observation and publication. Never put owner/nonce/password
values in argv or Git.

Invoke only from a separately approved, verified pinned runtime. The producer checks the active root-owned installation
reference and source/interpreter manifest, then discovers its verified Ansible helper and WebSocket wheel directly. No
source download, package installation or mutation adoption is hidden in this command:

```text
<verified-python> -B -E -s <release>/apps/scripts/storage/reconciliation.py \
  --state-root /var/lib/homelab-maintenance \
  --credentials <private-NAS-file> --ca <verified-CA-file> \
  --leaf-pin <verified-leaf-pin-file> --stage <original-owned-stage>
```

The producer does not depend on PYTHONPATH or ambient site packages for its transport/helper imports. The command
accepts only owner/nonce JSON on stdin; it does not accept a supplied `passed=true` report. Its producer reads
no-follow, bounded snapshots, lets the existing validators consume private copies of those exact journals, checks
reconstructed native allocation fields against the saved record (allowing only its additional filesystem UUID), and
rejects input drift. Only allowlisted NAS query/config methods can reach the transport; existing TLS chain and
independent leaf pin checks protect authentication.

Publication creates a root-owned 0640 receipt with the diagnostic directory's group, flushes it, then links it into the
fixed filename without overwriting any receipt. The entire configuration-directory ancestor chain must be root-owned and
not writable by group/other. Publication rechecks directory identity before reporting success. Original journals stay in
their existing shared operations layout. Existing receipts are refused; refresh/archive is a separate operator-reviewed
action. Publication failure is not success and must be inspected before continuing. No journal edits, namespace changes,
mount operations, service restarts, or writer releases occur.

Source delivery requires Apps regression/CI checks. Root filesystem publication and VM300 rollout acceptance remain
pending separate runtime qualification and execution approval. Tests use synthetic state; no workstation Ansible,
privileged containers or local systemd qualification is permitted.
