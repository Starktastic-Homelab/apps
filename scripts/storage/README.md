# Operator storage maintenance

This directory contains explicit operator tools, not an in-cluster provisioner.
Merging the NFS policy or tools executes **no NAS update**. Production execution
requires a separately approved window and the shared runner maintenance lock.

## NFS durability correction

`nfs-sync.json` records the September 21, 2026 read-only preflight identities:
TrueNAS 25.10.7, pool `apps` GUID `9917900421692286909`, dataset `apps/pv`
GUID `14547210392972608779`. Reinspect before execution; a mismatch requires
review, never editing the policy to whatever currently occupies the name.
The transition changes only explicit local `DISABLED` to `STANDARD`. It affects
all NFS-backed application data on this dataset. It does not fix SQLite's NFS
locking constraints or establish the cause of earlier errors.

Create an isolated environment and install `requirements.txt`. Supply an owned
mode-0600 credentials file containing three lines: HTTPS origin, username,
password. The CA file and SHA-256 leaf fingerprint file must come from an
independently trusted management route. The fingerprint is 64 hexadecimal
characters. TLS validates the CA chain and exact leaf before sending credentials;
the NAS IP lacks a matching certificate SAN. Do not trust a certificate first
seen through an unauthenticated network request.

Read-only inspection:

```sh
python scripts/storage/nfs_sync.py inspect \
  --credentials /run/private/nas.credentials \
  --ca /run/private/nas-ca.pem --leaf-pin /run/private/nas-leaf.sha256
```

Before applying, the operator must review fresh consistent backups of **every
critical application** on `apps/pv`, including SQLite DB/WAL state and an actual
PostgreSQL restore. Independently inspect the archives and restore reports. The
tool validates the receipt's coverage/age/shape; it cannot prove that an operator
actually performed the reported restore. Do not use synthetic test receipts.

The private JSON backup receipt contains `dataset_guid`, timezone-aware
`captured_at` (maximum 24 hours old), `coverage_reviewed_by`, an explicit
`critical_applications` list including `postgresql`, and nonempty `archives`.
Each archive records `application`, positive `bytes`, lowercase hex `sha256`,
`consistency` (`cold` or `database-native`), `integrity: passed`, `restore: passed`,
and the private restore report location in `evidence`. A filesystem snapshot
alone is not proof of database consistency. Include all covered critical apps;
application names in the test fixtures are examples, not the coverage inventory.

After approval, and only under the runner maintenance lock:

```sh
python scripts/storage/nfs_sync.py apply-standard \
  --credentials /run/private/nas.credentials \
  --ca /run/private/nas-ca.pem --leaf-pin /run/private/nas-leaf.sha256 \
  --backup-receipt /maintenance/operations/nfs-backup-coverage.json \
  --journal /maintenance/operations/nfs-standard.jsonl
```

The journal is exclusively created and fsynced before the single update. Keep
it on the durable runner disk, not `/tmp`. An existing intent always blocks
another apply, even when a previous update succeeded but its reply was lost.
After an error, inspect and then explicitly reconcile the **same journal**:

```sh
python scripts/storage/nfs_sync.py reconcile \
  --credentials /run/private/nas.credentials \
  --ca /run/private/nas-ca.pem --leaf-pin /run/private/nas-leaf.sha256 \
  --journal /maintenance/operations/nfs-standard.jsonl
```

Reconcile never updates the NAS. If readback is not STANDARD, the operation stays
unverified for operator investigation. Preserve the journal; do not delete it
and rerun blindly. No automatic reversal to DISABLED exists.

Capture pre/post app readiness, error rates, NAS storage latency and pool health
during the agreed observation window. On regression, retain STANDARD and
investigate workload/storage latency. A durability-reducing reversal would
require a separate explicit decision. A successful unit test is not a live
NAS change or performance qualification.

## Local checks

```sh
python -m unittest discover -s scripts/storage/tests -v
python3 scripts/test-pg-backup.py
```

The NFS tool is prepared first; the shared-lock workflow and later storage
operations are companion changes. Do not deploy the tool before that runner
coordination has been reviewed and qualified.

The standalone NFS apply entry point requires the same external ownership as the
workflow, both before inspection and immediately before updating TrueNAS. Supply
the immutable Ansible helper on `PYTHONPATH`, the verified runner marker, and the
original `MAINTENANCE_OWNER` / `MAINTENANCE_NONCE`; never log the nonce. Tests also
need that pinned helper on `PYTHONPATH` and use a temporary root to exercise real
missing-owner, mismatched-owner/nonce/marker and ownership-loss cases.

## Retained target lifecycle

`storage/services/jellyfin.json` is an **allocation intent**, not a deployable
volume identity. The one-time onboarding tool creates the reviewed 64 GiB ZVOL,
dedicated export and restrictions; it preserves the existing global IQN basename
and verifies portal 1 before reuse. It returns native identifiers, but does not
format a filesystem or authorize a workload. Keep the private CHAP file and
allocation journal on the runner. No normal recovery code creates or repairs
storage. An interrupted create requires explicit inspection/reconciliation;
missing partial objects are not automatically recreated.

`verify_existing` checks native identity read-only. `probe_filesystem` uses a
reviewed SSH worker route under the external lock, refuses existing CSI sessions
before node updates, checks device identity, and mounts only clean matching ext4
as `ro,noload`. SQLite integrity runs on private DB/WAL copies. It never invokes
mkfs or fsck. Failed unmount intentionally prevents logout; leave the operation
held for inspection. Plugin readability still requires the independent restored
Jellyfin startup, not merely a SQLite check.

`snapshot_policy` is a separate explicit operation for `apps/iscsi`, recursive,
one-week retention. It reads the actual existing `apps/pv` schedule before
recording its intent, preserves unrelated tasks and refuses conflicting rules.
An ambiguous create reply has a read-only reconciliation path. The existing
`apps/pv` task does not protect the sibling iSCSI dataset.

Target restore is also a separate operation: hold writers, verify/fence the
previous owner, clone the selected snapshot to a **new** reviewed dataset/export,
verify that clone's returned native identities and filesystem state, and perform
an independent restore test before authorizing it. Never overwrite or roll back
the active production ZVOL automatically. Keep original target and source until
an explicit cleanup decision.

The initiator probe configures CHAP through SSH stdin and a private, fsynced
Debian node record under `/var/lib/iscsi/nodes`; credentials never enter command
arguments. It refuses a pre-existing target record before creation. A completed
probe deletes only its own node record after successful unmount and logout.
A configuration failure or uncertain login retains that record: reconcile the
actual session/device state under the original maintenance owner before retrying.

The CSI Secret uses the driver's `node-db.` prefix: seal
`node-db.node.session.auth.authmethod=CHAP`,
`node-db.node.session.auth.username`, and `node-db.node.session.auth.password`.
Bare `node.session.auth.*` keys are ignored by the pinned node-manual driver's
Linux NodeStageVolume path. The native probe's private credential file has a
different format; its success alone does not verify the CSI Secret mapping.
