# Redis and Immich command-package preparation

Production remains unchanged. Target values/bindings/guards are inactive under
`scripts/redis-immich-retained/production/`; no production owner, snapshot, helper,
backup transfer, credential generation, ACL/AOF change, allocation, activation or
merge has been performed by this preparation.

The finite package now implements all24 Redis phases and20 Immich phases. Its
private commands and exact native receipts live under the ignored0700 operation
workspace. Public CI imports only public tests/helpers. No private payload,
infrastructure credential or sealing private key is committed.

## Qualification and limits

- Full private native suite:89 tests passed in216.784seconds. It includes original
  owner/clock exclusion, real-child lost replies, full Redis current-memory and
  live/cold AOF recovery, binary keys/TTL/streams/queues, native PG physical and
  independent logical restore, full POSIX population, encryption and cleanup.
- Assembled memory backup:2/2 passed in20.445seconds, including a live synthetic
  source, private streams, two relay-path ciphertext copies, separate key,
  independent decryption/engine recovery and exact evidence recheck. Both relay
  endpoints are local fixtures; this does not establish real off-NAS survival.
- Full native restore suite:4/4 passed in79.362seconds, including rejection of a
  dirty PG cold archive, correct physical PG identity and independent logical
  recovery. Dedicated PG export/archive tests:2/2 passed in5.892seconds while
  the original synthetic PG instance remained running.
- Current public Redis native suite:8/8 passed in112.615seconds. Public state
  tests11/11 and chart contract tests7/7 passed. Both materialized active
  candidates were rendered and passed the same preservation contracts; their
  complete renders also match the reviewed candidates before outage.
- Exact chart layers/schema:47/47 resources valid. Native alert-rule tests passed.
  Relevant pre-commit hooks and diff whitespace checks passed.
- Offline native sealing used the repository's exact`seal.sh` with a newly
  generated synthetic controller key/certificate only. It proved verifier-only
  default-account preservation, distinct maintenance credential, strict scope and
  native recovery-unseal. Real credential creation and unsealing remain Task6.
- Installed PVE/QGA/NFS prerequisites were checked read-only, including nested
  native QGA100 terminal handling and fresh full-growth quota accounting. Existing
  Jellyfin CSI identity/retirement primitives were qualified read-only against
  the real binding/WWN/ext4/raw generation. No new remote allocation, snapshot,
  helper creation or other remote mutation is claimed qualified by those probes.
- The exact final read-only photo-check command passed against the existing
  Immich asset:4,112,724bytes matched its original metadata checksum, with no
  photo saved and no credential forwarded. Redirects are refused.

These are synthetic qualification timings, not production restore/outage
measurements. Real data may have different volume and workload behavior. The
execution limits are explicit original clocks, not an inferred ETA.

## Resulting behavior

Redis stays alive until both current-memory and live-AOF native recovery pass.
Full frozen target data passes before consumer startup. Native ACLs preserve all
existing app passwords while preventing the previously reproduced Dispatcharr
persistence-disable behavior. The selected later DVR queue reset remains stock.

Immich takes a coordinated database/photo checkpoint while all21 overlapping
writable-mount workloads are stopped, then resumes19 unrelated media workloads
at the immutable barrier. Photos/model cache stay on NFS. Only the dedicated
PG17 physical data moves, with its identity and current extension/image packaging.

Activation starts only the target database under held Argo automation. It verifies
native state, recreation, healthy-worker movement and restored normal placement
before releasing consumers. Full current Git revision vectors preserve sync
options; a six-minute continuous native watch follows normal automation release.

Unknown replies preserve original intents/children/deadlines; no mutation replay,
new ownership or deadline renewal is implied. Before authority, any return to the
source requires target retirement and source validation. After authority, new CSI
writes are preserved and stale NFS is never reopened automatically.

## Delivery boundary

The independent final review and hosted exact-head CI are separate gates from
these local results. Preparation can be merged without activating candidate
storage, but active merges, outages, transfers and cutovers still require the
[production execution proposal](../plans/2026-10-19-redis-immich-production-execution.md).
The [Redis](../../runbooks/redis-storage.md) and
[Immich](../../runbooks/immich-storage.md) runbooks define recovery and retention.
