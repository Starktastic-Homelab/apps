# Paperless and Calibre retained CSI completion

Both remaining justified storage migrations are complete. The application images,
PostgreSQL/Redis dependencies, accounts, keys and endpoints are unchanged.

| Application | Retained CSI state | NFS state retained in use | Delivery |
| --- | --- | --- | --- |
| Paperless-ngx | Private data: Tantivy index, native scheduler state and logs; one 1GiB RWOP volume | Documents, consume and ordinary configuration | [Preparation #1411](https://github.com/Starktastic-Homelab/apps/pull/1411), [activation #1412](https://github.com/Starktastic-Homelab/apps/pull/1412) |
| Calibre-Web Automated | Complete config, app.db, gdrive.db, cwa.db, metadata.db and complete .calnotes; one 1GiB RWOP volume | Book files and ingest | [Preparation #1413](https://github.com/Starktastic-Homelab/apps/pull/1413), [activation #1414](https://github.com/Starktastic-Homelab/apps/pull/1414) |

## Calibre stock layout

The unchanged upstream image uses its native split-library settings. The CSI
volume's `config` and `library` directories mount at `/config` and
`/calibre-library`; NFS books mount at `/calibre-books`, and ingest remains at
`/cwa-book-ingest`. Database directories are mounted whole so journals and notes
resources stay beside their databases. No driver or application patch is used.

Cold copy compared all 48 entries and 7,734,632 bytes with full POSIX metadata.
The bundled Calibre APSW extension verified integrity and every table before
setting the three approved stock split fields. All other cells, accounts and the
encryption key were preserved. Existing Google Drive, Kobo, KOReader and Hardcover
integrations were disabled; enabled conversion and metadata enforcement were
qualified with isolated synthetic ingestion and conversion.

The exact image passed synthetic stock web login, metadata edit, cover, original
and newly converted book downloads, author notes and cold recovery. Production
acceptance passed all five native database checks, existing account/settings/key
hashes, stock read-only book/notes reads and login HTTP on both workers and after
final normal scheduling. Native assertions are explicitly enabled because
`calibre-debug` otherwise runs optimized Python.

The same 1GiB raw image and filesystem UUID survived every attachment. Each
attachment's actual VM, SCSI slot and WWN was checked independently. Stops were
graceful and verified through the Kubernetes API and both VM generations' real
runtime processes/mounts. No force detach or forced process termination was used.

## Retained recovery state

The old Paperless data remains on its retained NFS claim with private-data access
held; its document and consume subpaths remain in use. Calibre's old config claim
is retained and blocked for new Pods. Original metadata and complete notes were
renamed intact outside active books under the root-only NAS directory
`/mnt/main/media/.homelab-retired-calibre/calibre-csi-9a6db837d6ba/`.

Calibre's root-private cold checkpoint remains inside the homelab at
`/mnt/apps/pv/.homelab-checkpoints/calibre-csi-9a6db837d6ba/retained/`.
The final comparison confirmed unchanged checkpoint, original config, archived
metadata/notes and ordinary book bytes/POSIX metadata. Application credentials
never entered workstation or CI fixtures. Old sources are retained; automatic
fallback to them after accepted target writes is prohibited.

## Final acceptance

- All 78 Argo applications are Healthy/Synced; scoped owners reconciled the exact
  activation revision. Calibre and Filebrowser access and the NFS provisioner are restored.
- All 95 unrelated controller UIDs/specifications are unchanged.
- 33 active CSI attachments: worker01 has 12, worker02 has 21. Current recordings
  match Kubernetes and leave 25 usable slots; capacity rules are healthy and alerts inactive.
- Fresh native full-growth checks include every retained raw image, 512MiB
  staging and 8GiB spare under the unchanged 288GiB quota.
- Both maintenance owners, temporary host operation files, reconciliation holds,
  copy helpers and synthetic containers/fixtures are removed. Permanent source
  guards remain. No new identity, VM, credential transfer or quota increase was required.
