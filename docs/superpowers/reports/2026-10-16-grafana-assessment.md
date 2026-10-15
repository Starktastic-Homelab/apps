# Grafana PostgreSQL and retained-storage assessment

Status: metadata discovery and synthetic conversion/recovery accepted. Real-data
qualification is blocked on explicit sensitive-transfer approval. Production
configuration and storage are unchanged; no outage, enrollment, CSI allocation,
maintenance owner or migration hold has been started.

## Actual runtime

Grafana 13.2.3-distroless runs the same image used by the closed local lab:
`grafana/grafana@sha256:202e5d5b3f8499e70ccac7991eea6d7da72d2790eb2e0597e7987acf724e7180`.
It is Healthy/Synced with one Ready Pod and zero restarts. Effective admin settings
confirm SQLite. Its 2Gi NFS claim holds about 159.3MiB logical / 81.5MiB allocated.
`grafana.db` is about 14.3MiB, integrity ok, with 94 tables. Current metadata counts
include 2 users, 4 data sources, 43 unified resources, 553 resource-history rows,
95 data keys and existing OAuth/session state. These are online observations,
not a consistent backup or evidence of a production conversion.

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

All six owned lab containers are stopped and generation identities are retained
privately for exact cleanup. No real Grafana data has entered the local workspace.
Synthetic success does not establish real-data conversion, real OIDC login,
production datasource connectivity, CSI movement or production recoverability.

## Transfer decision and next step

Automatic approval review rejected the proposed consistent SQLite-copy command
because general Grafana authorization did not explicitly cover moving credential
and OAuth/session records to this computer. The rejected command did not execute;
no alternative route was attempted. The exact payload, private destinations,
isolated use, encrypted recovery retention and plaintext cleanup are described in
the [design's transfer scope](../specs/2026-10-16-grafana-postgresql-csi-design.md#sensitive-copy-scope-requiring-explicit-transfer-approval).

After explicit transfer approval, copy current consistent state with SQLite backup
semantics and perform real full-field comparison, fresh independent restore and
functional qualification. Continue autonomous preparation/execution only while
preservation and existing architecture requirements hold. The remaining plan is
[recorded here](../plans/2026-10-16-grafana-postgresql-csi.md).

## Primary sources

- [Grafana supported databases and customer-managed conversion](https://grafana.com/docs/grafana/latest/setup-grafana/installation/)
- [Grafana 13 unified-storage behavior](https://grafana.com/docs/grafana/latest/upgrade-guide/upgrade-v13.0/)
- [Exact Grafana defaults](https://github.com/grafana/grafana/blob/v13.2.3/conf/defaults.ini)
- [PostgreSQL 18 date/time precision](https://www.postgresql.org/docs/18/datatype-datetime.html)
- [Grafana-owned MySQL migrator](https://github.com/grafana/database-migrator)
