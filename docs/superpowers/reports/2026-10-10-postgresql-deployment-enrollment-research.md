# PostgreSQL deployment and application enrollment research

Date: 2026-10-10. Read-only research and proposed direction; no production changes,
lab allocation, credential transfers or migration authorization.

## Qualification outcome

The approved [disposable qualification](2026-10-10-cnpg-qualification-results.md)
passed automatic enrollment but failed interrupted orphan-PVC adoption with stock
CNPG1.30.1. Use the existing PostgreSQL deployment plus an enrollment Job as the
next implementation direction; production migration remains separately gated.
The assessment below records the initial shortlist and why this recovery test was
required, rather than a current CNPG adoption recommendation.

## Initial recommendation

Evaluate CloudNativePG (CNPG) as the leading replacement for the shared PostgreSQL
deployment, with automatic application enrollment. Keep the existing server plus
a small enrollment Job as the minimal fallback. Decide before step 3 of the
[storage migration design](../specs/2026-10-10-live-storage-migrations-design.md).

CNPG must first prove the existing unattended Terraform/Ansible/Git rebuild
contract with an unmodified operator and driver. Automatic enrollment alone does
not justify compromising that contract. Keep one shared PostgreSQL instance with
separate application databases and restricted roles; a server per application is
unnecessary. Additional replicas are a separate availability/fencing design.

## Current deployment and requirements

Repository inspection found Bitnami chart 18.12.4, one primary in `databases`, an
8Gi NFS claim, digest-pinned server image, and an existing sealed administrator
Secret. Applications have their own credentials. The live catalog contains
authentik, dispatcharr, lingarr, listmonk, mealie, paperless, vaultwarden and
vikunja databases, plus postgres. Presence does not establish active clients or
role names. The server's live version, extensions, privileges and dependencies
must be inventoried before migration; the backup client's version is not proof
of the server version.

The daily backup is a checked, compressed `pg_dumpall` on the same NAS. It does
not cover NAS loss. The current init container removes `postmaster.pid`; this is
not proof that an old writer is excluded and must be reviewed before CSI use.

The solution must recreate enrollment and credentials after loss of all k3s
metadata, reuse the latest surviving database disk without a backup checkpoint,
and prevent takeover until old writers are verifiably retired. Keep static Git
PV/PVC bindings, retained images, RWOP access and the existing CSI generation
placement policy. Dynamic replacement storage cannot stand in for missing data.

## Alternatives

| Option | Application enrollment | Assessment for this homelab |
|---|---|---|
| CloudNativePG | `DatabaseRole`, `Database`, supplied password Secrets | Leading lifecycle candidate; retained-data metadata-loss recovery needs qualification |
| Existing PostgreSQL plus Argo Job | Idempotent SQL creates roles/databases and applies credentials | Minimal fallback; preserves current server; runs on sync rather than continuously repairing SQL drift |
| Crunchy PGO | Runtime `spec.users`, databases, generated or supplied credentials | Capable replacement with Patroni/pgBackRest; same rebuild proof still required |
| Percona PostgreSQL Operator | Runtime users/databases, generated or supplied credentials | Comparable alternative with Percona images; no enrollment advantage sufficient to prefer it here |
| Zalando Postgres Operator | Users/databases/prepared databases; generated credentials, cross-namespace options | Capable, but adds Spilo/Patroni and more lifecycle configuration |
| StackGres | Versioned `SGScript` SQL execution | Broader platform while enrollment still needs SQL; outside shortlist |
| Movetokube external Postgres operator | Enrollment against an existing server | Inspected implementation stores a generated role identity in CR status; unsuitable without proof of stable recovery |
| Crossplane SQL provider | Database, role and grant resources against an existing server | Relevant external-server option, but adds Crossplane/provider infrastructure for this one problem |

Crunchy and Percona support ongoing additions, rather than only initial bootstrap.
Crunchy's current developer terms allow personal/internal production use by
individuals and organizations under 50 employees; operator and image terms are
distinct. Neither alternative's backup features establish fresh-metadata adoption
of our exact retained images. [Crunchy user management](https://access.crunchydata.com/documentation/postgres-operator/latest/architecture/user-management),
[image terms](https://www.crunchydata.com/developers/terms-of-use),
[Percona 3.0 users](https://docs.percona.com/percona-operator-for-postgresql/3.0.0/users.html).

Zalando offers cross-namespace credentials, but its cluster-deletion settings need
explicit PVC/Secret protection. StackGres supplies repeatable SQL execution rather
than eliminating enrollment SQL. [Zalando user guide](https://opensource.zalando.com/postgres-operator/docs/user.html),
[administration](https://opensource.zalando.com/postgres-operator/docs/administrator.html),
[StackGres SQL scripts](https://stackgres.io/doc/1.19/administration/sql-scripts/).

The inspected Movetokube controller generates a new suffixed SQL role when CR status
has no recorded role, and user deletion drops that role. Recreating metadata and
an output Secret alone is not demonstrated recovery of the original identity.
This is a source finding, not a claim about every release. Crossplane can manage
an existing PostgreSQL server; its credentials and orphan/deletion semantics would
still need qualification. [Movetokube controller](https://github.com/movetokube/postgres-operator/blob/master/internal/controller/postgresuser_controller.go),
[Crossplane SQL provider](https://github.com/crossplane-contrib/provider-sql).

## Enrollment with CloudNativePG

Released CNPG 1.30.1 provides standalone roles and databases. A new service would
declare its role, database owner and password Secret; no manual SQL session is
needed. Extra managed roles do not automatically receive generated passwords:
the bootstrap application user is a different feature. Use explicit retain
policies. Standalone roles apply on specification/Secret changes; inline managed
roles additionally repair periodic catalog drift.
[Role management](https://cloudnative-pg.io/docs/1.30/declarative_role_management/),
[database management](https://cloudnative-pg.io/docs/1.30/declarative_database_management/),
[release](https://github.com/cloudnative-pg/cloudnative-pg/releases/tag/v1.30.1).

Proposed onboarding generates one password outside the cluster and seals the
corresponding database-namespace and application-namespace Secrets into Git using
the existing workflow. Rebuilds recover that password, rather than generating a
replacement. The sealing private key must remain independently recoverable.
No plaintext password enters Git and no secret-reflection controller is needed.
[Sealed Secrets recovery and scope](https://github.com/bitnami/sealed-secrets).

The role, Cluster and password Secret must share a namespace. Existing-role
adoption resets omitted attributes/memberships to defaults, so capture them first.
Database/schema ownership and extensions do not constitute a general table-grant
or default-privilege API; unusual grants may still need controlled SQL. Extension
packages must exist in the selected image. Password rotation must coordinate
database reconciliation with clients; environment-based credentials require Pod
replacement. [CNPG API](https://cloudnative-pg.io/docs/1.30/cloudnative-pg.v1/),
[Kubernetes Secret consumption](https://kubernetes.io/docs/tasks/inject-data-application/distribute-credentials-secure/).

This requires a CNPG-managed PostgreSQL deployment. Its role/database resources
are not an enrollment sidecar for the existing Bitnami server.

## Rebuild qualification is the deciding gate

CNPG documents static PV support, but this alone does not mean that a fresh
`Cluster` adopts existing PGDATA. In released v1.30.1, ordinary initdb preparation
renames recognizable existing data directories, or removes unrecognized ones,
before initializing a new database. Bound/Healthy can therefore describe a new,
empty database on a surviving image. [Static storage](https://cloudnative-pg.io/docs/1.30/storage/#static-provisioning-of-persistent-volumes),
[released directory preparation](https://github.com/cloudnative-pg/cloudnative-pg/blob/v1.30.1/pkg/management/postgres/initdb.go#L138).

Released source also has orphan-PVC adoption before first initialization. It
discovers ownerless claims with cluster labels and instance serials, reconstructs
primary/initialization state and assigns new ownership. For one fixed instance,
Git could recreate `<cluster>-1` before permitting Cluster reconciliation.
This is a source-based candidate, not a documented general recovery guarantee.
The source updates initialization state before finishing PVC ownership, so
interruption at that boundary needs testing. Adoption also clears CNPG fencing
annotations. [Exact v1.30.1 adoption implementation](https://github.com/cloudnative-pg/cloudnative-pg/blob/v1.30.1/internal/controller/cluster_restore.go#L42).

Keep one authoritative disk initially. Multi-instance failover can change which
disk is primary; fixed labels after metadata loss cannot establish the latest
writes. Automatic promotion also needs fencing analysis beyond indefinite
NoExecute tolerations. Same-NAS replicas do not provide NAS availability.
CNPG's default primary disruption budget needs integration with verified worker
retirement. [Failover](https://github.com/cloudnative-pg/cloudnative-pg/blob/v1.30.1/docs/src/failover.md),
[worker maintenance](https://github.com/cloudnative-pg/cloudnative-pg/blob/v1.30.1/docs/src/kubernetes_upgrade.md).

Live read-only `/version` confirmed k3s `v1.37.0+k3s1`. CNPG 1.30's support table
lists Kubernetes 1.34–1.36 as supported and 1.37 as tested but unsupported.
Refresh release compatibility before selecting lab and production pins; do not
silently change the homelab Kubernetes version.
[Supported releases](https://cloudnative-pg.io/docs/1.30/supported_releases/).

## Migration and fallback

Prefer a one-time logical import into a new CNPG disk rather than copying Bitnami's
directory into a different image/layout. CNPG's monolith import handles multiple
databases and roles. Preserve owners, extensions, locale behavior and application
authentication; imported roles lose superuser status and reserved roles are
excluded. Verify the current server major, pin a compatible destination, and avoid
combining this with a major upgrade. Stop all source writers for the final import;
it does not automatically catch up later writes.
[Database import](https://cloudnative-pg.io/docs/1.30/database_import/).

The fallback is an explicitly non-destructive, rerunnable enrollment Job against
the existing server. Check catalogs, create absent objects, apply canonical
credentials/grants and reject incompatible ownership. `CREATE DATABASE` cannot
run inside a transaction. Bitnami and official-image init scripts only run against
fresh data, so they do not solve ongoing enrollment. Moving to the official image
would itself require layout/ownership qualification.
[psql](https://www.postgresql.org/docs/current/app-psql.html),
[Bitnami chart](https://github.com/bitnami/charts/blob/main/bitnami/postgresql/README.md),
[official PostgreSQL image](https://hub.docker.com/_/postgres).

A rerunnable Argo hook needs Secrets and database readiness before enrollment,
then successful enrollment before app startup. PreSync cannot depend on ordinary
same-Application Secrets being applied first; hooks do not run on selective sync.
This is sync-time automation, not continuous SQL drift correction.
[Argo sync phases and waves](https://argo-cd.readthedocs.io/en/stable/user-guide/sync-waves/).

Regardless of deployment, test an independent off-NAS database backup restore.
CNPG base backups plus archived WAL are useful disaster recovery, but the latest
archived WAL can lag live writes. Backup restoration cannot replace exact disk
reuse during ordinary rebuilds under the agreed freshness requirement.
[Recovery](https://cloudnative-pg.io/docs/1.30/recovery/),
[WAL archiving](https://cloudnative-pg.io/docs/1.30/wal_archiving/).

## Required disposable qualification

1. Enroll a new service solely through declarations and sealed credentials; test
   authentication, ownership, deletion retention and coordinated rotation.
2. Import representative existing databases at the same PostgreSQL major; compare
   roles, extensions and application data, then write additional sentinel records.
3. Replace all lab k3s compute and metadata using the real rebuild sequence,
   preserving the disk. Prove the same PostgreSQL system identifier, newest
   sentinels and recovered client credentials without a manual checkpoint.
4. Test interrupted adoption, late/missing claims, wrong metadata/image identity
   and missing/invalid PGDATA. Established-data failures must stop startup without
   new initialization, dynamic replacement or formatting.
5. Exercise normal Pod recreation, healthy-worker movement, verified worker
   retirement and an unreachable old writer. Prove placement/tolerations on
   bootstrap Jobs too, and no second writer before verified retirement.
6. Restore an independent backup and validate application recovery separately.

If passing this requires a custom CNPG fork, repeated operator intervention or a
backup freshness checkpoint, reject that fit and use the enrollment Job fallback.
This research defines acceptance criteria, not a lab execution plan: exact
resources, quota, credentials and cleanup must be specified before authorization.
