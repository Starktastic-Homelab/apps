# Operations and Home Assistant migration assessment

Status: read-only assessment complete; user accepted the CrowdSec precision exception.
No production changes, outage, owner acquisition, storage allocation, source
snapshot, credential rotation or database conversion has occurred.

The user authorized autonomous Karakeep + Meilisearch, Bytestash, ConvertX,
Excalidash, Home Assistant and CrowdSec migration, pausing for real decisions.
Preserve existing data, identities, versions, credentials and unattended rebuilds.

## Current evidence

Collected October17 at11:37UTC. All six ArgoCD Applications Healthy/Synced.
One active writer Pod each; CrowdSec additionally has three agents. ConvertX
has three historical Failed Pods and a current Running Pod; no diagnosis or
cleanup has been performed.

| App | Current version | Approximate private state | Direction |
|---|---|---|---|
| Karakeep / Meilisearch |0.33.2 /1.55.0|0.80 /0.16MiB|SQLite job/main DBs and intact search store on CSI|
| Bytestash |1.5.12|0.32MiB|SQLite and files on CSI; retain old empty inherited claim|
| ConvertX |0.18.0|1.72MiB|Complete SQLite/files directory on CSI|
| Excalidash |0.6.5|0.75MiB|Qualify PostgreSQL; preserve JWT/CSRF keys through encrypted declarations; potentially no app PVC|
| Home Assistant / Matter |2026.9.3 /1.4.0|208 /13.5MiB|Existing recorder history/config and Matter state on CSI|
| CrowdSec |1.8.1; chart0.24.2|37.1MiB|Qualify PostgreSQL with accepted precision exception|

All source trees contain ordinary directories/files, without symlinks, specials
or xattrs. Excalidash backend is1001:65533; Matter is1000:1000. Preserve actual
identities. Home Assistant's existing custom components, integration/auth entries,
history and Matter identities are all in scope. No deliberate device actions.

Pinned Karakeep uses SQLite for application and job state. Bytestash uses
better-sqlite3; ConvertX uses Bun SQLite. Home Assistant supports PostgreSQL but
explicitly does not support existing-history migration, consistent with the prior
accepted existing-engine/CSI policy.

The current Meilisearch wrapper deletes the search store on a version-marker
mismatch. Recovery preparation must guard the intact current version and prevent
an accidental wipe; no version upgrade is included.

Excalidash's consistent in-memory SQLite snapshot passed integrity and foreign-key
checks:17application tables,10application rows,28separate Prisma migration records.
Its stock provider-specific PostgreSQL schema/clients and environment-supplied
JWT_SECRET/CSRF_SECRET may allow complete DB conversion without an app PVC.
This is not yet a qualified conversion or file-volume removal.

CrowdSec's consistent in-memory snapshot passed integrity and foreign-key checks:
12tables,51,565rows. Stock backend switching does not migrate existing data and
requires new registrations, which is not accepted preservation. A custom transfer
would have to retain every row, registration, credential, relationship and ID
allocation history. Generated CAPI/cscli Kubernetes Secrets additionally require
durable encrypted declarations; SQL alone is insufficient for rebuild recovery.

## Required CrowdSec decision

110,523timestamp values across22columns have nonzero sub-microsecond digits.
PostgreSQL18 native timestamps have one-microsecond resolution. Proposed sole
exception: deterministically truncate fractions to microseconds, changing each
affected instant by strictly less than1microsecond. No other loss/reset is allowed.
A full isolated stock-image rehearsal and independent SQL restore remain required.
No preservation exception from another app is inherited.

Alternative: keep CrowdSec's complete SQLite state on retained CSI and preserve
nanosecond timestamps exactly. The user accepted the PostgreSQL precision exception; no other loss is authorized.

## Capacity and recovery constraints

NAS pool ONLINE; dataset quota256GiB, available about179.8GiB. Active raw files
have185GiB total logical capacity and145.4GiB potential remaining growth.
The protected historical64GiB Jellyfin partial occupies26.4GiB; preserve it as
fixed historical evidence, not a growing active disk. Its actual allocation is
already in dataset/pool usage.

Provisional new file-storage budget20GiB: Karakeep4 +Meilisearch4 +Bytestash2
+ConvertX4 +Home Assistant4 +Matter2. Excalidash/CrowdSec need no app disk only
if full PostgreSQL and credential recovery qualification succeeds. CrowdSec's
SQLite alternative adds2GiB. Recheck full growth, staging,8GiB spare, physical
free, identities and target collisions before any allocation; no quota change
has been made or selected. VM300 has about371MiB available memory and is not a
rehearsal host. Its native maintenance owner is absent.

Reuse installed immutable native ownership/fencing/receipt tools with fresh
operation identity. Preserve cold encrypted recovery on VM300 and this computer
with separate keys; require independent native recovery, source/helper retirement,
stock startup, clean recreation and healthy-worker movement. Preserve source
roots/claims/snapshots; no stale source restart after target authority. Exact-head
CI and scoped Argo diff precede merges; final desired/live checks and six-minute
watch precede cleanup/owner release. No live operation has started.

## Primary references

- https://github.com/karakeep-app/karakeep/blob/v0.33.2/packages/db/drizzle.config.ts
- https://github.com/jordan-dalby/ByteStash/blob/v1.5.12/server/src/config/database.js
- https://github.com/C4illin/ConvertX/blob/v0.18.0/src/db/db.ts
- https://www.home-assistant.io/integrations/recorder/
- https://github.com/ZimengXiong/ExcaliDash/blob/v0.6.5/backend/docker-entrypoint.sh
- https://docs.crowdsec.net/docs/next/local_api/database/
- https://github.com/crowdsecurity/crowdsec/blob/v1.8.1/pkg/database/ent/migrate/schema.go
- https://www.postgresql.org/docs/18/datatype-datetime.html

## Qualification progress

The user accepted only CrowdSec timestamp truncation below one microsecond.
Pinned native PostgreSQL schemas, synthetic complete-field imports, stock-image
startup and independent full database dump/restore passed for both applications.
CrowdSec's two JSON fields use SQLite BLOB storage: strict UTF-8 decoding followed
by native JSONB insertion preserved nested values and a number above 2^53 exactly.
The corrected live read-only normalization check accepted every current source
field; full cold-source conversion/recovery is still required before authority.

The isolated Argo credential test restored exact original-shaped multiline bytes
with native file sealing and proved the upstream CAPI hook skipped registration.
Repeated hooks retained Secret UIDs and values while recreating SealedSecrets.
No production credentials entered the fixture. Fresh namespace recovery is being
checked separately. TLS currently means no cscli password Secret exists; preserve
only the actual CAPI and shared LAPI/registration identities.

Inactive file overlays use six static retained claims totaling 20GiB. Their guards
refuse missing/wrong identity, invalid native files and mismatched Meilisearch
versions without writing data. Supplemental groups retain current access while
avoiding CSI fsGroup ownership rewriting. No production cutover has started.
