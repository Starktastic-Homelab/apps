# Retained PostgreSQL startup guard (inactive)

This source is outside ApplicationSet discovery. It changes no current server,
PVC, credentials or application. It is for an **already initialized PG18 server**
whose retained data must survive a fresh Kubernetes cluster. Initial installation
and logical restore require separate reviewed procedures.

The init runs before the unmodified Bitnami18.6 entrypoint, using the same pinned
server image. It requires an independently declared, canonical physical system
identifier, PG_VERSION18, real readable full-sized control/version files and searchable data directories,
and native `pg_controldata` success with no warnings. A CRC warning may accompany
exit0, so stderr is checked too. Missing/empty/wrong/unreadable data and standby or
recovery signals refuse startup. Signals are checked even if they are dangling
symlinks. Directory/version/control symlinks are deliberately unsupported.

The guard mounts data read-only, runs as UID/GID1001, needs no credentials or API
access, and never initializes, repairs or changes ownership. Only `/tmp` is
writable. The chart overlay disables volumePermissions and omits fsGroup so neither
an earlier ownership init nor kubelet fsGroup ownership handling precedes it.
Existing data must already be accessible to1001; verify this before activation.
These checks do not validate every data page or replace backups. CSI's own stock
filesystem handling is still covered by the previously accepted storage contract.

## Approved PID-file policy

A remaining `postmaster.pid` is left untouched and accepted after data identity
validation. The pinned Bitnami entrypoint removes it during restart cleanup,
**before Bitnami pre-init hooks**. It also removes standby/recovery signals; the
Kubernetes init rejects those signals first. The existing production BusyBox init
currently deletes the PID file unconditionally; this inactive overlay replaces
that entire init list when separately activated.

Single-writer safety relies on retained RWOP CSI storage, verified retirement of
old VM generations, and the control-plane/worker rebuild cohort policy. The guard
is not distributed fencing. Verify old writers are gone before permitting a new
attachment, including the already accepted manual fencing procedure after storage
faults. PID absence alone proves no such thing. Changing files concurrently with
the guard is outside this contract.

## Integration after source merge and native qualification

1. Record the physical ID on the intended, independently verified server (for
   example `SELECT system_identifier FROM pg_control_system()`), and retain it in
   reviewed desired state. Never auto-discover/adopt an ID from a newly attached
   disk at startup. A typo or this source's placeholder blocks startup.
2. Generate the non-secret ConfigMap from the exact reviewed source:

   ```sh
   kubectl create configmap postgres-retained-startup-guard -n databases \
     --from-file=guard.sh=scripts/postgres-retained-startup/guard.sh \
     --dry-run=client -o yaml > /private/review/postgres-retained-startup-guard.yaml
   ```

3. Copy that reviewed ConfigMap into the PostgreSQL Application's manifests and
   merge `values.yaml` as its final chart overlay. Replace the expected-ID
   placeholder with the verified ID. Preserve any separately reviewed required
   init containers and extra volumes when combining arrays; this overlay replaces
   arrays. Its data volume name/path match chart18.12.4's current layout.
4. Render the actual ApplicationSet value cascade. Confirm only the guard precedes
   the main entrypoint, the data mount is read-only in the guard, fsGroup is absent,
   volumePermissions is absent, no password/token mount reaches the guard, and the
   server/guard image pins agree. Review retained PVC/RWOP/fencing separately.

Any PG major, server digest, chart layout or data-path change requires rechecking
native tool behavior and these invariants. No production integration or startup is
authorized by merging this source PR.

## Checks

```sh
python3 scripts/test-pg-retained-startup.py
```

Requires Docker and PyYAML. Synthetic Docker volumes use the exact pinned native
image/tools, with no production mounts, network or credentials. Native `initdb`
initializes only a disposable fixture; it is never called by the guard. Checks
cover exact/wrong identity, malformed expected IDs, stale PID, replica/recovery
signals, wrong major, missing/symlink/unreadable inputs, a real CRC mismatch, and
empty/missing data. Every invocation compares file hashes before/after, even on
rejection; all fixture containers/volumes are removed and absence verified.
`--native-only` avoids PyYAML; `--manifests-only` avoids Docker. Set
`PG_STARTUP_TEST_RECEIPT` to save a non-secret result and cleanup receipt.

These source checks precede native Kubernetes startup and full Terraform/Ansible
fresh-metadata rebuild qualification. Those remaining gates must pass after merge
before production activation is proposed.
