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

| Stage | Required acceptance before advancing |
|---|---|
| nfs-held | All consumers/jobs drained, server cleanly stopped, source protection and admission hold verified |
| target-held | Encrypted off-NAS recovery copies and independent real cold restore accepted; populated target verified; helper detached; immutable controller replaced at zero |
| server-only | Sole guarded target server, original physical identity/catalog/semantics and readiness verified |
| hook-pilot | Full current-generation enrollment hook and retry accepted before pilot start; original sentinel and ordered pilot gates verified before consumer release |
| released | Authentik and all affected application behavior accepted; backup scheduling resumed |

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

CI verifies the stage contract and strict admission schema, then renders every
consumer with its actual globals/common/extras/application layers. Hold renders
must change only controller replica counts; release renders must equal baseline.
Offline lab admission and synthetic PostgreSQL backup/restore qualify procedure
only. The actual production cold backup still needs independent restore acceptance
before the retained target can be released.
