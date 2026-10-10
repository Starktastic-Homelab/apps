# Live storage migrations with final Git reconciliation

Status: proposed written design. The user approved the direction in conversation;
the maintenance mechanism below requires isolated qualification before production.
This document authorizes no outage, allocation, credential transfer or cutover.

## Intent and scope

Move private application state from NFS to retained Proxmox CSI, and use official
PostgreSQL integrations where existing data can be preserved. Complete the live
cutover and restart the application before asking the user to merge its final
reconciliation PR. Keep ordinary cluster rebuilds driven by Terraform, Ansible
and Git, without Velero or a manual backup checkpoint.

This design defines the operational workflow and first migration order. It does
not design every application's migration, change the CSI driver, move shared
media or implement a general migration controller. Per-application preparation
must still establish exact identities, writers, backup, copy and acceptance steps.

The October10 inventory has Jellyfin and Filebrowser using retained CSI. Shared
PostgreSQL and Immich's separate PostgreSQL remain on NFS. Shared media, downloads
and multi-consumer files remain on NFS. Historical SQLite files are leads for
investigation, not proof of an application's currently selected database engine.

## Approach

Use native ArgoCD deny sync windows to hold only the Applications that own resources
being changed. Use the existing VM300 maintenance runtime and per-operation
records for the approved live commands. Prepare the final manifests before the
outage; update them with proven storage identities and validation results afterward.

Two alternatives were considered:

- Disabling an Application's automated sync policy does not hold this deployment:
  the cluster-apps ApplicationSet uses RollingSync, which initiates sync operations
  itself. ApplicationSet ownership also makes a temporary child-spec edit fragile.
- Pausing the ArgoCD controllers would affect unrelated services and suspend
  ordinary reconciliation. App-specific windows retain a narrower scope.

Live preflight on October10 found ArgoCD v3.5.3, RollingSync on cluster-apps and
ordinary automatic sync on config-apps. All Applications use the default project.
The default AppProject has no sync windows, owner references or Argo tracking
annotation; no AppProject declaration was found in the inspected repository.
Recheck this ownership before every operation; Helm/bootstrap or future Git
ownership must not silently remove an active hold.

## Maintenance hold

Add one operation-owned deny window to the existing project using an exact list
of Application names. Do not use namespace, cluster or wildcard selectors. The
proposed window recurs every minute, lasts 24h, uses UTC, and sets manualSync and
syncOverrun to false. Its description identifies the operation. Repetition keeps
the hold active until explicit removal, including after a lost maintenance session.

ArgoCD documents that RollingSync respects sync windows. Its v3.5.3 source makes
an active deny window reject syncs unless the relevant manual exception is enabled.
These are reasons to qualify this mechanism, not evidence it has been rehearsed.

Before stopping a writer:

1. Require every affected Application to be idle, with no pending, running,
   terminating or scheduled retry operation. Resolve existing operations before
   activating the deny window, while the original workload is still intact.
2. Record the project's UID, resource version and complete original window list.
   Add the owned window with a concurrency precondition, preserving other entries.
3. Verify the hold is active for every resource-owning Application, including
   base-configs if it owns a PVC, PV or CronJob being changed. Blocking base-configs
   pauses its other changes too; include that scope in the operation approval.
4. Recheck operation state after activation and prove no resource application is
   underway. If an operation raced with the hold, stop before writer shutdown and
   use the qualified recovery procedure. A window declaration alone is insufficient.
5. Verify no repository change removes/renames the affected Application or changes
   its project while held. Sync windows do not prevent Application deletion,
   arbitrary Kubernetes writes, operator actions or independent controllers.
6. Confirm all writers and backup jobs, suspend the affected schedules, install
   the app-specific old-source Pod guard, and stop all writers. Existing Pods must
   terminate and the source must unmount cleanly before cold copy or backup.

The hold must survive ApplicationSet reconciliation and Argo controller restart
in an isolated qualification. Test denied manual sync, RollingSync, queued sync,
retries and a recurrence boundary; prove an unrelated app can still reconcile.
Test exact owned-window removal with another window present. If any scenario
can reapply old state, stop and revise the mechanism before production.

There is an exact-version release hazard: v3.5.3 checks sync windows before handling
operation termination, so a blocked Running/Terminating operation may remain
nonterminal. RollingSync can queue operations during live drift even if acquisition
started idle. Qualification must establish how to discard any operation queued
while held without applying its stale revision, including after controller restart.
Do not assume terminate-operation drains a denied operation. The production
workflow is unavailable until safe acquisition and stale-operation release pass.

RollingSync may delay other rollout groups while a held app is unhealthy. This is
a temporary deployment-order effect, not a reason to promise completely independent
rollouts. Runtime availability of unrelated apps should remain unchanged.

## Per-application operation

Preparation occurs while the application is running: render its actual value
layers, inventory every direct and indirect writer, measure its directory, select
capacity, draft the final Git binding, and prepare app-native integrity and restore checks. Preserve
image pins and avoid combining upgrades with a storage or database conversion.

The writer inventory must compare exported paths and subpaths, not only PVC names.
Filebrowser's writable /srv/apps mount exports /mnt/apps/pv, the parent of the
private NFS directories. Temporarily stop Filebrowser too during the cold-copy
window unless an effective, qualified write exclusion is established. Include its
Application in the hold and its brief outage in the operation scope. Also account
for NAS-host writers and unmanaged exports. A guard on one old PVC cannot exclude
writers using a different claim that exposes the same directory.

One concrete operation approval covers the named application's outage, exact
source/destination, backup/restore, helper mounts, live cutover, acceptance and
owned temporary-resource cleanup. New secret transfers require their own explicit
scope. Draft manifests and scripts must be reviewable before asking for approval.

After the hold and verified writer stop:

1. Protect the exact source claim against prune/delete and set its bound PV to
   Retain. Preserve the old-source guard beyond the cutover. Capture a consistent
   backup outside the NAS failure domain with full readback verification.
2. Allocate the approved retained image only after fresh volume-name, identity,
   quota and owner checks. Reject a conflicting existing image. Stock CSI may
   format this explicitly approved blank target; missing established data is an
   error. Use static Git PV/PVC bindings that survive fresh Kubernetes metadata.
3. Copy the complete private directory with numeric ownership, permissions, ACLs,
   xattrs and required filesystem semantics. An optional live pre-copy cannot
   replace the final stopped-writer copy. Verify content and metadata before startup.
4. Verify an independently restored backup with engine-appropriate checks. Reuse
   qualified transport/copy tooling, but do not infer recoverability from a hash
   or startup alone. Novel engines/conversions require isolated application restore.
5. Terminate and detach every helper. Switch the live workload to its final claim,
   placement and fencing settings, then start it and perform app-specific tests.
   Verify clean recreation and movement between healthy CSI workers; never force
   takeover from an unverified NotReady writer.
6. Finalize one reconciliation PR containing the permanent binding, claim choice,
   guards and workload changes, plus sanitized validation and recovery instructions.
   Exclude temporary replicas0, maintenance windows and secret values from the
   final desired state. Keep Helm/baseApp inheritance intact.

The app can be available while awaiting this final merge, but its Argo Application
remains held and may be OutOfSync. The final PR is still necessary for completion.
Use one final PR per application or explicitly coordinated small cohort. The first
pilot cohort is Prowlarr alone; this is not one PR covering the entire inventory.

## Failure and rebuild boundaries

An interruption retains the hold, source protection, target and backup. Recover
from recorded identities and actual native state; never replay an uncertain
allocation, copy or delete blindly. Remove the owned window only after recovery
or accepted final reconciliation, preserving concurrent project changes.

Before any writes on the target, rollback may return to the protected source after
the new writer is stopped. Once the target has accepted writes, the old source is
stale. Returning to it requires a fresh consistent reverse copy/conversion or an
explicitly accepted loss boundary. Git revert alone is not a data rollback.

Between live cutover and final PR merge, do not run a full control-plane/cluster
replacement: fresh metadata would restore old Git state and would lose the
temporary hold. This interval is a deliberate maintenance boundary. After merge,
normal rebuilds must work without operator checkpoints. A source guard retained
in the current cluster does not establish fresh-cluster protection by itself.

To finish, verify the merged Git revision renders the exact accepted permanent
resources, resolve stale queued operations before release, remove only the owned
window, and observe reconciliation to that revision as Healthy/Synced. Preserve
the accepted encrypted backup and old source; cleanup authority excludes them.

## Migration order and independent assessments

| Track | Next step | Dependency or exception |
|---|---|---|
| Workflow | Isolated qualification of native maintenance hold | Required before any new live cutover |
| First CSI app | Prowlarr private /config, preserving SQLite | One main writer; measure current bytes and qualify existing state first |
| PostgreSQL prerequisite | Select and qualify deployment plus automatic database/role enrollment | Complete the PostgreSQL research decision before step 3; prove unattended metadata-loss recovery |
| Shared database | Selected shared PostgreSQL deployment on retained CSI | Own operation after qualification; include database clients, backup jobs and Authentik availability in outage scope |
| PostgreSQL conversion | Autobrr, then Seerr instances, then Bazarr | Start conversions only after shared PostgreSQL CSI and tested restore; rehearse pinned versions |
| Further conversions | ntfy, Grafana and pgAdmin qualification | Require proof of existing-data preservation, not just backend configuration |
| Later CSI waves | Embedded state, files for PostgreSQL-backed apps, monitoring | Recheck writer topology and full growth budget before each small cohort |
| Separate design | Calibre library and Dispatcharr shared data | Calibre metadata.db is beside books; Dispatcharr web/Celery share a claim across Pods |
| Separate performance work | qBittorrent payload storage | Preserve shared completed/incomplete download paths during config migration |

Autobrr's official converter makes it the strongest first database-conversion
candidate. Research/rehearsal design can proceed alongside CSI preparation;
production cutovers sharing PostgreSQL, NAS quota or attachment resources remain
serialized. Do not move Autobrr to CSI first merely to migrate its SQLite database
again immediately afterward: determine and rehearse the final engine first.

The user requested PostgreSQL deployment/enrollment research before step 3 because
database, user and password creation are currently manual. The
[research report](../reports/2026-10-10-postgresql-deployment-enrollment-research.md)
shortlisted CloudNativePG qualification and an enrollment Job on the existing
server. The [disposable qualification results](../reports/2026-10-10-cnpg-qualification-results.md)
reject stock CNPG 1.30.1 for the proposed retained-data rebuild design: an
interrupted orphan-PVC adoption required manual intervention. Full Terraform
rebuild tests were not completed. Continue with the existing deployment plus an
idempotent enrollment Job as the next design direction; that Job and the shared
PostgreSQL CSI cutover remain unimplemented and require their own reviewed plan
and live approval. Credentials must recover consistently from durable encrypted
declarations. Any deployment replacement must preserve existing databases and
does not authorize a PostgreSQL major upgrade.

Treat converter dry-run as potentially mutating. Inspect the exact installed
Autobrr converter: current develop-branch code can initialize PostgreSQL schema and modify
SQLite fixups before its dry-run branch, excludes sessions, and can report a
completion message alongside table errors. Run qualification against disposable
copies only, reject conversion errors, compare preserved records and explicitly
accept any documented session reset. These source findings are not yet verified
against the installed 1.86.0 tool. A successful process exit is insufficient.

Seerr and Bazarr document existing-data conversion using PGLoader. ntfy's importer
requires matching schema versions and qualification of auth, cache and webpush
stores. In v2.28.0 the importer expects cache schema14 while the app uses schema15;
qualify its documented create-schema/import/start ordering before considering it
ready. Do not modify production schema markers to bypass the check. Grafana's
engine migration is user-managed, and pgAdmin's external database
documentation alone does not establish preservation of the current configuration.

Servarr conversions, Home Assistant recorder history and CrowdSec identity recovery
have additional preservation limitations. Keep their existing embedded engines on
CSI initially. Preserve shared NAS media, download payloads, ingest paths and
rebuildable caches according to the previously agreed storage policy.

Do not assign target sizes from PVC requests or NFS kubelet capacity. Measure
actual source directories and shared dataset use at execution time. The existing
128GiB aggregate quota must cover full planned image growth, staging, snapshots,
preserved archives and headroom. Shared PostgreSQL also needs measured resource
and connection headroom before adding new clients; its declared 1Gi memory limit
is not evidence of sufficient capacity.

An October10 live directory scan measured Prowlarr at 305MiB logical/105MiB
allocated and shared PostgreSQL at 640MiB logical/251MiB allocated. These were
active filesystem scans, not consistent backups or database-size measurements.
The CSI dataset reported quota128GiB, used56.5GiB, available71.5GiB, including
2.47GiB used by snapshots. Current availability is not reservation for full image
growth; refresh and reconcile all existing allocations/archives before sizing.

## Acceptance and remaining decisions

The workflow is acceptable when isolated tests establish a reliable scoped hold,
interruption recovery and release; the first application's operation shows no
merge wait during its outage; its final merge restores Git/live agreement; and
the permanent storage declarations retain the existing unattended rebuild model.

The next review is this written workflow and its proposed first candidate. Its
implementation plan will specify the isolated qualification and Prowlarr read-only
preflight. Before step 3, resolve the PostgreSQL deployment/enrollment choice and
qualify its storage and credential recovery. Production Prowlarr and shared PostgreSQL execution will each require
a concrete operation approval with refreshed capacity and recoverability evidence.

## Primary references

- [ArgoCD RollingSync](https://argo-cd.readthedocs.io/en/release-3.5/operator-manual/applicationset/Progressive-Syncs/)
- [ArgoCD sync windows](https://argo-cd.readthedocs.io/en/release-3.5/user-guide/sync_windows/)
- [ArgoCD v3.5.3 sync-window implementation](https://github.com/argoproj/argo-cd/blob/v3.5.3/pkg/apis/application/v1alpha1/types.go)
- [ArgoCD v3.5.3 sync/termination ordering](https://github.com/argoproj/argo-cd/blob/v3.5.3/controller/sync.go)
- [Autobrr PostgreSQL conversion](https://autobrr.com/installation/supplementary/postgresql)
- [Seerr database migration](https://docs.seerr.dev/extending-seerr/database-config/)
- [Bazarr PostgreSQL migration](https://wiki.bazarr.media/Additional-Configuration/PostgreSQL-Database/)
- [ntfy v2.28.0 importer](https://github.com/binwiederhier/ntfy/tree/v2.28.0/tools/pgimport)
- [Autobrr current converter implementation](https://github.com/autobrr/autobrr/blob/develop/internal/database/tools/convert.go)
- [Grafana database migration guidance](https://grafana.com/docs/grafana/latest/setup-grafana/installation/)
- [pgAdmin 9.18 external database](https://www.pgadmin.org/docs/pgadmin4/9.18/external_database.html)
