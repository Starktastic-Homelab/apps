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
