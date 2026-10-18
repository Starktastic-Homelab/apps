# Immich recovery checkpoint writer scope

Status: the user selected the checkpoint-only pause on18October2026. This
approves preparation strategy; no outage or production change is authorized.
The user accepted stock Dispatcharr DVR resets. No Dispatcharr startup override
will be added; its full migration checkpoint still includes all queue messages.

## Fresh observations

Read-only inventory found21 running workloads with writable NFS mounts overlapping
`/mnt/main/media/immich`. Immich mounts that directory directly. Filebrowser and
19 additional applications mount its parent `/mnt/main/media` writable. This
establishes filesystem access, not that those applications currently write photos.
All26 owning Applications in the combined Redis/Immich inventory were Healthy and
Synced. The maintenance runtime identity and every installed file hash matched;
no maintenance operation was held. VM300 had7600480256bytes free.

The additional applications are:

- `audiobookshelf`
- `bazarr`
- `cross-seed`
- `jellyfin`
- `lidarr`
- `lingarr`
- `metube`
- `navidrome`
- `qbit-manage`
- `qbit-manage-ru`
- `qbittorrent`
- `qbittorrent-ru`
- `radarr`
- `radarr-ru`
- `shelfmark`
- `sonarr`
- `sonarr-ru`
- `subgen`
- `unpackerr`

Both database sources additionally have the expected Filebrowser and NFS
provisioner parent mounts under `/mnt/apps/pv`. Those are already part of the
database retirement procedure.

Immich originals stay on NFS. Their root is a directory in `main/media`, dataset
GUID7793984242400538160, rather than its own dataset. A coordinated ZFS snapshot
therefore covers the full media dataset (about46TB referenced); it does not copy
46TB immediately, but retaining it can retain blocks changed/deleted elsewhere in
that dataset. Original assets are not copied to the2GiB/10GiB CSI images.

## Accepted preparation strategy

**Plan a coordinated pause of all21 overlapping workloads**
for the database/original-asset checkpoint. Stop verified owners under scoped
holds, capture the immutable database and asset recovery points, then resume the
unrelated media applications immediately after their capture/retirement gate.
Their pause is limited to this checkpoint barrier, not Immich's full restore,
CSI qualification or acceptance. Jellyfin playback and qBittorrent transfers
would be interrupted during that barrier. Current mount definitions stay intact.
The barrier duration has not yet been rehearsed; a restart-time estimate is not
an outage guarantee. The finished execution proposal will give the budget,
recovery commands and explicit affected list before any live action.

**Considered alternative, not selected: first qualify a narrower set of effective writers.** Read the
applications' current library/download/output paths and native job configuration,
then determine whether disjoint paths and a complete consistency proof justify
leaving specific applications running. A broad writable mount alone is not proof
of an active writer, so this option does not assume every listed app modifies
photos. Unexplained paths or an overlapping actual writer still block capture.
Any necessary permanent mount change would need its own reviewed scope; this
option does not authorize making one.

The selected strategy leaves existing mounts unchanged and resumes unrelated
media workloads after the immutable checkpoint barrier. Filebrowser and the NFS
provisioner remain paused until database-source retirement permits their release.
Production execution, outage, snapshot
creation, real-data/key transfers, allocation and merges remain separately gated.
