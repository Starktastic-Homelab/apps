# Redis and Immich retained storage preparation

This package is inactive. It prepares Redis queue durability on retained CSI,
then a physical move of Immich’s dedicated PostgreSQL17 cluster. The
[approved plan](../../docs/superpowers/plans/2026-10-18-redis-immich-retained-csi.md)
requires a reviewed finite command packet and separate execution approval before
outages, real-data/key transfers, allocation, activation or merges.

Redis uses the current chart28.3.1 and deployed Redis/exporter digests. Immich
keeps its PG17/VectorChord0.4.3/pgvector0.8.1 image and all existing server/ML
settings. Photos/videos and model cache stay on NFS. Shared PG18/enrollment,
Paperless’s own index and Calibre are outside this operation.

## Local qualification

Use Python with PyYAML, Helm, kubeconform and Docker. The engine fixtures use
only pinned images, disconnected containers and exact labeled resources. They
use synthetic records and credentials and verify cleanup on success/failure.
They never run the Paperless or Immich application entrypoint. PG17’s database
wrapper is intentionally exercised. The Redis fixtures match the chart’s module
configuration and the live UID/GID1001:1001.

```bash
python3 scripts/test-redis-immich-state.py
python3 scripts/test-redis-immich-native.py --app redis
python3 scripts/test-redis-immich-native.py --app immich
REDIS_CHART=/tmp/redis-immich-charts/redis \
APP_TEMPLATE_CHART=/tmp/redis-immich-charts/app-template \
REDIS_IMMICH_RENDERS=/tmp/redis-immich-renders \
bash scripts/redis-immich-retained/check.sh
```

Pull Redis28.3.1 and app-template5.3.0 into those chart directories first.
Use a private0700 output directory. Validation compares complete containers,
services/configuration and unaffected Immich controllers against actual layered
baselines, then checks static bindings, guard mounts, schemas and real promtool
alert timing/recovery. A pinned promtool container is used when no local binary
is available. No production notification is sent.

Immich’s upstream schema rejects null `fsGroup`. `check.sh` therefore removes
only the old PG fsGroup, PID-deletion init and its mount from a temporary service
values copy before applying the inactive overlay through globals/common/service
layers. Activation must apply those same deletions to the real service file.
No chart fork or validation bypass is required. The guard uses UID999 without
pre-guard ownership rewriting; the native process keeps its existing identity.

## Recovery contracts

`redis_checkpoint.capture` requires redis-py5.2.1, binary responses and a single
connection. It uses native TIME, absolute key deadlines and two frozen passes.
All records stay private in lossless base64 encoding. Unknown module types and
hash-field expiration refuse qualification. Only expiry already explained by
the actual capture clock can excuse a missing key.

Redis must stay alive while AOF is off until a current-memory RDB is exported,
encrypted and independently restored/compared. Historical disk AOF is never a
substitute. Only then may the reviewed operation enable AOF on that same source,
wait for native persistence and eventually stop it. A failed transition never
justifies restarting into historical data or turning restored AOF off again.

The guard requires the marker `homelab/redis/data/v1\n`, native manifest and
all active regular files. Native integrity checks use private scratch copies;
retained data is read-only. Valid empty datasets/zero-byte increments and unused
manifest history are supported. The qualified stock loader may recover an
incomplete final AOF command after a crash under the accepted everysec policy;
bad increment format aborts startup. There is no guard repair, `--fix`, CONFIG
SET loop or durability-triggered liveness restart. Full migration state must
still match before acceptance. Native exporter/ENOSPC fixtures qualify both AOF
alerts, their recovery, and the existing service labels.

PG17 export uses native psql/pg_dump/pg_dumpall and repeatable-read read-only
transactions with quiescent writers. Private artifacts include records and
password verifiers: keep them outside Git. Complete table rows (including
duplicates, binary/vector values), schema/roles/extensions and sequence floors
must survive. A physical restore preserves the recorded identifier; an independent
logical restore must have a different identifier and the same logical proof.
The guard pins PG17 and production identifier7614955115223928876, rejects corrupt,
empty, wrong, linked or recovery media and leaves PID files untouched. Stock
stale-PID and WAL recovery rely on RWOP plus verified VM-retirement fencing.
External WAL/tablespace links and foreign tables require a reviewed expanded
copy contract; they are not silently skipped.

## Activation and authority

The `production/` directory has no app discovery entry. Its declarations cannot
activate themselves. Static claims use ext4/cache-none, RWOP, Retain, fixed
external owner9999, bidirectional prebinding and Argo prune/delete protection.
Keep both old NFS claims/PVs protected and permanently refuse old app claim/path
reuse. Capacity must be checked fresh against dataset and pool full remaining
image growth,512MiB staging and8GiB spare; the288GiB quota stays unchanged.

The finite private packet must record original owner/nonce/clocks, intents,
known child terminals, exact resource generations and target authority. Unknown
or completed mutations cannot replay. Source rollback requires retired target
writers before authority; after authority preserve the newest target writes.
Real records/keys/lab resources need the later explicit execution scope. Keep
infrastructure credentials out of restore fixtures and Git.

After separate approval, Redis completes acceptance and ownership release before
Immich begins. Real queue work, PostgreSQL/native asset/API checks, clean Pod
recreation, worker movement, normal placement, exact-head CI and current-main
Healthy/Synced state remain distinct production gates. Release only owned Argo
holds while preserving every sync option, then watch for six minutes and release
maintenance ownership last. Engine tests and lint are not a cluster rollout or
a full Terraform destroy/apply rehearsal.
