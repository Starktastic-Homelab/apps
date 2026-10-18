# Redis native recovery qualification

Preparation only. No production Redis/configuration/workload/storage was changed.
Task 1 of the [plan](../plans/2026-10-18-redis-immich-retained-csi.md) is locally qualified; the remaining package, final independent review and separate execution approval are still required.

## Evidence

Six state tests and four exact-image native tests passed on 18 October 2026.
The Redis binary is 8.10.2 at the design’s exact deployed digest. The isolated
Python helper uses the pinned Paperless image’s redis-py 5.2.1, Celery 5.6.3
and Kombu 5.6.2. The pinned Immich image supplies BullMQ 5.81.3. Application
entrypoints, real application records, credentials and production networks were
not used. Each fixture owns labeled Docker volumes/containers and verifies their
removal; the tests retain no application data.

The synthetic source intentionally retained historical AOF files with AOF disabled
while current memory contained newer data. Historical restore failed comparison.
Current-memory native RDB export/check/independent restore passed full comparison
before AOF was enabled on the still-running source. Native rewrite, clean cold
copy, fresh start, abrupt termination and recreation preserved the checkpoint.

Checks cover binary keys/payloads, duplicate SCAN, every supported native type,
ordered lists, streams with group offsets/pending ownership, database 4,
absolute expirations, and native Celery/BullMQ pending/in-flight recovery.
Unknown module types and hash-field expiration refuse qualification. Waiting to
compare cannot excuse a key already missing before its native expiry.

The read-only guard and its metadata/byte hashes accept a valid empty dataset,
zero-byte increments, and stock manifest history. They refuse empty/wrong media,
missing manifests/base files, path escapes, unreadable base files, symlinks and
corrupt base data. Final-increment corruption is also tested through the actual
server: invalid format aborts startup instead of creating an empty Redis.

## Qualified stock crash recovery

The exact engine discards an incomplete final AOF command during default startup;
all complete commands in the fixture survived. The guard leaves retained data
read-only and never repairs it. It validates marker/manifest/paths, the base and
earlier increments, then lets the stock loader decide an invalid final increment.
This preserves the design’s qualified native recovery and accepted `everysec`
policy; it does not waive the complete migration checkpoint.

Redis documents both the usual one-second disaster-loss window and automatic
incomplete-tail recovery, while other invalid AOF formats abort startup:
[Redis persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/).
This is not a zero-loss power-failure guarantee. No `--fix` command or automatic
CONFIG SET loop is part of this package.

The native AOF checker opens files writable even without repair mode. Checks run
on private scratch copies; retained media stays read-only. Startup therefore needs
scratch disk and copy I/O up to the retained AOF footprint. The exact image emits
optional native `startoffset`/`endoffset` manifest fields; these are accepted.

## Reproduce

```bash
python3 scripts/test-redis-immich-state.py
python3 scripts/test-redis-immich-native.py --app redis
```

The native command needs Docker and the exact pinned images, uses disconnected
synthetic containers only, and cleans exact owned resources even on failure.
A real workload rollout, filesystem move between Kubernetes workers and full
Terraform destroy/apply have not been performed by this preparation.
