# Grafana PostgreSQL and retained-storage assessment

Status: synthetic and explicitly approved real-data conversion/recovery accepted.
Production configuration and storage are unchanged; no outage, enrollment, CSI
allocation, maintenance owner or migration hold has been started.

## Actual runtime

Grafana 13.2.3-distroless runs the same image used by the closed local lab:
`grafana/grafana@sha256:202e5d5b3f8499e70ccac7991eea6d7da72d2790eb2e0597e7987acf724e7180`.
It is Healthy/Synced with one Ready Pod and zero restarts. Effective admin settings
confirm SQLite. Its 2Gi NFS claim holds about 159.3MiB logical / 81.5MiB allocated.
`grafana.db` is about 14.3MiB, integrity ok, with 94 tables. Current metadata counts
include 2 users, 4 data sources, 43 unified resources, 553 resource-history rows,
95 data keys and existing OAuth/session state. These initial observations are distinct from the later consistent rehearsal copy
and do not establish a production conversion.

No explicit security-key override is declared in the main container, its ini file
or the two-key OIDC Secret. Admin settings mask security values; a masked setting's
presence must not be mistaken for a custom key. Preserve the exact current image,
config and Secrets; this operation does not rekey stored credentials.

The Helm Application is kube-prometheus-stack 91.9.0. Holding it also holds
reconciliation for other resources in that Application, although their running
services need not be stopped. Grafana currently has RollingUpdate strategy;
retained RWOP activation requires safe single-writer replacement behavior.
Filebrowser's parent NFS claim and the provisioner's parent export must be included
in the complete source-writer preflight before any cold-copy window.

## Synthetic evidence

A local internal-network Docker lab uses fixture credentials, no published ports,
no external egress and no real homelab database or Kubernetes Secret payloads.
The exact Grafana image creates a stock PostgreSQL 18.6 schema with 91 tables,
801 columns, 684 constraints and 252 indexes. All common-table columns match the
live SQLite schema. Three obsolete SQLite-only tables are empty in the live source;
refuse a later source if any becomes populated.

The previously qualified unmodified loader image is
`ghcr.io/ralgar/pgloader@sha256:e5ae0b8149058828938d0f14ccc1f793171db8c4c8b69b7b6b45dfd998f0149f`.
A new fixture SQLite instance created an additional user, an encrypted datasource
password and a Unicode dashboard with two revisions. Data-only conversion into the
stock target preserved all 87 application tables and 946 rows under native SQL
timestamp semantics. Four backend-specific schema-migration tables stayed native
to the initialized PostgreSQL schema. Do not replace target schema or copy SQLite
schema-operation SQL into the destination.

The independent comparison checks every column, including identities, nulls,
booleans, password hashes, encrypted values, modern resource content and history.
SQLite binary JSON is accepted as native PostgreSQL text only through strict,
byte-reversible UTF-8. Negative witnesses detect altered passwords, encryption
fields, resource content, missing history and malformed UTF-8.

SQL timestamps use PostgreSQL's native microsecond precision. A live metadata-only
profile found finer fractions in 16 values across six columns; no timestamp values
or user records were exported by that profile. The comparison uses PostgreSQL's
own casts rather than silently truncating timestamps in the checker. Preserve the
original SQLite precision in retained source/recovery. Do not call SQL timestamp
strings byte-identical across engines.

The converted stock app accepts both original synthetic admin and non-admin
passwords and returns the expected current dashboard/search results. A custom
PostgreSQL dump restores all 91 tables exactly into a different physical database.
The restored app opens the same dashboard. An internal fixture upstream receives
the correct Basic authentication password decrypted from the migrated ciphertext;
this tests decryption, rather than only the presence of secureJsonFields.

The synthetic lab generations are stopped and retained by exact identities for
cleanup. Synthetic success alone does not establish real OIDC login, production
datasource connectivity, CSI movement or production recoverability.

## Approved real-data qualification

After automatic review rejected the first transfer before execution, the user
explicitly approved the design's named payloads, private destinations, closed lab,
encrypted recovery retention and exact plaintext cleanup. The consistent SQLite
backup was then copied with the source opened read-only. No Kubernetes credential
Secret or infrastructure administrator credential entered the lab.

The initial real import exposed four legacy Go UTC timestamp strings rejected by
PGLoader. A new working copy changes only their SQL representation, retaining the
wall-clock nanoseconds and original source. Go's process-local monotonic suffix
has no SQL wall-clock meaning. PostgreSQL performs the final native cast. The
fresh import completed without loader errors. The maintained comparator accepts
all 87 application tables and 1883 rows, every field and duplicate included.
Native CHAR(44) padding is explicit and bounded; arbitrary trimming is forbidden.
The original source and the four PostgreSQL schema-operation logs remain intact.

An independent custom-format dump restores all 91 tables exactly into a different
physical PostgreSQL database. All 801 columns, 684 constraints and 252 indexes match
the stock contract. All 63 serial allocators have safe floors. A production-like
rehearsal with the exact dashboard provider and its 25 files accepts both existing
account IDs and organization roles, all 35 current dashboards/search results,
four datasource definitions, the folder and readable alert configuration. The
closed-lab auth proxy exercises account identity/permissions without resetting
passwords; it does not prove a real password or OIDC sign-in. Alert evaluation is
disabled and the network has no external egress.

A first startup without provisioning files removed 25 dashboard resources from
that disposable restore. Grafana's stock orphan cleanup explains the behavior;
all 35 remain available in production. The accepted conversion/dump was untouched.
A fresh restore with the actual provider/files passes all 35. Final startup must
keep the dashboard sidecar, provider, service account and its discovery RBAC.

All 95 source data-key identities and ciphertexts survive full-field comparison,
along with OAuth/session/password state. The stock CLI processes every restored
key, but its success is not an authentication proof: the upstream AES-CFB cipher
can rewrap with a wrong key without an error. Acceptance therefore relies on
unchanged pinned-image encryption configuration, exact key/ciphertext preservation
and the separate fixture's actual decrypted-credential request. The four real
datasources currently have no populated encrypted credential fields. Production
rekeying is out of scope. Real login and connectivity still require production
acceptance; configuration fingerprints cannot establish a fresh OIDC login.

## Next step

Refresh full PostgreSQL/NAS capacity and overlapping writers; prepare retained
startup guards, actual layered Helm output and the exact native execution package.
Rehearse cold recovery and failure boundaries, then complete one independent final
review before production. The remaining work is recorded in the
[implementation plan](../plans/2026-10-16-grafana-postgresql-csi.md).

## Primary sources

- [Grafana supported databases and customer-managed conversion](https://grafana.com/docs/grafana/latest/setup-grafana/installation/)
- [Grafana 13 unified-storage behavior](https://grafana.com/docs/grafana/latest/upgrade-guide/upgrade-v13.0/)
- [Exact Grafana defaults](https://github.com/grafana/grafana/blob/v13.2.3/conf/defaults.ini)
- [Stock dashboard orphan cleanup](https://github.com/grafana/grafana/blob/v13.2.3/pkg/services/provisioning/dashboards/dashboard.go)
- [Stock data-key re-encryption](https://github.com/grafana/grafana/blob/v13.2.3/pkg/services/secrets/database/database.go)
- [Stock AES decryption](https://github.com/grafana/grafana/blob/v13.2.3/pkg/services/encryption/provider/decipher_aes.go)
- [PostgreSQL 18 date/time precision](https://www.postgresql.org/docs/18/datatype-datetime.html)
- [Grafana-owned MySQL migrator](https://github.com/grafana/database-migrator)
