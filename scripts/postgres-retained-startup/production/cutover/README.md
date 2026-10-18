# Inactive PostgreSQL cutover states

These are review and render inputs outside ApplicationSet discovery. They do not
change a workload or authorize production execution. The
[storage runbook](../../../../docs/runbooks/postgresql-storage.md) defines
backup, restore, fencing and rollback gates.

`states.yaml` names each affected consumer, its real values path, and exact hold
and release overrides. The stage table defines PostgreSQL replicas/storage,
enrollment-hook presence, pilot/consumer release and backup suspension. This is
an operation contract, not a custom controller. At activation, merge the overrides
into each application's actual values; applying them before those values can
leave Authentik's explicit replica count unchanged.

The concrete stage/acceptance table below separates each release gate.

`postgres-held-values.yaml` applies last to render either the current NFS values
or the final prepared CSI overlay at zero replicas. `source-hold.yaml` reuses the
qualified Filebrowser admission pattern for the preserved PostgreSQL NFS claim.
It denies Pod CREATE/UPDATE and does not terminate an already running Pod. Install
it only during the approved stopped-writer operation; no source-helper exception
is needed because the cold archive uses VM300's read-only NAS mount. Keep it after
release. Removing it or restoring the old writer requires a separately verified
rollback using the newest state once the target has started.

The enrollment Job must be absent while PostgreSQL is stopped; retain its scripts,
config and credentials. Restore the unchanged generation-specific hook only after
the guarded server is healthy. The pilot remains held until the current full hook
passes. Active backup Jobs must finish before shutdown; suspending the CronJob
alone does not drain them. The main server and exporter containers, image pins,
credentials and SQL declarations stay unchanged.

The production cutover is complete. CI replays its stage contract and renders
the reviewed historical consumer and PostgreSQL inputs from `released-inputs.json`.
Every archived file must match the released hashes in `patches/index.yaml`; all
patch hashes, intermediate states and replica-only hold/release checks remain
enforced. Current application changes and removals do not change this historical
rehearsal. Current enrollment generation and hook validation remain separate.
The archive is test input, not an executable recovery or redeployment plan.
Offline lab admission and synthetic PostgreSQL backup/restore qualify procedure
only. The actual production cold backup still needs independent restore acceptance
before the retained target can be released.

## Concrete Git changes for the approved operation

`patches/` contains sequential, inactive diffs for the actual application paths.
Merging this preparation installs none of them. The index records every patch's
SHA256 and the full before/after file hashes, including unchanged chart descriptors
and value layers. CI applies all diffs in a temporary directory, verifies their
scope and every state, and renders the real consumer/PostgreSQL charts. It reverses the
archived released state to baseline in that temporary directory. Any archived
input outside the reviewed released hashes fails. A new live operation requires
fresh source qualification and review; these old patches must not be applied to
current application inputs.
The final consumer, enrollment Job and CronJob files return to their original bytes.

Prepare each actual PR from the preceding accepted state, using only its indexed
patch. Run the complete CI checks before merging it. Do not apply these changes
live or merge an actual stage PR until the separately reviewed execution scope,
helpers, real recovery locations and outage are approved. Do not use an unattended
merge chain: Git merge is not evidence that the previous runtime gate passed.

| Patch | Runtime gate before advancing |
|---|---|
| `01-clients-held.patch` | Clients/pilot zero; backup suspended; all backup/enrollment Jobs drained; no unexpected DB writer; PostgreSQL still running |
| `02-nfs-held.patch` | Server zero and absent; source PVC/PV protected; admission hold effective; exact native PG18 identity and clean shutdown; cold encrypted backup and independent real restore accepted |
| `03-target-held.patch` | Populated exact target accepted; sole copy helper terminated/unmounted/detached; immutable old StatefulSet replaced at zero with UID preconditions; target binding and new zero-replica controller verified |
| `04-server-only.patch` | New-write boundary recorded **before merge**; sole guarded target server starts; physical/catalog/application semantic baseline and exporter readiness accepted |
| `05-hook-only.patch` | Full non-selective PostgreSQL sync and repeat sync; exact current-generation enrollment acceptance, canonical logins and unchanged established objects verified |
| `06-hook-pilot.patch` | Ordered completion/login gates and original fixed pilot sentinel accepted |
| `07-authentik-only.patch` | Original server2/worker1; native login and OIDC acceptance |
| `08-consumers-only.patch` | Remaining original replicas restored; each affected application's preserved records/behavior and migration/login logs accepted; backup remains suspended |
| `09-released.patch` | Resume backup scheduling only after all application acceptance; verify scoped applications, then complete the approved restart/movement and cleanup checks |

Installing the target binding for the approved sole copy helper is a separately
reviewed imperative step before patch03. Patch03 publishes the same prepared
PV/PVC and guard durably. It deliberately has no automatic StatefulSet
`Force`/`Replace` option: the immutable claim-template change requires the exact
UID-tested controller replacement while old/new servers remain held. Source
protection is verified on the actual existing PVC/PV; these diffs do not manufacture
a replacement NFS claim or new NFS data directory.

The hook is omitted starting at patch01; its ConfigMap, completion roles and sealed
credentials stay unchanged. Removing its source file does not prove an existing
Job has finished. The source admission policy is added at patch02 and retained in
every later state. It denies old-claim Pod creation/update even after target release.
Authentication-dependent services can lose access during the Authentik hold; the
approved operation retains independent SSH management.

The hashes and schema checks establish reproducible Git inputs. Runtime receipts
establish shutdown, backup/restore, copy, fencing and application acceptance. Both
are required. Never reverse patches to reopen the old NFS writer after target
startup: startup itself may write, so rollback must recover the newest state as
specified in the storage runbook. Interrupted or ambiguous operations retain the
original maintenance owner and evidence until reconciled.
