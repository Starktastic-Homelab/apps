# PostgreSQL backup failure handling and fresh restore

Date: 2026-09-21 Asia/Jerusalem. Production PostgreSQL18.6.

## Change

The scheduled job used `pg_dumpall | gzip` under POSIX sh. A failed producer
could leave a valid empty gzip, publish it, delete older backups and exit zero.
This was reproduced before editing: five failure scenarios incorrectly passed.

Dumping now finishes into a private temporary SQL file before compression.
Nonempty output and the pg_dumpall completion marker are required; compression
and gzip integrity must succeed before same-directory atomic publication.
Retention runs only afterward. Normal failures and handled signals clean both
temporary files. New files are mode0600. The client is pinned to18.6 and its
verified image digest, matching the server major. Four regression tests cover
seven scenarios: failed/partial producer, empty/incomplete successful output,
compression failure, corrupt output and successful publication/retention.
The success path also asserts restrictive archive permissions. CI runs this check.

## Fresh backup and restore evidence

A temporary pod ran the actual Helm-rendered script and pinned client against
production PostgreSQL, using the existing Secret reference. It wrote only to
emptyDir; no production CronJob, ConfigMap or retained backup file was changed.
A fresh33,127,974-byte archive expanded to156,803,747 bytes. It was copied to a
mode0700 local directory and restored with `psql -X -v ON_ERROR_STOP=1` into the
exact production Bitnami image, with Docker networking disabled and only a Unix
socket listener. Restore exited0 with no warnings. All nine expected databases
were present; all542 user tables were counted, totaling658,606 rows. Counts are
of restored data, not a value-by-value comparison with concurrently changing
production. PostgreSQL remained2/2Ready with zero restarts.

The first restore attempt failed because the target connection used template1,
which this `--clean` dump drops. Recreating the isolated target with a separate
bootstrap role and scratch database resolved the harness error; the archive
was unchanged. Full restore began again from an empty target.

The read-only backup-volume probe found approximately368GiB available, existing
archives totaling286MiB, and no stale `.tmp` files. Peak additional staging for
this dump was about181MiB (raw SQL plus compressed output). The1Gi PVC request
does not represent a measured per-directory NFS quota.

## Limits and rollout

SIGKILL or node loss can leave a private temporary file; traps cannot handle
those events. Such files are not published or pruned automatically. Inspect
and remove abandoned temporaries only after confirming no backup is active.
Same-NAS backups still do not protect against NAS loss; independent storage
and periodic restore exercises remain separate requirements.

Local regression, shellcheck, runtime shell parsing, actual-value Helm render,
configured pre-commit, Homepage coverage, Jellyfin compatibility and README
image checks passed. Independent review found no Critical/Important issues;
staging headroom was checked and its minor file-permission test gap addressed.
The scheduled job remains unchanged until the user merges the PR and Argo syncs.
After merge, run a fresh scheduled-job-derived backup and verify its completion
and resulting archive. The known invalid September15 archive was preserved.

Sanitized [restore evidence](evidence/2026-09-21-postgres-backup-restore.json).
Private dumps, restore instance and temporary Kubernetes resources are removed
after evidence capture; cleanup receipt is recorded in the evidence file.
