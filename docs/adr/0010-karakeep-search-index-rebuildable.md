# ADR 0010: Treat the Karakeep Meilisearch index as rebuildable

- **Status:** Accepted
- **Date:** 2026-11-05

## Context

Karakeep keeps its search index in a Meilisearch sidecar on the retained CSI volume `karakeep-meilisearch-block`
(`/meili_data`). Meilisearch refuses to open a `data.ms` written by another engine version. The retained-storage cutover
treated the index like irreplaceable data: the init guard and the container wrapper refused to start unless the binary
and the stored version were both exactly 1.55.0, and a test pinned the image tag. Every Meilisearch update (for example
Renovate PR #1448, v1.55.0 to v1.56.1) therefore failed CI and would have crash-looped the pod.

Karakeep's database (`karakeep-data-block`) is the source of truth. Karakeep can rebuild the whole index from it with
`Reindex All Bookmarks`. The "Upgrading Meilisearch" section of Karakeep's troubleshooting docs gives exactly that
workaround for an incompatible engine version: delete `data.ms`, start Meilisearch, reindex. The same page advises not
upgrading Meilisearch without good reason, which is why updates stay manual.

## Decision

Decided by Ben on 2026-11-05: the index is rebuildable, so an engine version change wipes the index instead of being
blocked.

1. The `karakeep-meilisearch` guard keeps the volume identity marker check and drops the engine-version checks.
2. The Meilisearch wrapper compares `meilisearch --version` with `/meili_data/.version_marker`. It wipes in exactly two
   cases: the marker's content differs from the running version, or the marker does not exist. It then logs what it is
   discarding, deletes only `data.ms` and the old marker, writes the new version, and starts Meilisearch on an empty
   index. A same-version restart keeps the index.
3. The wrapper exits without deleting anything when `/meili_data/.homelab-karakeep-meilisearch-data` is missing or is a
   symlink (the container is not on the retained volume, for example it lost its mount), or when the version marker
   exists but cannot be read (a directory, a symlink, or a read error). The wrapper only ever writes the marker as a
   regular file, so a symlink is refused rather than followed.
4. Renovate still needs a manual merge for Meilisearch updates, because each one needs a reindex afterwards.
5. The reindex is a manual admin step: `Admin Settings > Background Jobs > Reindex All Bookmarks`, or
   `POST /api/v1/admin/jobs/trigger/reindex` with body `{}` and an admin user's API key (Karakeep 0.33.2). Karakeep
   recreates the missing `bookmarks` index on its own but does not fill it. Karakeep keeps its index handle while it
   runs: if the reindex fails with `index_not_found`, restart Karakeep, then retry.
6. Rollout order: merge this change first, wait for ArgoCD to sync `base-configs` (it carries the guard ConfigMaps),
   then rebase and merge the Meilisearch update (Starktastic-Homelab/apps#1448), then reindex. The old guard still
   requires a 1.55.0 marker, so it would refuse the pod at its next start after the engine change.

## Rationale

Qualifying a migration for every Meilisearch release costs a PR each time, for an index that a reindex rebuilds.
Meilisearch's in-place migration (`MEILI_UPGRADE_DB`) is one-way, so each release would still need checking. Automating
the reindex would need a long-lived admin API key in the cluster just for this. We did not add one.

## Consequences

- Meilisearch updates no longer fail CI. Search returns nothing between the upgrade and the reindex. Bookmarks, lists,
  tags and assets are not affected.
- Rolling the image back also wipes the index, which an older engine could not open anyway.
- Embeddings would also live in this Meilisearch, but embeddings are not enabled here. If they are turned on later, also
  run `Regenerate Embeddings for All Bookmarks` after an upgrade, which calls the embedding provider again.
- The guards for Karakeep's own data volume and for every other retained application are unchanged.
