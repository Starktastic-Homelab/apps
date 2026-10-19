# Paperless retained private data

The preparation adds a static 1GiB retained CSI binding and a read-only startup
ConfigMap. The inactive production values move only `/usr/src/paperless/data`.
Documents/media and consume keep the existing `paperless-ngx-data` NFS claim;
the empty inherited `/config` mount stays on NFS. No application image, database,
Redis setting, credential or endpoint is replaced.

The startup guard checks the retained identity, native Tantivy metadata/settings
and segment stores, index version and the existing GDBM schedule header. It never
opens an engine writer, repairs files or initializes empty data. Run the negative
and actual-render checks with `scripts/test-paperless-retained.py`.

`test_native.py` creates synthetic state with the exact configured Paperless
image's own schema/tokenizers and GDBM library, closes it, uses the shared cold
copier and reopens/queries the recovered state twice. It verifies byte/POSIX
metadata equality and unchanged source/target. No network or production state is
used. The current Tantivy reader needs a writable lockfile, so native recovery
runs on the isolated target after the read-only guard; native reads leave file
bytes and timestamps unchanged.

Before activation, require green review/CI and a finite independently reviewed
command package. Under the existing maintenance owner, hold the relevant Argo
owners and frontend, stop Paperless and Filebrowser, verify runtime/mount
retirement, add the identity marker to the exact cold source, and populate the
fresh target from a read-only source mount. Verify native recovery before stock
startup, preserve source data, remove exact helpers and reconcile through the
activation PR. Confirm original document/account/key fingerprints, native search,
Redis-backed task behavior, restart and both-worker startup before release.

The prepared source hold blocks new Pods mounting old private `data` through the
original NFS claim, while allowing its exact `media`/`consume` subpaths. Install
it only after copy helpers retire. Preserve old data and both source PVC/PV
identities; do not automatically fall back after the target has accepted writes.

The pinned [search backend](https://github.com/paperless-ngx/paperless-ngx/blob/v3.1.3/src/documents/search/_backend.py)
uses file locking and an on-disk index, which is the reason for this migration.
Capacity checks include growth of all valid raw images, the historical partial's
allocated space, 512MiB staging and 8GiB spare; quota remains 288GiB. The initial
private directory is about 35MiB. Use the existing verified expansion procedure
if future data growth requires more space.
